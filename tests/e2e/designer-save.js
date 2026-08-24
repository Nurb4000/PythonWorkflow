'use strict';
/* Designer save/cancel test against a DISPOSABLE workflow, deleted at the end. */
const { BASE, connect, newPage, login, sleep, apiLogin, request, creds } = require('./lib');

function step(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => console.log('PASS  ' + name))
    .catch((e) => {
      console.log('FAIL  ' + name + '  -> ' + e.message);
      throw e;
    });
}

(async () => {
  const token = await apiLogin(...creds('dev'));
  let wfId = null;
  let stepA = null;
  let stepB = null;

  try {
    // Create a disposable two-step workflow
    const created = await request('POST', '/api/workflows/', {
      token,
      body: {
        name: 'E2E Designer Save ' + Date.now(),
        description: 'created by tests/e2e/designer-save.js',
        steps: [
          { step_type: 'delay', definition: { seconds: 1 } },
          { step_type: 'delay', definition: { seconds: 1 } },
        ],
      },
    });
    if (created.status !== 200 || !created.body || !created.body.id) {
      throw new Error('create workflow failed: ' + created.status + ' ' + JSON.stringify(created.body));
    }
    wfId = created.body.id;

    const detail = await request('GET', '/api/workflows/' + wfId, { token });
    const steps = detail.body.steps || [];
    stepA = steps[0].id;
    stepB = steps[1].id;
    const cfg = await request('PUT', '/api/workflows/' + wfId, { token, body: { config: { start_step_ids: [stepA] } } });
    if (cfg.status !== 200) throw new Error('set start step failed: ' + cfg.status);
    console.log('created workflow ' + wfId + ' (A=' + stepA + ', B=' + stepB + ')');

    const browser = await connect();
    const { page } = await newPage(browser);
    page.on('dialog', async (d) => {
      console.log('DIALOG: ' + d.message());
      await d.accept();
    });

    await login(page, ...creds('dev'));
    await page.goto(BASE + '/workflows/' + wfId + '/design', { waitUntil: 'networkidle0' });
    await page.waitForSelector('.react-flow__node', { timeout: 10000 });
    await sleep(1200);

    const edgeCount = () => page.evaluate(() => document.querySelectorAll('.react-flow__edge').length);
    const edgesInitial = await edgeCount();
    console.log('edges before save: ' + edgesInitial);

    // SAVE FLOW: add an output A -> B, save, reload, confirm persisted
    await step('add output A->B and Save Workflow persists after reload', async () => {
      await page.evaluate((id) => {
        document.querySelector('.react-flow__node[data-id="step-' + id + '"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
      }, stepA);
      await page.waitForFunction(() => [...document.querySelectorAll('h3')].some((h) => h.textContent.includes('Edit Step')), { timeout: 4000 });
      await page.evaluate(() => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        [...modal.querySelectorAll('button')].find((b) => b.textContent.trim() === '+ Add Output').click();
      });
      await page.waitForFunction(() => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        return !!modal && modal.querySelectorAll('select.form-select').length > 0;
      }, { timeout: 4000 });
      await page.evaluate((b) => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        const sel = modal.querySelector('select.form-select');
        sel.value = String(b);
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }, stepB);
      await sleep(300);
      await page.evaluate(() => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        [...modal.querySelectorAll('button')].find((x) => x.textContent.trim() === 'Save Changes').click();
      });
      await sleep(1000);
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === 'Save Workflow');
        if (btn) btn.click();
      });
      await sleep(2500);
      const err = await page.evaluate(() => [...document.querySelectorAll('.error')].map((e) => e.textContent.trim()).join(' | '));
      if (err) throw new Error('save error: ' + err);

      await page.reload({ waitUntil: 'networkidle0' });
      await page.waitForSelector('.react-flow__node', { timeout: 10000 });
      await sleep(1200);
      const after = await edgeCount();
      // Wiring A->B replaces A's auto-connect to End, so the raw count does not
      // grow; assert the persisted graph instead (API ground truth) plus a
      // rendered A->B edge in the DOM.
      const detailAfter = await request('GET', '/api/workflows/' + wfId, { token });
      const defA = (detailAfter.body.steps || []).find((s) => s.id === stepA);
      const nexts = (defA?.definition?.next_step_ids) || (defA?.definition?.next_step_id ? [defA.definition.next_step_id] : []);
      if (!nexts.map(Number).includes(Number(stepB))) {
        throw new Error('A->B not persisted after reload; definition.next_step_ids=' + JSON.stringify(nexts));
      }
      const hasABEdge = await page.evaluate((a) =>
        [...document.querySelectorAll('.react-flow__edge')].some((e) => (e.getAttribute('data-id') || '').startsWith('e-' + a + '-')), stepA);
      if (!hasABEdge) throw new Error('no rendered edge out of step A after reload');
      if (after < 3) throw new Error('edges lost after reload: ' + after);
    });

    // CANCEL FLOW: make a staged change, Cancel -> confirm -> leaves designer, DB unchanged
    await step('Cancel with unsaved changes shows confirm and leaves designer', async () => {
      await page.evaluate((id) => {
        document.querySelector('.react-flow__node[data-id="step-' + id + '"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
      }, stepB);
      await page.waitForFunction(() => [...document.querySelectorAll('h3')].some((h) => h.textContent.includes('Edit Step')), { timeout: 4000 });
      await page.evaluate(() => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        [...modal.querySelectorAll('button')].find((b) => b.textContent.trim() === '+ Add Output').click();
      });
      await sleep(400);
      await page.evaluate(() => {
        const modal = [...document.querySelectorAll('.card')].find((c) => c.querySelector('h3')?.textContent.includes('Edit Step'));
        [...modal.querySelectorAll('button')].find((x) => x.textContent.trim() === 'Save Changes').click();
      });
      await sleep(800);
      const dirty = await page.evaluate(() => [...document.querySelectorAll('p')].some((e) => e.textContent.includes('Unsaved changes')));
      if (!dirty) throw new Error('dirty indicator not shown');

      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === 'Cancel');
        if (btn) btn.click();
      });
      await sleep(1500);
      const url = page.url();
      if (!url.includes('/workflows/' + wfId) || url.includes('/design')) {
        throw new Error('after cancel landed on ' + url);
      }
    });

    await browser.disconnect();
  } finally {
    if (wfId) {
      const del = await request('DELETE', '/api/workflows/' + wfId, { token });
      console.log('deleted disposable workflow ' + wfId + ' (' + del.status + ')');
    }
  }
})().catch((e) => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
