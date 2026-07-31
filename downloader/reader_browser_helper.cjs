const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const READER_PATH_RE = /\/reader\/\d+\/\d+(?:\/)?(?:[?#].*)?$/i;

function log(message) {
  process.stdout.write(`${message}\n`);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function safeFolderName(value, fallback) {
  let name = String(value || '')
    .replace(/[<>:\"/\\|?*\x00-\x1F]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[. ]+$/g, '');

  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) {
    name = `_${name}`;
  }

  return name || fallback;
}

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    url.hash = '';
    return url.href;
  } catch {
    return String(value || '');
  }
}

function readerIdFromUrl(value, fallback = 'issue') {
  try {
    const match = new URL(value).pathname.match(/\/reader\/\d+\/(\d+)/i);
    return match ? match[1] : fallback;
  } catch {
    return fallback;
  }
}

function safeExtension(url, contentType) {
  const typeMap = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
    'image/avif': '.avif'
  };

  const normalizedType = String(contentType || '').split(';')[0].trim().toLowerCase();
  if (typeMap[normalizedType]) return typeMap[normalizedType];

  try {
    const ext = path.extname(new URL(url).pathname).toLowerCase();
    if (/^\.[a-z0-9]{2,5}$/.test(ext)) return ext;
  } catch {}

  return '.jpg';
}

async function waitForCapturedImage(capturedImages, imageUrl, timeoutMs) {
  const key = normalizeUrl(imageUrl);
  const deadline = Date.now() + Math.min(timeoutMs, 15000);

  while (Date.now() < deadline) {
    const captured = capturedImages.get(key);
    if (captured) return captured;
    await sleep(100);
  }

  return capturedImages.get(key) || null;
}

async function findActiveImage(page, timeoutMs) {
  try {
    await page.waitForFunction(
      () => {
        const wrap = document.querySelector('div.reader__item-wrap.active');
        const img = wrap?.querySelector('img');
        if (!img) return false;
        const raw = img.currentSrc || img.src || img.dataset.src || img.dataset.lazySrc || img.dataset.original;
        return Boolean(raw && !raw.startsWith('data:') && !raw.startsWith('blob:'));
      },
      null,
      { timeout: timeoutMs }
    );
  } catch {
    return null;
  }

  return page.evaluate(() => {
    const wrap = document.querySelector('div.reader__item-wrap.active');
    const img = wrap?.querySelector('img');
    if (!img) return null;
    const raw = img.currentSrc || img.src || img.dataset.src || img.dataset.lazySrc || img.dataset.original;
    if (!raw || raw.startsWith('data:') || raw.startsWith('blob:')) return null;
    return new URL(raw, location.href).href;
  });
}

function saveCapturedImage(captured, imageUrl, outBase) {
  const extension = safeExtension(imageUrl, captured.contentType);
  const outFile = `${outBase}${extension}`;
  if (fs.existsSync(outFile)) return { outFile, skipped: true, method: 'browser response' };
  fs.writeFileSync(outFile, captured.body);
  return { outFile, skipped: false, method: 'browser response' };
}

async function saveElementScreenshot(page, outBase) {
  const locator = page.locator('div.reader__item-wrap.active img').first();
  const outFile = `${outBase}.png`;
  if (fs.existsSync(outFile)) return { outFile, skipped: true, method: 'element screenshot' };
  await locator.screenshot({ path: outFile, animations: 'disabled' });
  return { outFile, skipped: false, method: 'element screenshot' };
}

async function collectReaderLinksFromCurrentPage(page) {
  return page.evaluate(() => {
    const selector = [
      'h3.cl__item-title a[href]',
      '.cl__item-title a[href]'
    ].join(',');

    return [...document.querySelectorAll(selector)]
      .map(anchor => {
        try { return new URL(anchor.getAttribute('href'), location.href).href; }
        catch { return null; }
      })
      .filter(Boolean)
      .filter(url => /\/reader\/\d+\/\d+(?:\/)?(?:[?#].*)?$/i.test(url));
  });
}

async function waitForAndDismissModal(page, config) {
  try {
    await page.waitForFunction(
      () => document.documentElement.innerHTML.includes('un-modal'),
      null,
      { timeout: Math.min(config.timeoutMs, 15000) }
    );
  } catch {
    return false;
  }

  const viewport = page.viewportSize() || { width: 1280, height: 900 };
  await page.mouse.click(24, Math.max(24, viewport.height - 24));
  await page.waitForTimeout(config.pageDelayMs);
  return true;
}

async function activateIssueListTab(page, config) {
  const issueTab = page.locator('.tabs__select-item').nth(1);
  try {
    await issueTab.waitFor({ timeout: Math.min(config.timeoutMs, 15000) });
  } catch {
    log('The second .tabs__select-item was not found; scanning current page state.');
    return false;
  }

  try {
    await issueTab.click({ timeout: 5000 });
    await page.waitForTimeout(config.pageDelayMs);
    return true;
  } catch (error) {
    log(`Could not click the second .tabs__select-item: ${error.message}`);
    return false;
  }
}

async function prepareListingPage(page, config) {
  if (!config.didAttemptModalDismiss) {
    config.didAttemptModalDismiss = true;
    if (await waitForAndDismissModal(page, config)) {
      log('Dismissed un-modal overlay with a bottom-left click.');
    }
  }
  if (await activateIssueListTab(page, config)) {
    log('Clicked the second .tabs__select-item before scanning links.');
  }
}

async function getForwardPaginationKind(page) {
  return page.evaluate(() => {
    const container = document.querySelector('.cl__navigation.pagination__pages');
    if (!container) return 'none';

    const forward = [...container.querySelectorAll('a, span')]
      .find(element => /\bForward\b/i.test((element.textContent || '').trim()));
    if (!forward) return 'none';
    return forward.matches('a[href]') ? 'a' : 'span';
  });
}

async function discoverIssueUrls(page, startUrl, config) {
  const issueUrls = new Map();
  let pageNumber = 1;

  log(`Chapter list page: ${startUrl}`);
  await page.goto(startUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(config.pageDelayMs);
  await prepareListingPage(page, config);

  while (true) {
    try {
      await page.waitForSelector('h3.cl__item-title a[href], .cl__item-title a[href]', { timeout: config.timeoutMs });
    } catch {
      log('No .cl__item-title links were found on this page.');
    }

    const links = await collectReaderLinksFromCurrentPage(page);
    for (const link of links) issueUrls.set(normalizeUrl(link), link);
    log(`Collected ${links.length} reader link(s) from listing page ${pageNumber}; ${issueUrls.size} unique total.`);

    const forwardKind = await getForwardPaginationKind(page);
    if (forwardKind !== 'a') {
      log(forwardKind === 'span'
        ? 'Forward pagination is disabled; reached the last listing page.'
        : 'No Forward pagination link found; listing discovery is complete.');
      break;
    }

    const forward = page.locator('.cl__navigation.pagination__pages a', { hasText: /Forward/i }).first();
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: Math.min(config.timeoutMs, 10000) }).catch(() => null),
      forward.click({ timeout: 5000 })
    ]);
    await page.waitForTimeout(config.pageDelayMs);
    await prepareListingPage(page, config);
    pageNumber += 1;
  }

  return [...issueUrls.values()];
}

async function downloadIssue(page, context, capturedImages, issueUrl, seriesDestination, config, issueIndex, issueTotal) {
  capturedImages.clear();
  const issueId = readerIdFromUrl(issueUrl, String(issueIndex).padStart(4, '0'));

  log(`\n[${issueIndex}/${issueTotal}] Opening issue: ${issueUrl}`);
  await page.goto(issueUrl.split('#')[0], { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(config.pageDelayMs);

  try {
    await page.waitForSelector('div.reader__item-wrap', { timeout: config.timeoutMs });
  } catch {
    log(`[${issueId}] No reader__item-wrap elements found. Skipping issue.`);
    return;
  }

  const rawIssueTitle = await page.locator('div.chapter__selector-trigger__title.text-truncate')
    .first().textContent().catch(() => null);
  const issueTitle = safeFolderName(rawIssueTitle, issueId);

  let issueDestination = path.join(seriesDestination, issueTitle);
  if (fs.existsSync(issueDestination)) {
    // Reusing an existing same-title folder is intentional for resume support.
  }
  fs.mkdirSync(issueDestination, { recursive: true });
  log(`[${issueId}] Issue folder: ${issueTitle}`);

  const readerItemCount = await page.locator('div.reader__item-wrap').count();
  log(`[${issueId}] Found ${readerItemCount} reader item(s).`);
  if (readerItemCount < 1) return;

  for (let pageNumber = 1; pageNumber <= readerItemCount; pageNumber++) {
    if (pageNumber === 1) {
      await page.evaluate(() => { location.hash = 'page-1'; });
    } else {
      await page.evaluate(number => { location.hash = `page-${number}`; }, pageNumber);
    }
    await page.waitForTimeout(config.pageDelayMs);

    await page.evaluate(() => {
      document.querySelector('div.reader__item-wrap.active')?.scrollIntoView({ block: 'center' });
    });
    await page.waitForTimeout(Math.min(config.pageDelayMs, 1000));

    const imageUrl = await findActiveImage(page, Math.min(config.timeoutMs, 15000));
    if (!imageUrl) {
      log(`[${issueId}][page ${pageNumber}] No active reader image found. Skipping page.`);
      continue;
    }

    const outBase = path.join(
      issueDestination,
      `${String(issueId)}_${String(pageNumber).padStart(4, '0')}`
    );

    try {
      const captured = await waitForCapturedImage(capturedImages, imageUrl, config.timeoutMs);
      const result = captured
        ? saveCapturedImage(captured, imageUrl, outBase)
        : await saveElementScreenshot(page, outBase);

      log(`[${issueId}][page ${pageNumber}] ${result.skipped ? 'Already exists' : 'Saved'} via ${result.method}: ${path.basename(result.outFile)}`);
    } catch (error) {
      log(`[${issueId}][page ${pageNumber}] Save failed: ${error.message}`);
    }
  }
}

async function main() {
  const configPath = process.argv[2];
  if (!configPath) throw new Error('Missing config path.');

  const rawConfig = fs.readFileSync(configPath, 'utf8').replace(/^\uFEFF/, '');
  const config = JSON.parse(rawConfig);
  fs.mkdirSync(config.seriesDestination, { recursive: true });

  const browser = await chromium.launch({
    headless: Boolean(config.headless),
    args: ['--disable-blink-features=AutomationControlled']
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 900 },
    locale: 'en-US'
  });

  const page = await context.newPage();
  const capturedImages = new Map();

  page.on('response', async response => {
    try {
      const contentType = String(response.headers()['content-type'] || '').toLowerCase();
      if (!contentType.startsWith('image/') || !response.ok()) return;
      const body = await response.body();
      if (!body || body.length === 0) return;
      capturedImages.set(normalizeUrl(response.url()), {
        body,
        contentType,
        status: response.status()
      });
    } catch {}
  });

  page.setDefaultTimeout(config.timeoutMs);
  page.setDefaultNavigationTimeout(config.timeoutMs);

  try {
    let issueUrls;
    const pathname = new URL(config.inputUrl).pathname;

    if (READER_PATH_RE.test(pathname)) {
      log('Direct reader URL detected. Only this issue will be downloaded.');
      issueUrls = [config.inputUrl];
    } else {
      log('Series page detected. Discovering reader URLs across chapter-list pagination...');
      issueUrls = await discoverIssueUrls(page, config.inputUrl, config);
    }

    issueUrls = [...new Map(issueUrls.map(url => [normalizeUrl(url), url])).values()].reverse();

    log(`\nFound ${issueUrls.length} unique issue URL(s).`);
    if (issueUrls.length === 0) return;

    for (let i = 0; i < issueUrls.length; i++) {
      await downloadIssue(
        page,
        context,
        capturedImages,
        issueUrls[i],
        config.seriesDestination,
        config,
        i + 1,
        issueUrls.length
      );
    }
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  console.error(`ERROR: ${error.stack || error.message}`);
  process.exit(1);
});