#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_VAULT = String.raw`E:\Desktop\codex项目\whostv-current`;
const DEFAULT_DIRECTORY = path.join(DEFAULT_VAULT, "脚本归档");
const DEFAULT_STATE = path.join(DEFAULT_VAULT, ".loveav", "whostv-state.json");

function usage(message = "") {
  if (message) console.error(message);
  console.error("用法：node generate_whostv_scraper.js (--pages n | --from 1 --to n | --incremental) [--directory 路径] [--state 状态JSON] [--reason 原因] [--delay 500] [--timeout 30000]");
  process.exit(2);
}

function parseArgs(argv) {
  const options = {
    mode: "", from: 1, to: 0, directory: DEFAULT_DIRECTORY, state: DEFAULT_STATE,
    reason: "按用户要求生成", delay: 500, timeout: 30000,
  };
  const values = [...argv];
  while (values.length) {
    const token = values.shift();
    if (token === "--pages") { options.mode = "pages"; options.from = 1; options.to = Number(values.shift()); }
    else if (token === "--from") options.from = Number(values.shift());
    else if (token === "--to") { options.mode = "pages"; options.to = Number(values.shift()); }
    else if (token === "--incremental") options.mode = "incremental";
    else if (token === "--directory") options.directory = values.shift() || usage("--directory 缺少路径");
    else if (token === "--state") options.state = values.shift() || usage("--state 缺少路径");
    else if (token === "--reason") options.reason = values.shift() || usage("--reason 缺少说明");
    else if (token === "--delay") options.delay = Number(values.shift());
    else if (token === "--timeout") options.timeout = Number(values.shift());
    else usage(`未知参数：${token}`);
  }
  if (!options.mode) usage("必须指定 --pages、--to 或 --incremental");
  if (options.mode === "pages" && (!Number.isInteger(options.from) || !Number.isInteger(options.to) || options.from !== 1 || options.to < options.from)) usage("只支持第 1-n 页，起始页必须是 1");
  if (!Number.isInteger(options.delay) || options.delay < 200 || options.delay > 10000) usage("--delay 必须是 200-10000 毫秒");
  if (!Number.isInteger(options.timeout) || options.timeout < 1000 || options.timeout > 120000) usage("--timeout 必须是 1000-120000 毫秒");
  return options;
}

function readState(file) {
  try { return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")); }
  catch (error) { throw new Error(`无法读取动态状态 ${file}：${error.message}`); }
}

function shanghaiParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(now);
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return { date: `${get("year")}-${get("month")}-${get("day")}`, stamp: `${get("year")}${get("month")}${get("day")}-${get("hour")}${get("minute")}${get("second")}` };
}

function buildConsoleScript(config) {
  const template = String.raw`(async () => {
  'use strict';
  const CONFIG = __CONFIG__;
  const runtimeScope = typeof window === 'undefined' ? globalThis : window;
  const runtimeKey = '__whosTvScrapeRuntime';
  const startedAt = Date.now();
  const entries = [];
  const ignoredNonAnswerCards = [];
  const seenUrls = new Set();
  const seenPageSignatures = new Map();
  let pagesRequested = 0;
  let pagesProcessed = 0;
  let activeController = null;
  let cancelDelay = null;
  let cancelRequested = false;
  let downloaded = false;
  let finalStatus = '失败';

  if (runtimeScope[runtimeKey]?.active) {
    throw new Error('已有 Whos.tv 抓取正在运行。请先执行 window.cancelWhosTvScrape()，等待其结束后再重试。');
  }
  const runState = { active: true };
  runtimeScope[runtimeKey] = runState;
  const cancellationError = () => {
    const error = new Error('抓取已由用户取消，停止且不下载。');
    error.name = 'WhosTvCancellationError';
    return error;
  };
  const throwIfCancelled = () => {
    if (cancelRequested) throw cancellationError();
  };
  const elapsedMs = () => Date.now() - startedAt;
  runtimeScope.cancelWhosTvScrape = () => {
    if (runtimeScope[runtimeKey] !== runState || !runState.active) {
      console.log('[Whos.tv] 当前没有正在运行的抓取任务。');
      return false;
    }
    if (cancelRequested) {
      console.log('[Whos.tv] 取消请求已经收到，正在安全停止。');
      return false;
    }
    cancelRequested = true;
    if (activeController) activeController.abort();
    if (cancelDelay) cancelDelay();
    console.warn('[Whos.tv] 已收到取消请求；将停止抓取，不下载任何文件。');
    return true;
  };
  console.log('[Whos.tv] 抓取已启动；控制台显示 Promise {<pending>} 属于正常现象，请以进度日志为准。', {
    mode: CONFIG.mode,
    pageRange: CONFIG.mode === 'pages' ? CONFIG.fromPage + '-' + CONFIG.toPage : '第 1 页至截止帖',
    delayMs: CONFIG.delayMs,
    requestTimeoutMs: CONFIG.requestTimeoutMs,
    cancel: 'window.cancelWhosTvScrape()',
  });

  try {
  const host = location.hostname.toLowerCase();
  if (!(host === 'whos.tv' || host.endsWith('.whos.tv'))) {
    throw new Error('请先打开 whos.tv 的已解决列表页面，再运行此脚本。');
  }

  const isVisible = (element) => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const controls = [...document.querySelectorAll('a, button, [role="button"], [data-account-menu], [data-user-menu]')].filter(isVisible);
  const hasLogout = controls.some((element) => /(?:登出|退出登录|logout|sign\s*out)/i.test((element.textContent || '').trim()));
  const hasAccountMenu = controls.some((element) =>
    element.matches('[data-account-menu], [data-user-menu], [aria-label*="account" i], [aria-label*="账户" i], [aria-label*="账号" i]') ||
    /(?:账户|账号|个人资料|account|profile)/i.test((element.textContent || '').trim())
  );
  if (!hasAccountMenu || !hasLogout) {
    throw new Error('未通过可见账户菜单和“登出”确认登录。请先登录并展开账户菜单，然后重新运行。');
  }
  const solvedTabLink = [...document.querySelectorAll('a[href]')].find((anchor) => {
    try {
      const candidate = new URL(anchor.getAttribute('href'), location.href);
      return candidate.searchParams.get('tab') === 'solved' && /\/helps(?:\/page-\d+)?\/?$/.test(candidate.pathname);
    } catch { return false; }
  });
  if (!solvedTabLink) {
    throw new Error('找不到求助社区的“已解决”入口，页面结构可能已经变化，停止且不下载。');
  }
  const solvedListBaseUrl = new URL(solvedTabLink.getAttribute('href'), location.href);
  const solvedListBasePath = solvedListBaseUrl.pathname.replace(/\/page-\d+\/?$/, '').replace(/\/$/, '');
  if (!/\/helps$/.test(solvedListBasePath)) {
    throw new Error('“已解决”入口路径不符合预期，停止且不下载。');
  }
  const buildSolvedPageUrl = (page) => {
    const pageUrl = new URL(solvedListBaseUrl.href);
    pageUrl.pathname = page === 1 ? solvedListBasePath : solvedListBasePath + '/page-' + page;
    pageUrl.searchParams.delete('page');
    pageUrl.searchParams.set('tab', 'solved');
    pageUrl.hash = '';
    return pageUrl;
  };

  const sleep = (milliseconds) => new Promise((resolve, reject) => {
    throwIfCancelled();
    const timer = setTimeout(() => {
      cancelDelay = null;
      resolve();
    }, milliseconds);
    cancelDelay = () => {
      clearTimeout(timer);
      cancelDelay = null;
      reject(cancellationError());
    };
  });
  const absolute = (value, base) => new URL(value, base).href;
  const realHttp = (value, base) => {
    try {
      const url = new URL(value, base);
      return /^https?:$/.test(url.protocol) ? url.href : '';
    } catch { return ''; }
  };
  const textWithLinks = (element, baseUrl) => {
    const clone = element.cloneNode(true);
    for (const anchor of clone.querySelectorAll('a[href]')) {
      const url = realHttp(anchor.getAttribute('href'), baseUrl);
      const label = (anchor.textContent || '').trim();
      anchor.replaceWith(document.createTextNode(url ? (label && label !== url ? label + ' ' + url : url) : label));
    }
    return (clone.textContent || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
  };
  const parsePage = (html, page, pageUrl) => {
    const documentForPage = new DOMParser().parseFromString(html, 'text/html');
    const articles = [...documentForPage.querySelectorAll('article[data-help-id], article[data-post-href]')];
    if (!articles.length) throw new Error('第 ' + page + ' 页解析为 0 条，停止且不下载。');
    const rows = [];
    const ignored = [];
    for (const [index, article] of articles.entries()) {
      const heading = article.querySelector('h2');
      const link = article.getAttribute('data-post-href') || heading?.querySelector('a[href*="/helps/"]')?.getAttribute('href') || '';
      if (!link) throw new Error('第 ' + page + ' 页第 ' + (index + 1) + ' 条找不到帖子地址。');
      const url = absolute(link, pageUrl);
      const title = (heading?.textContent || '').replace(/\s+/g, ' ').trim();
      if (!title) throw new Error('第 ' + page + ' 页第 ' + (index + 1) + ' 条标题为空。');
      const answerRegion = article.querySelector('[data-post-answer-preview]');
      const articleText = (article.textContent || '').replace(/\s+/g, ' ').trim();
      const isPinnedAnnouncement = !answerRegion && /置顶/u.test(articleText) && /官方公告/u.test(articleText);
      if (isPinnedAnnouncement) {
        ignored.push({ page, position: index + 1, title, url, reason: '置顶官方公告，不是已解决答案' });
        continue;
      }
      if (!answerRegion) {
        throw new Error(
          '第 ' + page + ' 页第 ' + (index + 1) + ' 条（' + title +
          '）没有已采纳答案区域。为避免漏抓，停止且不下载；请确认网站“已解决”筛选和页面结构。'
        );
      }
      let answer = '';
      const explicitAnswerBody = answerRegion.querySelector('[data-answer-body], [data-answer-text], .answer-content');
      const paragraphs = [...answerRegion.querySelectorAll('p')];
      if (explicitAnswerBody) answer = textWithLinks(explicitAnswerBody, pageUrl);
      else if (paragraphs.length) answer = paragraphs.map((paragraph) => textWithLinks(paragraph, pageUrl)).filter(Boolean).join('\n');
      else answer = textWithLinks(answerRegion, pageUrl);
      if (!answer) {
        const fallback = (article.textContent || '').match(/答案[：:]\s*([\s\S]+)$/u);
        answer = fallback ? fallback[1].trim() : '';
      }
      if (!answer) throw new Error('第 ' + page + ' 页第 ' + (index + 1) + ' 条答案为空，停止且不下载。');
      rows.push({ page, position: index + 1, title, answer, url, pageUrl });
    }
    if (!rows.length) throw new Error('第 ' + page + ' 页没有可提取的已解决答案，停止且不下载。');
    return { rows, ignored };
  };
  const fetchPage = async (page) => {
    throwIfCancelled();
    const pageUrl = buildSolvedPageUrl(page);
    const controller = new AbortController();
    let timedOut = false;
    pagesRequested += 1;
    activeController = controller;
    console.log('[Whos.tv] 第 ' + page + ' 页：开始请求', {
      url: pageUrl.href,
      timeoutMs: CONFIG.requestTimeoutMs,
    });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, CONFIG.requestTimeoutMs);
    try {
      const response = await fetch(pageUrl.href, {
        credentials: 'include',
        cache: 'no-store',
        signal: controller.signal,
      });
      throwIfCancelled();
      if (!response.ok) {
        const error = new Error('第 ' + page + ' 页请求失败：HTTP ' + response.status + '，停止且不下载。');
        error.name = 'WhosTvHttpError';
        throw error;
      }
      const html = await response.text();
      throwIfCancelled();
      return { pageUrl: pageUrl.href, html };
    } catch (error) {
      if (cancelRequested || error?.name === 'WhosTvCancellationError') throw cancellationError();
      if (timedOut) {
        throw new Error('第 ' + page + ' 页请求超过 ' + CONFIG.requestTimeoutMs + ' 毫秒，停止且不下载。');
      }
      if (error?.name === 'WhosTvHttpError') throw error;
      throw new Error('第 ' + page + ' 页网络请求失败：' + (error?.message || String(error)) + '，停止且不下载。');
    } finally {
      clearTimeout(timeout);
      if (activeController === controller) activeController = null;
    }
  };
  let stopFound = CONFIG.mode !== 'incremental';
  const append = (row, page) => {
    if (seenUrls.has(row.url)) {
      throw new Error('第 ' + page + ' 页未取得分页进展：发现重复帖子 URL ' + row.url + '，停止且不下载。');
    }
    seenUrls.add(row.url);
    entries.push(row);
  };

  const shortTitle = (title) => {
    const normalized = String(title || '').replace(/\s+/g, ' ').trim();
    return normalized.length > 48 ? normalized.slice(0, 47) + '…' : normalized;
  };
  const rowPath = (row) => new URL(row.url).pathname.replace(/\/$/, '');
  const processPage = async (page, stopAtCutoff) => {
    throwIfCancelled();
    const pageStartedAt = Date.now();
    const fetched = await fetchPage(page);
    const parsed = parsePage(fetched.html, page, fetched.pageUrl);
    throwIfCancelled();
    const signature = parsed.rows.map((row) => rowPath(row)).join('\n');
    const repeatedFromPage = seenPageSignatures.get(signature);
    if (repeatedFromPage !== undefined) {
      throw new Error(
        '第 ' + page + ' 页与第 ' + repeatedFromPage +
        ' 页返回相同帖子列表，分页可能失效，停止且不下载。'
      );
    }
    seenPageSignatures.set(signature, page);
    ignoredNonAnswerCards.push(...parsed.ignored);
    const cutoffIndex = stopAtCutoff ? parsed.rows.findIndex((row) => rowPath(row) === CONFIG.cutoffPath) : -1;
    const rowsBeforeStop = cutoffIndex >= 0 ? parsed.rows.slice(0, cutoffIndex) : parsed.rows;
    if (rowsBeforeStop.length && rowsBeforeStop.every((row) => seenUrls.has(row.url))) {
      throw new Error(
        '第 ' + page + ' 页没有带来新记录：该页待收录帖子 URL 全部已在前页出现，分页没有进展，停止且不下载。'
      );
    }
    let acceptedOnPage = 0;
    let foundCutoffOnPage = false;
    for (const [index, row] of parsed.rows.entries()) {
      throwIfCancelled();
      const pathname = rowPath(row);
      if (stopAtCutoff && pathname === CONFIG.cutoffPath) {
        foundCutoffOnPage = true;
        stopFound = true;
        console.log(
          '[Whos.tv] 第 ' + page + ' 页 ' + (index + 1) + '/' + parsed.rows.length +
          ' | 累计 ' + entries.length + ' | 命中截止点，不收录 | ' + pathname + ' | ' + shortTitle(row.title)
        );
        break;
      }
      append(row, page);
      acceptedOnPage += 1;
      console.log(
        '[Whos.tv] 第 ' + page + ' 页 ' + (index + 1) + '/' + parsed.rows.length +
        ' | 累计 ' + entries.length + ' | ' + pathname + ' | ' + shortTitle(row.title)
      );
    }
    pagesProcessed += 1;
    console.log('[Whos.tv] 第 ' + page + ' 页：完成', {
      extracted: parsed.rows.length,
      accepted: acceptedOnPage,
      ignored: parsed.ignored.length,
      cumulative: entries.length,
      cutoffFound: foundCutoffOnPage,
      durationMs: Date.now() - pageStartedAt,
    });
    if (!foundCutoffOnPage && acceptedOnPage === 0) {
      throw new Error('第 ' + page + ' 页没有带来任何新记录，分页没有进展，停止且不下载。');
    }
    return { foundCutoffOnPage };
  };

  if (CONFIG.mode === 'pages') {
    for (let page = CONFIG.fromPage; page <= CONFIG.toPage; page += 1) {
      await processPage(page, false);
      if (page < CONFIG.toPage) await sleep(CONFIG.delayMs);
    }
  } else {
    for (let page = 1; page <= CONFIG.maxPages; page += 1) {
      const result = await processPage(page, true);
      if (result.foundCutoffOnPage) break;
      if (page < CONFIG.maxPages) await sleep(CONFIG.delayMs);
    }
    if (!stopFound) throw new Error('抓取到安全页数上限仍未找到截止帖 ' + CONFIG.cutoffPath + '，停止且不下载。');
  }

  if (!entries.length) throw new Error('没有抓到截止帖之前的新答案，不生成空文件。');
  if (entries.some((entry) => !entry.answer.trim())) throw new Error('结果中存在空答案，不下载。');
  const payload = {
    mode: CONFIG.mode,
    count: entries.length,
    generatedAt: new Date().toISOString(),
    durationMs: elapsedMs(),
    pagesFetched: pagesProcessed,
    cutoffPath: CONFIG.mode === 'incremental' ? CONFIG.cutoffPath : '',
    stopFound,
    pageStart: CONFIG.fromPage,
    pageEnd: Math.max(...entries.map((entry) => entry.page)),
    ignoredNonAnswerCards,
    entries,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = downloadUrl;
  anchor.download = CONFIG.outputFile;
  document.body.appendChild(anchor);
  anchor.click();
  downloaded = true;
  finalStatus = '成功';
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
  console.log('[Whos.tv] 抓取完成', {
    count: entries.length,
    pages: pagesProcessed,
    durationMs: elapsedMs(),
    ignoredNonAnswerCards: ignoredNonAnswerCards.length,
    first: entries[0].url,
    last: entries.at(-1).url,
    output: CONFIG.outputFile,
  });
  } catch (error) {
    finalStatus = cancelRequested || error?.name === 'WhosTvCancellationError' ? '已取消' : '失败';
    const report = {
      status: finalStatus,
      reason: error?.message || String(error),
      pagesRequested,
      pagesProcessed,
      count: entries.length,
      durationMs: elapsedMs(),
      downloaded: false,
      stateUpdated: false,
    };
    if (finalStatus === '已取消') console.warn('[Whos.tv] 抓取已取消；未下载文件，也未更新状态。', report);
    else console.error('[Whos.tv] 抓取失败；未下载文件，也未更新状态。', report);
    throw error;
  } finally {
    runState.active = false;
    activeController = null;
    cancelDelay = null;
    console.log('[Whos.tv] 运行结束', {
      status: finalStatus,
      pagesRequested,
      pagesProcessed,
      count: entries.length,
      durationMs: elapsedMs(),
      downloaded,
      stateUpdated: false,
    });
  }
})();`;
  return template.replace("__CONFIG__", JSON.stringify(config, null, 2));
}

function archive(directory, script, metadata) {
  fs.mkdirSync(directory, { recursive: true });
  const generatedDirectory = path.join(directory, "generated");
  fs.mkdirSync(generatedDirectory, { recursive: true });
  const scriptFile = path.join(generatedDirectory, metadata.scriptName);
  fs.writeFileSync(scriptFile, `${script}\n`, "utf8");
  const archiveFile = path.join(directory, "whostv_scripts.md");
  const old = fs.existsSync(archiveFile) ? fs.readFileSync(archiveFile, "utf8").replace(/^\uFEFF/, "") : "";
  const entry = [
    `# ${metadata.title}`, "",
    `- 用途：${metadata.purpose}`,
    `- 范围：${metadata.range}`,
    `- 输出文件：\`${metadata.outputFile}\``,
    `- 修改原因：${metadata.reason}`,
    "", "```javascript", script, "```", "",
  ].join("\n");
  fs.writeFileSync(archiveFile, old ? `${entry}\n${old}` : entry, "utf8");
  const organizerFile = path.join(directory, "organize_whos_answers.js");
  fs.copyFileSync(path.resolve(__dirname, "organize_whos_answers.js"), organizerFile);
  return { scriptFile, archiveFile, organizerFile };
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const state = readState(path.resolve(options.state));
  const time = shanghaiParts();
  let config;
  let metadata;
  if (options.mode === "incremental") {
    const cutoffPath = String(state.cutoffPath || "");
    if (!/^\/helps\/\d+$/.test(cutoffPath)) throw new Error(`动态状态中的截止点无效：${cutoffPath}`);
    const outputFile = String(state.nextJsonName || `whos_tv_solved_answers_since_${state.lastProcessedDate || time.date}.json`);
    config = {
      mode: "incremental", fromPage: 1, toPage: null, cutoffPath, outputFile,
      delayMs: options.delay, requestTimeoutMs: options.timeout, maxPages: 500,
    };
    metadata = {
      title: `Whos.tv 增量抓取（截止 ${cutoffPath}）`, purpose: "从第 1 页抓取到当前截止帖之前",
      range: `第 1 页开始；遇到 ${cutoffPath} 停止且不收录截止帖`, outputFile,
      reason: options.reason, scriptName: `whostv_incremental_${time.stamp}.js`,
    };
  } else {
    const outputFile = `whos_tv_solved_answers_pages_${options.from}-${options.to}.json`;
    config = {
      mode: "pages", fromPage: options.from, toPage: options.to, cutoffPath: "", outputFile,
      delayMs: options.delay, requestTimeoutMs: options.timeout, maxPages: options.to,
    };
    metadata = {
      title: `Whos.tv 第 ${options.from}-${options.to} 页抓取`, purpose: "抓取指定范围的已解决页面",
      range: `第 ${options.from}-${options.to} 页`, outputFile,
      reason: options.reason, scriptName: `whostv_pages_${options.from}_${options.to}_${time.stamp}.js`,
    };
  }
  const script = buildConsoleScript(config);
  const paths = archive(path.resolve(options.directory), script, metadata);
  console.log(JSON.stringify({ ok: true, mode: options.mode, config, ...paths }, null, 2));
}

try { main(); } catch (error) {
  console.error(`生成 Whos.tv 抓取脚本失败：${error.message}`);
  process.exitCode = 1;
}
