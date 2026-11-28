'use strict';
// M7: smoke-check admin/task screens at a phone viewport. Run with
//   bash tests/e2e/run-e2e.sh mobile-responsive.js
// against a running dev stack. Set SHOT_DIR to save screenshots.
const { BASE, connect, newPage, login, creds, sleep } = require('./lib');

const ROUTES = [
  '/admin',
  '/admin/runs',
  '/admin/tasks',
  '/tasks',
  '/my-tasks',
];

(async () => {
  const browser = await connect();
  const { page, errors } = await newPage(browser);
  await page.setViewport({
    width: 390,
    height: 844,
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });

  const [username, password] = creds('admin');
  await login(page, username, password);

  // Nav collapses to a toggle on phones; links must be reachable from it.
  await page.waitForSelector('.nav-toggle', { visible: true, timeout: 8000 });
  await page.click('.nav-toggle');
  const expanded = await page.$eval('.nav-toggle', (el) => el.getAttribute('aria-expanded'));
  if (expanded !== 'true') throw new Error('Mobile nav toggle did not open');
  const linksVisible = await page.$$eval('.nav-links a', (els) => els.length);
  if (linksVisible === 0) throw new Error('Mobile nav has no links');

  for (const route of ROUTES) {
    await page.goto(BASE + route, { waitUntil: 'networkidle0' });
    await sleep(400);
    const metrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      buttons: Array.from(document.querySelectorAll('.btn, .btn-sm')).map((el) => {
        const r = el.getBoundingClientRect();
        return { label: (el.textContent || '').trim(), width: r.width, height: r.height };
      }),
      tables: Array.from(document.querySelectorAll('table')).map((t) => ({
        clientWidth: t.clientWidth,
        scrollWidth: t.scrollWidth,
        overflowX: getComputedStyle(t).overflowX,
      })),
    }));

    if (metrics.scrollWidth > metrics.innerWidth + 1) {
      throw new Error(`${route}: page scrolls horizontally (${metrics.scrollWidth} > ${metrics.innerWidth})`);
    }
    const smallButtons = metrics.buttons.filter((b) => b.height > 0 && b.height < 40);
    if (smallButtons.length) {
      throw new Error(`${route}: ${smallButtons.length} button(s) below 40px tall: ${JSON.stringify(smallButtons.slice(0, 3))}`);
    }
    console.log(`${route}: no page overflow; ${metrics.tables.length} table(s) checked`);

    if (process.env.SHOT_DIR) {
      const name = route.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'home';
      await page.screenshot({ path: `${process.env.SHOT_DIR}/mobile-${name}.png`, fullPage: false });
    }
  }

  if (errors.length) throw new Error('Browser errors:\n' + errors.join('\n'));
  await browser.disconnect();
  console.log('Mobile responsive smoke check passed');
})().catch((e) => {
  console.error(e && e.stack || e);
  process.exit(1);
});
