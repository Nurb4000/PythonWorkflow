'use strict';
/* Entry form save persistence (P3.3) + form-on-task UI (P3.3). Creates disposable data. */
const { BASE, connect, newPage, login, sleep, request, apiLogin } = require('./lib');

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

async function getToken(user) {
  return apiLogin(user, user);
}

async function api(method, path, token, body, query) {
  const opts = {};
  if (token) opts.token = token;
  if (body !== undefined) opts.body = body;
  if (query) path += '?' + new URLSearchParams(query).toString();
  const res = await request(method, '/api' + path, opts);
  if (res.status >= 400) {
    throw new Error('API ' + method + ' ' + path + ' -> ' + res.status + ' ' + JSON.stringify(res.body));
  }
  return res.body;
}

async function findEntryFormSelect(page) {
  return page.evaluate(() => {
    const labels = [...document.querySelectorAll('.form-label')];
    const label = labels.find((l) => l.textContent.includes('Entry Form'));
    if (!label) return null;
    const group = label.closest('.form-group');
    const sel = group ? group.querySelector('select.form-select') : null;
    return sel ? { found: true, value: sel.value, options: [...sel.options].map((o) => o.value) } : null;
  });
}

function waitForText(page, text, timeout = 10000) {
  return page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);
}

function waitForNoText(page, text, timeout = 10000) {
  return page.waitForFunction((t) => !document.body.innerText.includes(t), { timeout }, text);
}

const FORM_SCHEMA = {
  type: 'object',
  title: 'E2E Approval Form',
  properties: {
    approved: { type: 'boolean', title: 'Approved' },
    notes: { type: 'string', title: 'Notes' },
    amount: { type: 'number', title: 'Amount' },
  },
  required: ['approved', 'notes'],
};

(async () => {
  const browser = await connect();
  const adminToken = await getToken('admin');
  const stamp = Date.now();
  const unique = stamp.toString();

  // ---------- Setup (API) ----------
  const form = await api('POST', '/forms', adminToken, undefined, {
    name: 'E2E Form ' + unique,
    schema: JSON.stringify(FORM_SCHEMA),
  });
  const wf = await api('POST', '/workflows/', adminToken, {
    name: 'E2E EntryForm ' + unique,
    description: 'disposable',
    steps: [{ step_type: 'delay', definition: { seconds: 0 } }],
    entry_form_id: null,
  });

  // ---------- Part A: entry form save persistence ----------
  await step('A1: select entry form + save persists selection', async () => {
    const { page } = await newPage(browser);
    await login(page, 'admin', 'admin');
    await page.goto(BASE + '/workflows/' + wf.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Portal Settings');

    const before = await findEntryFormSelect(page);
    if (!before) throw new Error('entry form select not found');

    await page.evaluate((id) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const label = labels.find((l) => l.textContent.includes('Entry Form'));
      const sel = label.closest('.form-group').querySelector('select.form-select');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
      setter.call(sel, String(id));
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }, form.id);
    await sleep(300);

    // Save via the portal settings button
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Save Portal Settings');
      btn.click();
    });
    await waitForNoText(page, 'Saving...');
    await waitForText(page, 'Save Portal Settings');
    await sleep(1200); // allow refetch after save

    const afterSave = await findEntryFormSelect(page);
    if (!afterSave || afterSave.value !== String(form.id)) {
      throw new Error('select value after save = ' + (afterSave && afterSave.value) + ', expected ' + form.id);
    }
    await page.close();
  });

  await step('A2: entry form survives page reload', async () => {
    const { page } = await newPage(browser);
    await login(page, 'admin', 'admin');
    await page.goto(BASE + '/workflows/' + wf.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Portal Settings');
    await sleep(800);
    const sel = await findEntryFormSelect(page);
    if (!sel || sel.value !== String(form.id)) {
      throw new Error('select value after reload = ' + (sel && sel.value) + ', expected ' + form.id);
    }
    await page.close();
  });

  await step('A3: clear entry form (None) saves + persists', async () => {
    const { page } = await newPage(browser);
    await login(page, 'admin', 'admin');
    await page.goto(BASE + '/workflows/' + wf.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Portal Settings');

    await page.evaluate(() => {
      const labels = [...document.querySelectorAll('.form-label')];
      const label = labels.find((l) => l.textContent.includes('Entry Form'));
      const sel = label.closest('.form-group').querySelector('select.form-select');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
      setter.call(sel, '');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await sleep(300);

    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Save Portal Settings');
      btn.click();
    });
    await waitForNoText(page, 'Saving...');
    await sleep(1200);

    await page.reload({ waitUntil: 'networkidle0' });
    await waitForText(page, 'Portal Settings');
    await sleep(800);
    const sel = await findEntryFormSelect(page);
    if (!sel || sel.value !== '') {
      throw new Error('select value after clear = ' + (sel && sel.value) + ', expected empty');
    }
    await page.close();
  });

  // ---------- Part B: form on human task ----------
  const userToken = await getToken('user');
  const me = await api('GET', '/auth/me', userToken);
  const wf2 = await api('POST', '/workflows/', adminToken, {
    name: 'E2E TaskForm ' + unique,
    description: 'disposable',
    steps: [
      {
        step_type: 'human_task',
        definition: {
          assigned_to_user_id: me.id,
          assigned_group_id: null,
          form_id: form.id,
          task_data: { kind: 'approve' },
          description: 'Please review',
          title: 'Approve request',
        },
      },
      { step_type: 'delay', definition: { seconds: 0 } },
    ],
  });

  async function makeTask() {
    const run = await api('POST', '/workflows/' + wf2.id + '/run', adminToken, {});
    for (let i = 0; i < 20; i++) {
      const res = await api('GET', '/tasks?workflow_run_id=' + run.id, adminToken);
      if (res.tasks && res.tasks.length) return res.tasks[0];
      await sleep(300);
    }
    throw new Error('no task created for run ' + run.id);
  }

  await step('B1: task page renders form read-only with fields', async () => {
    const task = await makeTask();
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/tasks/' + task.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Approved');
    await waitForText(page, 'Notes');
    await waitForText(page, 'Amount');

    const state = await page.evaluate(() => ({
      hasTake: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Take Task'),
      disabledInputs: document.querySelectorAll('.form-input:disabled, .form-textarea:disabled').length,
      submitHidden: ![...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Complete Task & Save Data'),
    }));
    if (!state.hasTake) throw new Error('Take Task button missing on open task');
    if (state.disabledInputs < 2) throw new Error('form inputs not read-only before take: ' + state.disabledInputs);
    if (!state.submitHidden) throw new Error('submit button visible before taking task');
    await page.close();
  });

  await step('B2: take task unlocks form editing', async () => {
    const task = await makeTask();
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/tasks/' + task.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Take Task');
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Take Task');
      btn.click();
    });
    await waitForNoText(page, 'Take Task');
    await sleep(800);
    const submitVisible = await page.evaluate(() =>
      [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Complete Task & Save Data'));
    if (!submitVisible) throw new Error('submit button not visible after take');
    const anyEnabled = await page.evaluate(() =>
      document.querySelectorAll('.form-input:not(:disabled), .form-textarea:not(:disabled)').length);
    if (!anyEnabled) throw new Error('form inputs still disabled after take');
    await page.close();
  });

  await step('B3: fill + submit form completes task with data', async () => {
    const task = await makeTask();
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/tasks/' + task.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Take Task');
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Take Task');
      btn.click();
    });
    await waitForNoText(page, 'Take Task');
    await sleep(600);

    const filled = await page.evaluate((uniq) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => {
        const l = labels.find((x) => x.textContent.startsWith(t));
        return l.closest('.form-group');
      };
      const notes = find('Notes').querySelector('textarea, input');
      const amount = find('Amount').querySelector('input[type=number]');
      const approved = find('Approved').querySelector('input[type=checkbox]');
      if (!notes || !amount || !approved) return { error: 'missing field inputs' };
      const nSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nSet.call(notes, 'Browser E2E notes ' + uniq);
      notes.dispatchEvent(new Event('input', { bubbles: true }));
      nSet.call(amount, '123');
      amount.dispatchEvent(new Event('input', { bubbles: true }));
      approved.click();
      return { ok: true };
    }, unique);
    if (filled.error) throw new Error(filled.error);
    await sleep(300);

    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Complete Task & Save Data');
      btn.click();
    });

    // After submit the task refetches -> status badge 'completed' and result data shown
    await page.waitForFunction(() => document.body.innerText.includes('completed'), { timeout: 10000 });
    const body = await page.evaluate(() => document.body.innerText);
    if (!body.includes('Result Data:')) throw new Error('Result Data section not shown');
    if (!body.includes('Browser E2E notes ' + unique)) throw new Error('saved notes not displayed');
    await page.waitForFunction(() =>
      document.querySelectorAll('.form-input:disabled, .form-textarea:disabled').length >= 1, { timeout: 10000 });
    const readOnlyAgain = await page.evaluate(() =>
      document.querySelectorAll('.form-input:disabled, .form-textarea:disabled').length);
    if (!readOnlyAgain) throw new Error('form not read-only after completion');
    const prefilled = await page.evaluate((uniq) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => labels.find((x) => x.textContent.startsWith(t)).closest('.form-group');
      const notes = find('Notes').querySelector('textarea, input');
      const amount = find('Amount').querySelector('input[type=number]');
      return { notes: notes.value, amount: amount.value };
    }, unique);
    if (!prefilled.notes.includes('Browser E2E notes ' + unique)) throw new Error('notes not prefilled read-only: ' + prefilled.notes);
    if (prefilled.amount !== '123') throw new Error('amount not prefilled read-only: ' + prefilled.amount);
    await page.close();
  });

  // ---------- Part C: portal entry form modal (regression: "Loading form fields..." hang) ----------
  await api('PUT', '/workflows/' + wf.id, adminToken, {
    environment: 'production',
    is_published: true,
    is_active: true,
    portal_visible: true,
    entry_form_id: form.id,
  });

  await step('C1: portal entry form modal renders fields instead of hanging', async () => {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((name) => document.body.innerText.includes(name), { timeout: 10000 }, wf.name);

    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      const btn = card.querySelector('button');
      btn.click();
    }, wf.name);

    await waitForText(page, form.name);
    await waitForText(page, 'Approved');
    await waitForText(page, 'Notes');
    const hung = await page.evaluate(() => document.body.innerText.includes('Loading form fields...'));
    if (hung) throw new Error('modal still shows "Loading form fields..."');
    await page.close();
  });

  await step('C2: submit portal entry form starts the workflow', async () => {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((name) => document.body.innerText.includes(name), { timeout: 10000 }, wf.name);

    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      card.querySelector('button').click();
    }, wf.name);
    await waitForText(page, 'Approved');

    await page.evaluate((uniq) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => labels.find((x) => x.textContent.startsWith(t)).closest('.form-group');
      const notes = find('Notes').querySelector('input');
      const approved = find('Approved').querySelector('input[type=checkbox]');
      const nSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nSet.call(notes, 'Portal notes ' + uniq);
      notes.dispatchEvent(new Event('input', { bubbles: true }));
      approved.click();
    }, unique);

    await page.evaluate(() => {
      const overlay = [...document.querySelectorAll('div[style*="position: fixed"]')]
        .find((el) => el.textContent.includes('Start Workflow'));
      const btn = [...overlay.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Start Workflow');
      btn.click();
    });

    // Toast confirms the run started
    await page.waitForFunction(() => document.body.innerText.includes('Started'), { timeout: 10000 });
    const body = await page.evaluate(() => document.body.innerText);
    if (!body.includes('Started')) throw new Error('no started toast');
    await page.close();
  });

  // ---------- Part C2: builder layout (columns) is honored ----------
  const layoutForm = await api('POST', '/forms', adminToken, undefined, {
    name: 'E2E Layout ' + unique,
    schema: JSON.stringify({
      type: 'object',
      title: 'Layout Form',
      columns: 2,
      properties: {
        left: { type: 'string', title: 'Left Field', column: 0 },
        right: { type: 'string', title: 'Right Field', column: 1 },
      },
      required: [],
    }),
  });
  const wf3 = await api('POST', '/workflows/', adminToken, {
    name: 'E2E Layout WF ' + unique,
    steps: [{ step_type: 'delay', definition: { seconds: 0 } }],
  });
  await api('PUT', '/workflows/' + wf3.id, adminToken, {
    environment: 'production',
    is_published: true,
    is_active: true,
    portal_visible: true,
    entry_form_id: layoutForm.id,
  });

  await step('C3: entry form honors 2-column builder layout', async () => {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((name) => document.body.innerText.includes(name), { timeout: 10000 }, wf3.name);

    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      card.querySelector('button').click();
    }, wf3.name);

    await waitForText(page, 'Left Field');
    await waitForText(page, 'Right Field');

    const layout = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => labels.find((x) => x.textContent.includes(t));
      const left = find('Left Field').getBoundingClientRect();
      const right = find('Right Field').getBoundingClientRect();
      return { leftX: left.x, rightX: right.x, leftY: left.y, rightY: right.y };
    });
    // In a 2-column layout the fields sit side by side (different x, same row)
    if (Math.abs(layout.leftX - layout.rightX) < 20) {
      throw new Error('fields not side by side: ' + JSON.stringify(layout));
    }
    if (Math.abs(layout.leftY - layout.rightY) > 10) {
      throw new Error('fields not on the same row: ' + JSON.stringify(layout));
    }
    await page.close();
  });

  // ---------- Part D: entry data prefills later human-task forms ----------
  const chainForm = await api('POST', '/forms', adminToken, undefined, {
    name: 'E2E Chain ' + unique,
    schema: JSON.stringify(FORM_SCHEMA),
  });
  const wf4 = await api('POST', '/workflows/', adminToken, {
    name: 'E2E Chain WF ' + unique,
    steps: [
      { step_type: 'human_task', definition: { assigned_to_user_id: me.id, assigned_group_id: null, form_id: chainForm.id, description: 'First review' } },
      { step_type: 'human_task', definition: { assigned_to_user_id: me.id, assigned_group_id: null, form_id: chainForm.id, description: 'Second review' } },
    ],
  });
  await api('PUT', '/workflows/' + wf4.id, adminToken, {
    environment: 'production',
    is_published: true,
    is_active: true,
    portal_visible: true,
    entry_form_id: chainForm.id,
  });

  async function readFormValues(page) {
    return page.evaluate(() => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => {
        const l = labels.find((x) => x.textContent.startsWith(t));
        return l ? l.closest('.form-group') : null;
      };
      const notes = find('Notes').querySelector('textarea, input');
      const amount = find('Amount').querySelector('input[type=number]');
      const approved = find('Approved').querySelector('input[type=checkbox]');
      return { notes: notes.value, amount: amount.value, approved: approved.checked };
    });
  }

  async function takeAndCompleteTask(taskId, notesText) {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/tasks/' + taskId, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Take Task');
    await page.evaluate(() => {
      [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Take Task').click();
    });
    await waitForNoText(page, 'Take Task');
    await sleep(600);
    const filled = await page.evaluate((txt) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => labels.find((x) => x.textContent.startsWith(t)).closest('.form-group');
      const notes = find('Notes').querySelector('textarea, input');
      const amount = find('Amount').querySelector('input[type=number]');
      const nSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nSet.call(notes, txt);
      notes.dispatchEvent(new Event('input', { bubbles: true }));
      nSet.call(amount, '100');
      amount.dispatchEvent(new Event('input', { bubbles: true }));
    }, notesText);
    await sleep(300);
    await page.evaluate(() => {
      [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Complete Task & Save Data').click();
    });
    await page.waitForFunction(() => document.body.innerText.includes('completed'), { timeout: 10000 });
    await page.close();
  }

  async function waitForOpenTask(runId) {
    for (let i = 0; i < 40; i++) {
      const res = await api('GET', '/tasks?workflow_run_id=' + runId, adminToken);
      const open = (res.tasks || []).find((t) => t.status === 'open');
      if (open) return open;
      await sleep(500);
    }
    throw new Error('no open task created for run ' + runId);
  }

  let chainRunId;

  await step('D1: first staff task is prefilled from the portal entry', async () => {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((name) => document.body.innerText.includes(name), { timeout: 10000 }, wf4.name);
    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      card.querySelector('button').click();
    }, wf4.name);
    await waitForText(page, 'Approved');
    await page.evaluate((uniq) => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => labels.find((x) => x.textContent.startsWith(t)).closest('.form-group');
      const notes = find('Notes').querySelector('input');
      const approved = find('Approved').querySelector('input[type=checkbox]');
      const nSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nSet.call(notes, 'Portal entry ' + uniq);
      notes.dispatchEvent(new Event('input', { bubbles: true }));
      approved.click();
    }, unique);
    await sleep(300);
    await page.evaluate(() => {
      const overlay = [...document.querySelectorAll('div[style*="position: fixed"]')]
        .find((el) => el.textContent.includes('Start Workflow'));
      const btn = [...overlay.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Start Workflow');
      btn.click();
    });
    await page.waitForFunction(() => document.body.innerText.includes('Started'), { timeout: 10000 });
    await page.close();

    for (let i = 0; i < 20; i++) {
      const runs = await api('GET', '/admin/runs?workflow_id=' + wf4.id, adminToken);
      if (runs && runs.length) { chainRunId = runs[0].id; break; }
      await sleep(300);
    }
    if (!chainRunId) throw new Error('no run found for chain workflow');
    const t1 = await waitForOpenTask(chainRunId);
    const { page: p2 } = await newPage(browser);
    await login(p2, 'user', 'user');
    await p2.goto(BASE + '/tasks/' + t1.id, { waitUntil: 'networkidle0' });
    await waitForText(p2, 'Take Task');
    const pre = await readFormValues(p2);
    if (!pre.notes.includes('Portal entry ' + unique)) throw new Error('task1 not prefilled from entry: ' + JSON.stringify(pre));
    if (!pre.approved) throw new Error('task1 approved not prefilled from entry');
    await p2.close();

    await takeAndCompleteTask(t1.id, 'Staff decision ' + unique);
  });

  await step('D2: second staff task prefilled from first task result', async () => {
    const t2 = await waitForOpenTask(chainRunId);
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto(BASE + '/tasks/' + t2.id, { waitUntil: 'networkidle0' });
    await waitForText(page, 'Take Task');
    const pre = await readFormValues(page);
    if (!pre.notes.includes('Staff decision ' + unique)) throw new Error('task2 not prefilled from task1 result: ' + JSON.stringify(pre));
    if (pre.amount !== '100') throw new Error('task2 amount not prefilled: ' + JSON.stringify(pre));
    await page.close();

    await takeAndCompleteTask(t2.id, 'Final ' + unique);
  });

  await browser.disconnect();

  console.log('\nRESULT: ' + passed.length + ' passed, ' + failed.length + ' failed');
  if (failed.length) process.exit(1);
})().catch((e) => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
