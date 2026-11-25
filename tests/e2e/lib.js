'use strict';
const http = require('http');

const BASE = process.env.E2E_BASE || 'http://localhost:3000';
const CDP_ENDPOINT = process.env.E2E_CDP || 'http://127.0.0.1:9222/json/version';

function getWsEndpoint() {
  return new Promise((resolve, reject) => {
    http.get(CDP_ENDPOINT, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        try {
          resolve(JSON.parse(data).webSocketDebuggerUrl);
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

async function connect() {
  const puppeteer = require('puppeteer-core');
  const ws = await getWsEndpoint();
  return puppeteer.connect({
    browserWSEndpoint: ws,
    defaultViewport: { width: 1400, height: 900 },
  });
}

async function newPage(browser) {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('CONSOLE: ' + m.text());
  });
  return { page, errors };
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function login(page, username, password) {
  await page.goto(BASE + '/login', { waitUntil: 'networkidle0' });
  await page.evaluate(() => localStorage.clear());
  await page.goto(BASE + '/login', { waitUntil: 'networkidle0' });
  await page.waitForSelector('input[type=text]', { timeout: 8000 });
  await page.type('input[type=text]', username);
  await page.type('input[type=password]', password);
  await page.click('button[type=submit]');
  await sleep(2500);
}

function request(method, path, opts = {}) {
  return new Promise((resolve, reject) => {
    const headers = {};
    if (opts.token) headers.Authorization = 'Bearer ' + opts.token;
    if (opts.form) headers['Content-Type'] = 'application/x-www-form-urlencoded';
    else if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    const req = http.request(BASE + path, { method, headers }, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        let parsed = null;
        try {
          parsed = data ? JSON.parse(data) : null;
        } catch (_) {
          parsed = data;
        }
        resolve({ status: res.statusCode, body: parsed });
      });
    });
    req.on('error', reject);
    if (opts.form) req.write(opts.form);
    else if (opts.body !== undefined) req.write(JSON.stringify(opts.body));
    req.end();
  });
}

// Fixture credentials (README): username===password per role by default.
// Override in environments where dev-DB passwords drifted, e.g. E2E_ADMIN_PASS.
function creds(name) {
  const key = String(name).toUpperCase();
  return [
    process.env['E2E_' + key + '_USER'] || name,
    process.env['E2E_' + key + '_PASS'] || name,
  ];
}

async function apiLogin(username, password) {
  const res = await request('POST', '/api/auth/login', {
    form: 'username=' + encodeURIComponent(username) + '&password=' + encodeURIComponent(password),
  });
  if (res.status !== 200 || !res.body || !res.body.access_token) {
    throw new Error('apiLogin failed: ' + res.status + ' ' + JSON.stringify(res.body));
  }
  return res.body.access_token;
}

module.exports = { BASE, getWsEndpoint, connect, newPage, login, sleep, request, apiLogin, creds };
