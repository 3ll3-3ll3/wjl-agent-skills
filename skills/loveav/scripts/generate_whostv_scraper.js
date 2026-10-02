#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_VAULT = String.raw`E:\Desktop\codex项目\whostv-current`;
const DEFAULT_DIRECTORY = path.join(DEFAULT_VAULT, "脚本归档");
const DEFAULT_STATE = path.join(DEFAULT_VAULT, ".loveav", "whostv-state.json");
const DEFAULT_OUTPUT_DIRECTORY_HINT = path.join(DEFAULT_VAULT, ".loveav", "imports");

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
  let cancelAuthorization = null;
  let cancelRequested = false;
  let commitStarted = false;
  let saved = false;
  let savedFileName = '';
  let saveOutcome = '未开始';
  let finalStatus = '失败';

  if (runtimeScope[runtimeKey]?.active) {
    throw new Error('已有 Whos.tv 抓取正在运行。请先执行 window.cancelWhosTvScrape()，等待其结束后再重试。');
  }
  const runState = { active: true };
  runtimeScope[runtimeKey] = runState;
  const cancellationError = (message = '抓取已由用户取消，停止且不保存。') => {
    const error = new Error(message);
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
    if (commitStarted) {
      console.warn('[Whos.tv] JSON 正在提交，无法安全取消；请稍后检查最终保存结果。');
      return false;
    }
    if (cancelRequested) {
      console.log('[Whos.tv] 取消请求已经收到，正在安全停止。');
      return false;
    }
    cancelRequested = true;
    if (activeController) activeController.abort();
    if (cancelDelay) cancelDelay();
    if (cancelAuthorization) cancelAuthorization();
    console.warn('[Whos.tv] 已收到取消请求；将停止抓取，不保存任何文件。');
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
    throw new Error('找不到求助社区的“已解决”入口，页面结构可能已经变化，停止且不保存。');
  }
  const solvedListBaseUrl = new URL(solvedTabLink.getAttribute('href'), location.href);
  const solvedListBasePath = solvedListBaseUrl.pathname.replace(/\/page-\d+\/?$/, '').replace(/\/$/, '');
  if (!/\/helps$/.test(solvedListBasePath)) {
    throw new Error('“已解决”入口路径不符合预期，停止且不保存。');
  }
  const buildSolvedPageUrl = (page) => {
    const pageUrl = new URL(solvedListBaseUrl.href);
    pageUrl.pathname = page === 1 ? solvedListBasePath : solvedListBasePath + '/page-' + page;
    pageUrl.searchParams.delete('page');
    pageUrl.searchParams.set('tab', 'solved');
    pageUrl.hash = '';
    return pageUrl;
  };

  const OUTPUT_DB_NAME = 'loveav-whostv-runner-v1';
  const OUTPUT_STORE_NAME = 'directory-handles';
  const OUTPUT_DIRECTORY_KEY = 'imports-directory';
  const validateOutputDirectory = (handle) => {
    if (!handle || handle.kind !== 'directory' || handle.name !== 'imports' || typeof handle.getFileHandle !== 'function') {
      throw new Error('请选择名为 imports 的 JSON 保存目录。目标路径提示：' + CONFIG.outputDirectoryHint + '；浏览器只能核对目录名，请自行确认所选绝对路径。');
    }
    return handle;
  };
  const openOutputDb = () => new Promise((resolve, reject) => {
    if (!runtimeScope.indexedDB) {
      reject(new Error('当前浏览器不支持保存目录句柄所需的 IndexedDB，抓取尚未开始。'));
      return;
    }
    const request = runtimeScope.indexedDB.open(OUTPUT_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OUTPUT_STORE_NAME)) db.createObjectStore(OUTPUT_STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error('无法打开 JSON 保存目录权限库：' + (request.error?.message || request.error || '未知错误')));
  });
  const directoryHandleStore = async (mode, operation) => {
    const db = await openOutputDb();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(OUTPUT_STORE_NAME, mode);
        const request = operation(transaction.objectStore(OUTPUT_STORE_NAME));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(new Error('JSON 保存目录权限库操作失败：' + (request.error?.message || request.error || '未知错误')));
        transaction.onabort = () => reject(new Error('JSON 保存目录权限库事务已中止。'));
      });
    } finally {
      db.close();
    }
  };
  const restoreOutputDirectory = async () => {
    const handle = await directoryHandleStore('readonly', (store) => store.get(OUTPUT_DIRECTORY_KEY));
    return handle ? validateOutputDirectory(handle) : null;
  };
  const rememberOutputDirectory = (handle) => directoryHandleStore('readwrite', (store) => store.put(handle, OUTPUT_DIRECTORY_KEY));
  const queryWritePermission = async (handle) => {
    if (typeof handle.queryPermission !== 'function') throw new Error('当前浏览器目录句柄不支持写入权限检查。');
    return handle.queryPermission({ mode: 'readwrite' });
  };
  const requestWritePermission = async (handle) => {
    if (typeof handle.requestPermission !== 'function') throw new Error('当前浏览器目录句柄不支持写入授权。');
    return handle.requestPermission({ mode: 'readwrite' });
  };
  const waitForOutputAuthorization = (storedHandle) => new Promise((resolve, reject) => {
    if (typeof runtimeScope.showDirectoryPicker !== 'function') {
      reject(new Error('当前浏览器不支持目录选择，无法把 JSON 保存到项目 imports 目录；抓取尚未开始。'));
      return;
    }
    const panel = document.createElement('div');
    panel.id = 'loveav-whostv-output-authorization';
    Object.assign(panel.style, {
      position: 'fixed', right: '20px', bottom: '20px', zIndex: '2147483647', width: '360px',
      padding: '16px', borderRadius: '12px', background: '#111827', color: '#f9fafb',
      boxShadow: '0 12px 32px rgba(0,0,0,.35)', font: '14px/1.5 system-ui,sans-serif',
    });
    const title = document.createElement('strong');
    title.textContent = '运行前授权 JSON 保存目录';
    const description = document.createElement('p');
    description.textContent = '请选择 E:\\Desktop\\codex项目\\whostv-current\\.loveav\\imports。浏览器只能核对目录名 imports，请自行确认绝对路径。';
    const status = document.createElement('p');
    status.textContent = '授权成功后才会开始抓取。';
    const actions = document.createElement('div');
    Object.assign(actions.style, { display: 'flex', gap: '8px', flexWrap: 'wrap' });
    const makeButton = (label) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      Object.assign(button.style, { padding: '8px 12px', cursor: 'pointer' });
      actions.appendChild(button);
      return button;
    };
    const storedButton = storedHandle ? makeButton('重新授权已保存的 imports') : null;
    const chooseButton = makeButton('选择 imports 目录');
    const cancelButton = makeButton('取消');
    panel.append(title, description, status, actions);
    document.body.appendChild(panel);
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      cancelAuthorization = null;
      panel.remove();
      callback(value);
    };
    const approve = async (handle, requestPermission) => {
      try {
        validateOutputDirectory(handle);
        const permission = requestPermission ? await requestWritePermission(handle) : await queryWritePermission(handle);
        if (permission !== 'granted') throw new Error('JSON 保存目录没有获得读写权限，抓取尚未开始。');
        await rememberOutputDirectory(handle);
        finish(resolve, handle);
      } catch (error) {
        finish(reject, error);
      }
    };
    storedButton?.addEventListener('click', () => { void approve(storedHandle, true); }, { once: true });
    chooseButton.addEventListener('click', () => {
      let selection;
      try {
        selection = runtimeScope.showDirectoryPicker({ id: 'loveav-whostv-imports', mode: 'readwrite' });
      } catch (error) {
        finish(reject, error);
        return;
      }
      void Promise.resolve(selection).then((handle) => approve(handle, true), (error) => finish(reject, error));
    }, { once: true });
    cancelButton.addEventListener('click', () => finish(reject, cancellationError('用户取消了 JSON 保存目录授权，抓取尚未开始。')), { once: true });
    cancelAuthorization = () => finish(reject, cancellationError('抓取已由用户取消，JSON 保存目录尚未授权。'));
  });
  const uniqueOutputName = (fileName) => {
    const dot = fileName.toLowerCase().endsWith('.json') ? fileName.length - 5 : fileName.length;
    const random = runtimeScope.crypto?.randomUUID
      ? runtimeScope.crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
    return fileName.slice(0, dot) + '_' + Date.now() + '_' + random + '.json';
  };
  const writeJsonToDirectory = async (handle, options) => {
    validateOutputDirectory(handle);
    const { fileName, content, outputDirectoryHint, checkCancelled = () => {}, onCommitStart = () => {} } = options;
    if (!/^whos_tv_solved_answers_[a-z0-9_-]+\.json$/i.test(String(fileName || '')) ||
        outputDirectoryHint !== CONFIG.outputDirectoryHint || typeof content !== 'string') {
      throw new Error('JSON 保存参数无效。');
    }
    const completePayload = JSON.parse(content);
    if (!Array.isArray(completePayload.entries) || !completePayload.entries.length || completePayload.count !== completePayload.entries.length) {
      throw new Error('JSON 不是完整的 Whos.tv 抓取结果，停止保存。');
    }
    if (await queryWritePermission(handle) !== 'granted') throw new Error('JSON 保存目录权限已失效，请重新授权后运行。');
    checkCancelled();
    let actualName = fileName;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        await handle.getFileHandle(actualName);
        actualName = uniqueOutputName(fileName);
      } catch (error) {
        if (error?.name !== 'NotFoundError') throw error;
        break;
      }
      if (attempt === 19) throw new Error('无法分配新的 JSON 文件名，旧文件没有被覆盖。');
    }
    checkCancelled();
    const file = await handle.getFileHandle(actualName, { create: true });
    let writable;
    let localCommitStarted = false;
    try {
      writable = await file.createWritable();
      checkCancelled();
      await writable.write(content);
      checkCancelled();
      onCommitStart();
      localCommitStarted = true;
      await writable.close();
      const savedFile = await file.getFile();
      const savedText = await savedFile.text();
      const expectedBytes = new TextEncoder().encode(content).byteLength;
      if (savedText !== content || savedFile.size !== expectedBytes) throw new Error('保存后内容或字节数核验不一致。');
      return { ok: true, saved: true, fileName: actualName, bytes: expectedBytes, directoryName: handle.name };
    } catch (error) {
      try { if (writable) await writable.abort(); } catch { /* 已关闭的流不能再取消。 */ }
      let fileMayExist = localCommitStarted;
      if (!localCommitStarted) {
        try { await handle.removeEntry(actualName); } catch { fileMayExist = true; }
      }
      const failure = new Error(
        'JSON 保存失败：' + (error?.message || error) + (fileMayExist ? '；请检查 imports 中的实际文件，保存结果尚未确认。' : ''),
        { cause: error }
      );
      failure.fileMayExist = fileMayExist;
      throw failure;
    }
  };
  const prepareJsonWriter = async () => {
    if (CONFIG.outputMode !== 'project-imports-v1' || !CONFIG.outputDirectoryHint) {
      throw new Error('脚本缺少项目 imports 保存配置，抓取尚未开始。');
    }
    if (typeof runtimeScope.__loveavWhosTvWriteJson === 'function') {
      saveOutcome = '宿主保存器已就绪';
      return runtimeScope.__loveavWhosTvWriteJson;
    }
    if (!runtimeScope.indexedDB) throw new Error('当前浏览器不支持 IndexedDB，无法恢复 JSON 保存目录；抓取尚未开始。');
    let handle = null;
    try { handle = await restoreOutputDirectory(); }
    catch (error) { console.warn('[Whos.tv] 无法恢复已保存的 imports 目录，将请求重新授权。', error); }
    if (handle && await queryWritePermission(handle) === 'granted') {
      saveOutcome = '已恢复 imports 写入权限';
      return (options) => writeJsonToDirectory(handle, options);
    }
    handle = await waitForOutputAuthorization(handle);
    saveOutcome = 'imports 写入权限已授权';
    return (options) => writeJsonToDirectory(handle, options);
  };
  const jsonWriter = await prepareJsonWriter();
  throwIfCancelled();
  console.log('[Whos.tv] JSON 保存目录权限已确认；现在开始抓取。', {
    outputDirectoryHint: CONFIG.outputDirectoryHint,
    note: '绝对路径仅为提示，浏览器已核对目录名和读写权限。',
  });

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
    if (!articles.length) throw new Error('第 ' + page + ' 页解析为 0 条，停止且不保存。');
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
          '）没有已采纳答案区域。为避免漏抓，停止且不保存；请确认网站“已解决”筛选和页面结构。'
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
      if (!answer) throw new Error('第 ' + page + ' 页第 ' + (index + 1) + ' 条答案为空，停止且不保存。');
      rows.push({ page, position: index + 1, title, answer, url, pageUrl });
    }
    if (!rows.length) throw new Error('第 ' + page + ' 页没有可提取的已解决答案，停止且不保存。');
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
        const error = new Error('第 ' + page + ' 页请求失败：HTTP ' + response.status + '，停止且不保存。');
        error.name = 'WhosTvHttpError';
        throw error;
      }
      const html = await response.text();
      throwIfCancelled();
      return { pageUrl: pageUrl.href, html };
    } catch (error) {
      if (cancelRequested || error?.name === 'WhosTvCancellationError') throw cancellationError();
      if (timedOut) {
        throw new Error('第 ' + page + ' 页请求超过 ' + CONFIG.requestTimeoutMs + ' 毫秒，停止且不保存。');
      }
      if (error?.name === 'WhosTvHttpError') throw error;
      throw new Error('第 ' + page + ' 页网络请求失败：' + (error?.message || String(error)) + '，停止且不保存。');
    } finally {
      clearTimeout(timeout);
      if (activeController === controller) activeController = null;
    }
  };
  let stopFound = CONFIG.mode !== 'incremental';
  const append = (row, page) => {
    if (seenUrls.has(row.url)) {
      throw new Error('第 ' + page + ' 页未取得分页进展：发现重复帖子 URL ' + row.url + '，停止且不保存。');
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
        ' 页返回相同帖子列表，分页可能失效，停止且不保存。'
      );
    }
    seenPageSignatures.set(signature, page);
    ignoredNonAnswerCards.push(...parsed.ignored);
    const cutoffIndex = stopAtCutoff ? parsed.rows.findIndex((row) => rowPath(row) === CONFIG.cutoffPath) : -1;
    const rowsBeforeStop = cutoffIndex >= 0 ? parsed.rows.slice(0, cutoffIndex) : parsed.rows;
    if (rowsBeforeStop.length && rowsBeforeStop.every((row) => seenUrls.has(row.url))) {
      throw new Error(
        '第 ' + page + ' 页没有带来新记录：该页待收录帖子 URL 全部已在前页出现，分页没有进展，停止且不保存。'
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
      throw new Error('第 ' + page + ' 页没有带来任何新记录，分页没有进展，停止且不保存。');
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
    if (!stopFound) throw new Error('抓取到安全页数上限仍未找到截止帖 ' + CONFIG.cutoffPath + '，停止且不保存。');
  }

  if (!entries.length) throw new Error('没有抓到截止帖之前的新答案，不生成空文件。');
  if (entries.some((entry) => !entry.answer.trim())) throw new Error('结果中存在空答案，不保存。');
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
  const content = JSON.stringify(payload, null, 2);
  const expectedBytes = new TextEncoder().encode(content).byteLength;
  throwIfCancelled();
  saveOutcome = '正在写入并核验';
  const saveResult = await jsonWriter({
    fileName: CONFIG.outputFile,
    content,
    mimeType: 'application/json;charset=utf-8',
    outputDirectoryHint: CONFIG.outputDirectoryHint,
    checkCancelled: throwIfCancelled,
    onCommitStart: () => {
      commitStarted = true;
      saveOutcome = '正在提交，稍后检查保存结果';
      console.log('[Whos.tv] JSON 已写入临时流，正在提交并核验；此阶段无法安全取消。');
    },
  });
  const actualName = String(saveResult?.fileName || '');
  const expectedStem = CONFIG.outputFile.replace(/\.json$/i, '');
  const validActualName = actualName === CONFIG.outputFile ||
    (actualName.startsWith(expectedStem + '_') && /^whos_tv_solved_answers_[a-z0-9_-]+\.json$/i.test(actualName));
  if (saveResult?.ok !== true || saveResult?.saved !== true || !validActualName ||
      saveResult.bytes !== expectedBytes || saveResult.directoryName !== 'imports') {
    const evidenceError = new Error('保存器没有返回完整且一致的 JSON 落盘证据，不能报告成功。');
    evidenceError.fileMayExist = commitStarted || saveResult?.saved === true;
    throw evidenceError;
  }
  saved = true;
  savedFileName = actualName;
  saveOutcome = '已保存并核验';
  finalStatus = '成功';
  console.log('[Whos.tv] 抓取完成', {
    count: entries.length,
    pages: pagesProcessed,
    durationMs: elapsedMs(),
    ignoredNonAnswerCards: ignoredNonAnswerCards.length,
    first: entries[0].url,
    last: entries.at(-1).url,
    output: savedFileName,
    outputDirectory: saveResult.directoryName,
    bytes: saveResult.bytes,
  });
  } catch (error) {
    const cancelledBeforeCommit = !commitStarted && (cancelRequested || error?.name === 'WhosTvCancellationError' || error?.name === 'AbortError');
    finalStatus = cancelledBeforeCommit ? '已取消' : '失败';
    if (!saved) saveOutcome = error?.fileMayExist ? '保存结果尚未确认' : '未保存';
    const report = {
      status: finalStatus,
      reason: error?.message || String(error),
      pagesRequested,
      pagesProcessed,
      count: entries.length,
      durationMs: elapsedMs(),
      saved: false,
      output: savedFileName || null,
      saveOutcome,
      fileMayExist: Boolean(error?.fileMayExist),
      stateUpdated: false,
    };
    if (error?.fileMayExist) console.error('[Whos.tv] 保存结果尚未确认；请检查 imports 目录。状态未更新。', report);
    else if (finalStatus === '已取消') console.warn('[Whos.tv] 抓取已取消；未保存文件，也未更新状态。', report);
    else console.error('[Whos.tv] 抓取失败；未保存文件，也未更新状态。', report);
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
      saved,
      output: savedFileName || null,
      saveOutcome,
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
      outputMode: "project-imports-v1", outputDirectoryHint: DEFAULT_OUTPUT_DIRECTORY_HINT,
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
      outputMode: "project-imports-v1", outputDirectoryHint: DEFAULT_OUTPUT_DIRECTORY_HINT,
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
