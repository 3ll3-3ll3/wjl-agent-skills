"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const organizer = path.join(root, "scripts", "organize_whos_answers.js");
const generator = path.join(root, "scripts", "generate_whostv_scraper.js");

function run(script, args) {
  return spawnSync(process.execPath, [script, ...args], { encoding: "utf8" });
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function fakeArticle({ href, title, answer = null, announcement = false }) {
  const heading = { textContent: title, querySelector: () => null };
  const answerRegion = answer === null ? null : {
    textContent: answer,
    querySelector: () => null,
    querySelectorAll: () => [],
    cloneNode: () => ({ textContent: answer, querySelectorAll: () => [] }),
  };
  return {
    textContent: announcement ? `置顶 Whos.tv 官方 官方公告 ${title}` : `已解决 ${title} ${answer || ""}`,
    getAttribute: (name) => name === "data-post-href" ? href : null,
    querySelector: (selector) => {
      if (selector === "h2") return heading;
      if (selector === "[data-post-answer-preview]") return answerRegion;
      return null;
    },
  };
}

function scraperHarness(script, articles, options = {}) {
  const requests = [];
  const logs = [];
  const warnings = [];
  const errors = [];
  let downloadedBlob = null;
  let downloadedName = "";
  class CapturingURL extends URL {
    static createObjectURL(blob) {
      downloadedBlob = blob;
      return "blob:whostv-test";
    }
    static revokeObjectURL() {}
  }
  const visibleControl = (textContent, isAccount = false) => ({
    textContent,
    matches: () => isAccount,
    getBoundingClientRect: () => ({ width: 10, height: 10 }),
  });
  const solvedTabLink = { getAttribute: () => "/helps?tab=solved" };
  const articlesForPage = (page) => options.pages?.[page] || articles;
  const context = {
    AbortController,
    Blob,
    URL: CapturingURL,
    console: {
      log: (...args) => logs.push(args),
      warn: (...args) => warnings.push(args),
      error: (...args) => errors.push(args),
    },
    location: { hostname: "whos.tv", href: "https://whos.tv/helps" },
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    setTimeout: options.setTimeout || (() => 0),
    clearTimeout: options.clearTimeout || (() => {}),
    document: {
      body: { appendChild() {} },
      querySelectorAll: (selector) => selector === "a[href]"
        ? [solvedTabLink]
        : [visibleControl("账户", true), visibleControl("登出")],
      createElement: () => ({
        href: "",
        download: "",
        click() { downloadedName = this.download; },
        remove() {},
      }),
    },
    DOMParser: class {
      parseFromString(html) {
        return {
          querySelectorAll: () => articlesForPage(Number(html) || 1),
        };
      }
    },
    fetch: async (url, init) => {
      requests.push(String(url));
      if (options.fetch) return options.fetch(url, init);
      const page = Number(new URL(url).pathname.match(/\/page-(\d+)/)?.[1] || 1);
      return { ok: true, text: async () => String(page) };
    },
  };
  return {
    requests,
    logs,
    warnings,
    errors,
    run: () => vm.runInNewContext(script, context),
    cancel: () => context.cancelWhosTvScrape?.(),
    downloadedBlob: () => downloadedBlob,
    downloadedName: () => downloadedName,
  };
}

function fixtureEntries() {
  return [
    { page: 1, position: 1, title: "只有番号", answer: "ABC-123\nFC2 PPV 123456", url: "https://whos.tv/helps/10260", pageUrl: "https://whos.tv/helps?status=solved&page=1" },
    { page: 1, position: 2, title: "只有链接", answer: "请看 https://example.com/a", url: "https://whos.tv/helps/10259", pageUrl: "https://whos.tv/helps?status=solved&page=1" },
    { page: 2, position: 1, title: "番号和链接", answer: "DEF-456\nhttps://example.com/b", url: "https://whos.tv/helps/10258", pageUrl: "https://whos.tv/helps?status=solved&page=2" },
    { page: 2, position: 2, title: "其他", answer: "暂时不知道，多行\n继续查找", url: "https://whos.tv/helps/10257", pageUrl: "https://whos.tv/helps?status=solved&page=2" },
  ];
}

test("organizer validates, classifies, writes Markdown, and advances cutoff", (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-organizer-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const input = path.join(temp, "whos_tv_solved_answers_since_2026-08-27.json");
  const state = path.join(temp, "state.json");
  const output = path.join(temp, "output");
  const entries = fixtureEntries();
  writeJson(input, { mode: "incremental", count: entries.length, cutoffPath: "/helps/10250", stopFound: true, entries });
  writeJson(state, { version: 1, timeZone: "Asia/Shanghai", lastProcessedDate: "2026-08-27", cutoffPath: "/helps/10250", nextJsonName: "whos_tv_solved_answers_since_2026-08-27.json" });

  const result = run(organizer, [input, "--output", output, "--state", state]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.counts, { onlyLinks: 1, other: 1, both: 1, onlyCodes: 1 });
  assert.equal(report.pureCodeCount, 2);
  const markdown = fs.readFileSync(report.output, "utf8");
  assert.match(markdown, /# 番号列表（2 条）/);
  assert.match(markdown, /ABC-123\nFC2-PPV-123456/);
  assert.match(markdown, /# 答案只有访问链接的（1 条）[\s\S]*# 其他内容（1 条）[\s\S]*# 答案同时有番号和访问链接的（1 条）[\s\S]*# 答案只有番号的（1 条）/);
  assert.equal((markdown.match(/^ABC-123$/gm) || []).length, 1);
  assert.equal(readJson(state).cutoffPath, "/helps/10260");
});

test("organizer rejects duplicate URLs without output or state change", (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-invalid-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const input = path.join(temp, "whos_tv_solved_answers_since_2026-08-27.json");
  const state = path.join(temp, "state.json");
  const output = path.join(temp, "result.md");
  const entries = fixtureEntries().slice(0, 2);
  entries[1].url = entries[0].url;
  writeJson(input, { mode: "incremental", count: entries.length, cutoffPath: "/helps/10250", stopFound: true, entries });
  writeJson(state, { cutoffPath: "/helps/10250" });
  const result = run(organizer, [input, "--output", output, "--state", state]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /重复帖子 URL/);
  assert.equal(fs.existsSync(output), false);
  assert.equal(readJson(state).cutoffPath, "/helps/10250");
});

test("organizer does not absorb the following prose word into a code", (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-code-boundary-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const input = path.join(temp, "answers.json");
  const state = path.join(temp, "state.json");
  const output = path.join(temp, "result.md");
  const entries = [
    {
      page: 1,
      position: 1,
      title: "求番号",
      answer: "HTTM-065 SNSで知り合った人妻",
      url: "https://whos.tv/helps/10255",
      pageUrl: "https://whos.tv/helps?status=solved&page=1",
    },
  ];
  writeJson(input, { mode: "pages", count: 1, entries });
  writeJson(state, { cutoffPath: "/helps/10250" });

  const result = run(organizer, [input, "--output", output, "--state", state, "--mode", "pages"]);
  assert.equal(result.status, 0, result.stderr);
  const markdown = fs.readFileSync(output, "utf8");
  assert.match(markdown, /^HTTM-065$/m);
  assert.doesNotMatch(markdown, /HTTM-065-SNS/);
});

test("generator archives newest script first and copies organizer", (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-generator-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, { lastProcessedDate: "2026-08-27", cutoffPath: "/helps/10250", nextJsonName: "whos_tv_solved_answers_since_2026-08-27.json" });

  const first = run(generator, ["--pages", "3", "--directory", temp, "--state", state, "--reason", "首次测试"]);
  assert.equal(first.status, 0, first.stderr);
  const second = run(generator, ["--incremental", "--directory", temp, "--state", state, "--reason", "增量修订"]);
  assert.equal(second.status, 0, second.stderr);
  const report = JSON.parse(second.stdout);
  const script = fs.readFileSync(report.scriptFile, "utf8");
  assert.match(script, /credentials: 'include'/);
  assert.match(script, /cache: 'no-store'/);
  assert.match(script, /article\[data-help-id\]/);
  assert.match(script, /searchParams\.get\('tab'\) === 'solved'/);
  assert.match(script, /solvedListBasePath \+ '\/page-' \+ page/);
  assert.match(script, /searchParams\.set\('tab', 'solved'\)/);
  assert.doesNotMatch(script, /searchParams\.set\('page', String\(page\)\)/);
  assert.match(script, /else answer = textWithLinks\(answerRegion, pageUrl\)/);
  assert.match(script, /置顶官方公告，不是已解决答案/);
  assert.match(script, /为避免漏抓，停止且不下载/);
  assert.match(script, /ignoredNonAnswerCards/);
  assert.match(script, /\/helps\/10250/);
  const archive = fs.readFileSync(report.archiveFile, "utf8");
  assert.ok(archive.indexOf("Whos.tv 增量抓取") < archive.indexOf("Whos.tv 第 1-3 页抓取"));
  assert.equal(path.basename(path.dirname(report.scriptFile)), "generated");
  assert.equal(fs.existsSync(report.organizerFile), true);
});

test("generated scraper forces solved list and reads an answer container without p", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, {
    lastProcessedDate: "2026-08-27",
    cutoffPath: "/helps/10260",
    nextJsonName: "whos_tv_solved_answers_since_2026-08-27.json",
  });
  const generated = run(generator, ["--incremental", "--directory", temp, "--state", state]);
  assert.equal(generated.status, 0, generated.stderr);
  const report = JSON.parse(generated.stdout);
  const script = fs.readFileSync(report.scriptFile, "utf8");
  const harness = scraperHarness(script, [
    fakeArticle({ href: "/helps/99999", title: "公告", announcement: true }),
    fakeArticle({ href: "/helps/10261", title: "新答案", answer: "ABC-123\nhttps://example.com/a" }),
    fakeArticle({ href: "/helps/10260", title: "截止帖", answer: "XYZ-789" }),
  ]);

  await harness.run();
  assert.deepEqual(harness.requests, ["https://whos.tv/helps?tab=solved"]);
  assert.equal(harness.downloadedName(), "whos_tv_solved_answers_since_2026-08-27.json");
  const payload = JSON.parse(await harness.downloadedBlob().text());
  assert.equal(payload.count, 1);
  assert.equal(payload.entries[0].url, "https://whos.tv/helps/10261");
  assert.equal(payload.entries[0].answer, "ABC-123\nhttps://example.com/a");
  assert.equal(payload.ignoredNonAnswerCards.length, 1);
  assert.equal(payload.ignoredNonAnswerCards[0].reason, "置顶官方公告，不是已解决答案");
  const progress = harness.logs.map((args) => args[0]).filter((message) => /\| 累计 \d+ \|/.test(message));
  assert.deepEqual(progress, [
    "[Whos.tv] 第 1 页 1/2 | 累计 1 | /helps/10261 | 新答案",
    "[Whos.tv] 第 1 页 2/2 | 累计 1 | 命中截止点，不收录 | /helps/10260 | 截止帖",
  ]);
});

test("generated scraper refuses an ordinary solved-list card without an answer", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-invalid-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, {
    lastProcessedDate: "2026-08-27",
    cutoffPath: "/helps/10260",
    nextJsonName: "whos_tv_solved_answers_since_2026-08-27.json",
  });
  const generated = run(generator, ["--incremental", "--directory", temp, "--state", state]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const harness = scraperHarness(script, [
    fakeArticle({ href: "/helps/10261", title: "缺少答案" }),
  ]);

  await assert.rejects(harness.run(), /没有已采纳答案区域/);
  assert.equal(harness.downloadedBlob(), null);
});

test("generated scraper logs every accepted row in order with cumulative counts", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-progress-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, { cutoffPath: "/helps/10250" });
  const generated = run(generator, ["--pages", "2", "--directory", temp, "--state", state, "--delay", "200"]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const harness = scraperHarness(script, [], {
    pages: {
      1: [
        fakeArticle({ href: "/helps/10987", title: "第一页第一条", answer: "不应出现在控制台的答案一" }),
        fakeArticle({ href: "/helps/10986", title: "第一页第二条", answer: "不应出现在控制台的答案二" }),
      ],
      2: [
        fakeArticle({ href: "/helps/10985", title: "第二页第一条", answer: "不应出现在控制台的答案三" }),
      ],
    },
    setTimeout: (callback, milliseconds) => {
      if (milliseconds === 200) queueMicrotask(callback);
      return 1;
    },
  });

  await harness.run();
  const progress = harness.logs.map((args) => args[0]).filter((message) => /\| 累计 \d+ \|/.test(message));
  assert.deepEqual(progress, [
    "[Whos.tv] 第 1 页 1/2 | 累计 1 | /helps/10987 | 第一页第一条",
    "[Whos.tv] 第 1 页 2/2 | 累计 2 | /helps/10986 | 第一页第二条",
    "[Whos.tv] 第 2 页 1/1 | 累计 3 | /helps/10985 | 第二页第一条",
  ]);
  assert.deepEqual(harness.requests, [
    "https://whos.tv/helps?tab=solved",
    "https://whos.tv/helps/page-2?tab=solved",
  ]);
  assert.equal(JSON.stringify([...harness.logs, ...harness.warnings, ...harness.errors]).includes("不应出现在控制台的答案"), false);
  const payload = JSON.parse(await harness.downloadedBlob().text());
  assert.equal(payload.count, 3);
  assert.equal(payload.pagesFetched, 2);
  const finalReport = harness.logs.find((args) => args[0] === "[Whos.tv] 运行结束")?.[1];
  assert.equal(finalReport.status, "成功");
  assert.equal(finalReport.pagesProcessed, 2);
  assert.equal(finalReport.count, 3);
});

test("generated scraper times out an unfinished page without downloading or changing state", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-timeout-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  const stateBefore = { cutoffPath: "/helps/10250", marker: "unchanged" };
  writeJson(state, stateBefore);
  const generated = run(generator, ["--pages", "1", "--directory", temp, "--state", state, "--timeout", "1000"]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const harness = scraperHarness(script, [], {
    fetch: (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      }, { once: true });
    }),
    setTimeout: (callback, milliseconds) => {
      if (milliseconds === 1000) queueMicrotask(callback);
      return 1;
    },
  });

  await assert.rejects(harness.run(), /第 1 页请求超过 1000 毫秒/);
  assert.equal(harness.downloadedBlob(), null);
  assert.deepEqual(readJson(state), stateBefore);
  assert.match(harness.logs.map((args) => args[0]).join("\n"), /第 1 页：开始请求/);
  assert.match(harness.errors.map((args) => args[0]).join("\n"), /未下载文件，也未更新状态/);
  const finalReport = harness.logs.find((args) => args[0] === "[Whos.tv] 运行结束")?.[1];
  assert.equal(finalReport.status, "失败");
  assert.equal(finalReport.downloaded, false);
});

test("generated scraper can be cancelled globally without downloading or changing state", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-cancel-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  const stateBefore = { cutoffPath: "/helps/10250", marker: "unchanged" };
  writeJson(state, stateBefore);
  const generated = run(generator, ["--pages", "1", "--directory", temp, "--state", state]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const harness = scraperHarness(script, [], {
    fetch: (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      }, { once: true });
    }),
  });

  const pending = harness.run();
  assert.equal(harness.cancel(), true);
  await assert.rejects(pending, /抓取已由用户取消/);
  assert.equal(harness.downloadedBlob(), null);
  assert.deepEqual(readJson(state), stateBefore);
  assert.match(harness.warnings.map((args) => args[0]).join("\n"), /已收到取消请求/);
  assert.match(harness.warnings.map((args) => args[0]).join("\n"), /未下载文件，也未更新状态/);
  const finalReport = harness.logs.find((args) => args[0] === "[Whos.tv] 运行结束")?.[1];
  assert.equal(finalReport.status, "已取消");
  assert.equal(finalReport.downloaded, false);
  assert.equal(harness.cancel(), false);
});

test("generated scraper rejects a repeated pagination response without downloading", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-repeat-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, { cutoffPath: "/helps/10250" });
  const generated = run(generator, ["--pages", "2", "--directory", temp, "--state", state, "--delay", "200"]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const repeatedArticles = [
    fakeArticle({ href: "/helps/10987", title: "重复第一页", answer: "ABC-123" }),
  ];
  const harness = scraperHarness(script, repeatedArticles, {
    setTimeout: (callback, milliseconds) => {
      if (milliseconds === 200) queueMicrotask(callback);
      return 1;
    },
  });

  await assert.rejects(harness.run(), /第 2 页与第 1 页返回相同帖子列表/);
  assert.equal(harness.downloadedBlob(), null);
  assert.equal(harness.errors.length, 1);
  const finalReport = harness.logs.find((args) => args[0] === "[Whos.tv] 运行结束")?.[1];
  assert.equal(finalReport.status, "失败");
  assert.equal(finalReport.pagesProcessed, 1);
});

test("generated scraper rejects pagination with no new records even when order changes", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-no-progress-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, { cutoffPath: "/helps/10250" });
  const generated = run(generator, ["--pages", "2", "--directory", temp, "--state", state, "--delay", "200"]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const first = fakeArticle({ href: "/helps/10987", title: "第一页第一条", answer: "ABC-123" });
  const second = fakeArticle({ href: "/helps/10986", title: "第一页第二条", answer: "DEF-456" });
  const harness = scraperHarness(script, [], {
    pages: { 1: [first, second], 2: [second, first] },
    setTimeout: (callback, milliseconds) => {
      if (milliseconds === 200) queueMicrotask(callback);
      return 1;
    },
  });

  await assert.rejects(harness.run(), /待收录帖子 URL 全部已在前页出现，分页没有进展/);
  assert.equal(harness.downloadedBlob(), null);
  const finalReport = harness.logs.find((args) => args[0] === "[Whos.tv] 运行结束")?.[1];
  assert.equal(finalReport.status, "失败");
  assert.equal(finalReport.pagesProcessed, 1);
});

test("generated scraper reports a network failure without downloading", async (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "whostv-runtime-network-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const state = path.join(temp, "state.json");
  writeJson(state, { cutoffPath: "/helps/10250" });
  const generated = run(generator, ["--pages", "1", "--directory", temp, "--state", state]);
  assert.equal(generated.status, 0, generated.stderr);
  const script = fs.readFileSync(JSON.parse(generated.stdout).scriptFile, "utf8");
  const harness = scraperHarness(script, [], {
    fetch: async () => { throw new TypeError("network down"); },
  });

  await assert.rejects(harness.run(), /第 1 页网络请求失败：network down/);
  assert.equal(harness.downloadedBlob(), null);
  assert.match(harness.errors.map((args) => args[0]).join("\n"), /未下载文件，也未更新状态/);
});

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}
