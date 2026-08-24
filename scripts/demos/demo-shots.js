'use strict';
// Visual demo: open the 4-column entry form in the portal, fill + submit it,
// then show the staff review task prefilled from the entry data (pass-through).
const { connect, newPage, login, sleep } = require('/e2e/lib.js');
const fs = require('fs');
const OUT = process.env.SHOT_DIR || '/shots';

const WORKFLOW = 'Demo: 4-Column Intake with Review';

(async () => {
  const browser = await connect();

  // ---- Submitter: open the entry form modal in the portal ----
  {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto('http://localhost:9000/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((n) => document.body.innerText.includes(n), { timeout: 10000 }, WORKFLOW);
    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      card.querySelector('button').click();
    }, WORKFLOW);
    await sleep(1500);
    await page.evaluate(() => {
      const modal = document.querySelector('.card');
      modal && modal.scrollIntoView({ block: 'center' });
    });
    await sleep(500);
    await page.screenshot({ path: `${OUT}/01-entry-form-modal.png` });
    await page.close();
  }

  // ---- Submitter: fill the form and submit (starts the workflow) ----
  let runId = null;
  {
    const { page } = await newPage(browser);
    await login(page, 'user', 'user');
    await page.goto('http://localhost:9000/portal', { waitUntil: 'networkidle0' });
    await page.waitForFunction((n) => document.body.innerText.includes(n), { timeout: 10000 }, WORKFLOW);
    await page.evaluate((name) => {
      const cards = [...document.querySelectorAll('.stat-card')];
      const card = cards.find((c) => c.textContent.includes(name));
      card.querySelector('button').click();
    }, WORKFLOW);
    await sleep(1200);

    await page.evaluate(() => {
      const labels = [...document.querySelectorAll('.form-label')];
      const find = (t) => {
        const l = labels.find((x) => x.textContent.startsWith(t));
        return l ? l.closest('.form-group') : null;
      };
      const setInput = (name, value) => {
        const group = find(name);
        if (!group) throw new Error('NO GROUP for ' + name);
        const el = group.querySelector('input, select, textarea');
        if (!el) throw new Error('NO CONTROL for ' + name + ' (' + group.outerHTML.slice(0, 80) + ')');
        if (el.tagName === 'SELECT') {
          el.value = value;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
          const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
          setter.call(el, value);
          el.dispatchEvent(new Event('input', { bubbles: true }));
        }
      };
      setInput('First Name', 'Alice');
      setInput('Last Name', 'Johnson');
      setInput('Email', 'alice.j@example.com');
      setInput('Phone', '555-0100');
      setInput('Department', 'IT');
      setInput('Request Type', 'New Request');
      setInput('Priority', 'High');
      setInput('Amount', '2500');
      setInput('Details / Notes', 'Need a new laptop for onboarding.');
    });
    await sleep(400);
    await page.screenshot({ path: `${OUT}/02-entry-form-filled.png` });

    await page.evaluate(() => {
      const overlay = document.querySelector('div[style*="position: fixed"]');
      const btn = [...overlay.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Start Workflow');
      btn.click();
    });
    await sleep(2500);
    await page.screenshot({ path: `${OUT}/03-after-submit.png` });
    await page.close();
  }

  // ---- Staff: open the review task, prefilled from the entry form ----
  {
    const { page } = await newPage(browser);
    await login(page, 'staff', 'staff');
    await page.goto('http://localhost:9000/tasks', { waitUntil: 'networkidle0' });
    await sleep(2500);
    await page.evaluate((n) => {
      const links = [...document.querySelectorAll('a')];
      const l = links.find((x) => x.textContent.includes(n));
      if (l) l.click();
    }, 'Review Intake');
    await sleep(2500);
    await page.screenshot({ path: `${OUT}/04-staff-task-prefilled.png` });
    await page.close();
  }

  console.log('DONE');
  await browser.close();
})().catch((e) => { console.error('ERROR', e); process.exit(1); });
