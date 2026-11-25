'use strict';
/* Read-only UI regression smoke test (never mutates the database). */
const { BASE, connect, newPage, login, sleep, creds } = require('./lib');

// Fixture workflow used by designer checks (README prerequisites). Override
// when the dev DB's fixture was recreated with a different autoincrement id.
const WF_ID = parseInt(process.env.E2E_WF_ID || '22', 10);

const ROLE_TARGETS = [
  ['admin', '/admin'],
  ['dev', '/workflows'],
  ['staff', '/tasks'],
  ['user', '/offerings'],
];

const passed = [];
const failed = [];

function step(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => {
      passed.push(name);
      console.log('PASS  ' + name);
    })
    .catch((e) => {
      failed.push(name);
      console.log('FAIL  ' + name + '  -> ' + e.message);
    });
}

(async () => {
  const browser = await connect();

  for (const [user, target] of ROLE_TARGETS) {
    await step('login ' + user + ' -> ' + target, async () => {
      const { page } = await newPage(browser);
      await login(page, ...creds(user));
      const url = page.url().replace(/\/$/, '');
      if (!url.endsWith(target)) throw new Error('landed on ' + url + ', expected ' + target);
      await page.close();
    });
  }

  await step('branding shown in app shell', async () => {
    const { page } = await newPage(browser);
    await login(page, ...creds('admin'));
    const brand = await page.evaluate(() => fetch('/api/branding').then((r) => r.json()));
    const body = await page.evaluate(() => document.body.innerText);
    if (!body.includes(brand.system_name) && !body.includes(brand.portal_name)) {
      throw new Error('navbar does not show branding ' + JSON.stringify(brand));
    }
    await page.close();
  });

  await step('workflows list shows Test WF (wf ' + WF_ID + ')', async () => {
    const { page } = await newPage(browser);
    await login(page, ...creds('dev'));
    await page.goto(BASE + '/workflows', { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => document.body.innerText.includes('Test WF'), { timeout: 8000 });
    await page.close();
  });

  await step('designer ' + WF_ID + ': edges render, end node stable during drag', async () => {
    const { page } = await newPage(browser);
    await login(page, ...creds('dev'));
    await page.goto(BASE + '/workflows/' + WF_ID + '/design', { waitUntil: 'networkidle0' });
    await page.waitForSelector('.react-flow__node', { timeout: 10000 });
    await sleep(1500);

    const edgeCount = () => page.evaluate(() => document.querySelectorAll('.react-flow__edge').length);
    const endPos = () =>
      page.evaluate(() => {
        const n = document.querySelector('.react-flow__node[data-id="end"]');
        return n ? n.style.transform : 'missing';
      });

    const edgesBefore = await edgeCount();
    if (edgesBefore < 1) throw new Error('no edges rendered');
    const endBefore = await endPos();
    if (endBefore === 'missing') throw new Error('no end node');

    const stepNode = await page.$('.react-flow__node[data-id^="step-"]');
    if (stepNode) {
      const box = await stepNode.boundingBox();
      await page.mouse.move(box.x + 30, box.y + 30);
      await page.mouse.down();
      await page.mouse.move(box.x + 90, box.y + 90, { steps: 8 });
      await page.mouse.up();
      await sleep(1200);
    }

    const endAfter = await endPos();
    if (endAfter !== endBefore) throw new Error('end node moved: ' + endBefore + ' -> ' + endAfter);
    const edgesAfter = await edgeCount();
    if (edgesAfter < edgesBefore) throw new Error('edges dropped during drag: ' + edgesBefore + ' -> ' + edgesAfter);

    await page.reload({ waitUntil: 'networkidle0' });
    await page.waitForSelector('.react-flow__node', { timeout: 10000 });
    await sleep(1200);
    if ((await edgeCount()) < 1) throw new Error('edges lost after reload');
    await page.close();
  });

  await step('settings: clearing System Name keeps page visible', async () => {
    const { page } = await newPage(browser);
    await login(page, ...creds('admin'));
    await page.goto(BASE + '/settings', { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => document.querySelector('h2')?.textContent.includes('System Settings'), { timeout: 8000 });
    await sleep(800);

    const probe = await page.evaluate(() => {
      const card = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Branding'));
      const input = card ? card.querySelectorAll('input[type=text]')[0] : null;
      if (!input) return { error: 'no branding input' };
      input.focus();
      input.select();
      return { before: input.value };
    });
    if (probe.error) throw new Error(probe.error);

    await page.keyboard.press('Backspace');
    await sleep(400);
    const state = await page.evaluate(() => ({
      h2: document.querySelector('h2')?.textContent || '',
      loading: !!document.querySelector('.loading'),
    }));
    if (!state.h2) throw new Error('page blanked after clearing system name');
    if (state.loading) throw new Error('loading spinner shown after clearing system name');
    await page.close();
  });

  await browser.disconnect();

  console.log('\nRESULT: ' + passed.length + ' passed, ' + failed.length + ' failed');
  if (failed.length) process.exit(1);
})().catch((e) => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
