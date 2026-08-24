# E2E tests (puppeteer-core + external Chromium over CDP)

Non-destructive UI regression tests for the frontend. They drive a browser over
CDP (no bundled Chromium download) from a tiny node container.

## Prerequisites

1. Stack is up: `docker compose up -d`.
2. A Chromium/Chrome running with remote debugging on `127.0.0.1:9222`, e.g.:
   ```
   google-chrome --headless --no-sandbox --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-e2e about:blank
   ```
3. Known-good fixtures used by the tests:
   - workflow **22** ("Test WF") exists (designer edge/end-node test);
   - logins `admin/admin`, `dev/dev`, `staff/staff`, `user/user` exist.

## Run

```
bash tests/e2e/run-e2e.sh            # runs smoke.js + designer-save.js
bash tests/e2e/run-e2e.sh smoke.js   # run one test
make test-e2e                        # same as the full run
```

Env overrides: `E2E_BASE` (default `http://localhost:3000`), `E2E_CDP`
(default `http://127.0.0.1:9222/json/version`).

## Tests

- `smoke.js` — read-only regression: role-based post-login routing for all four
  roles, branding in the app shell, workflows list, designer 22 edge rendering +
  stable end node during drag + edges after reload, and the Settings "clear
  System Name" blanking bug. Never mutates the database.
- `designer-save.js` — creates a **disposable** workflow via the API, exercises
  staged Save (add output A→B, persist, survive reload) and Cancel-with-dirty
  (confirm dialog, leaves designer), then deletes the workflow. Safe to run
  repeatedly.

## Adding a test

Write a script that `require('./lib')` (helpers: `connect`, `newPage`, `login`,
`apiLogin`, `request`) and `process.exit(1)` on failure. It will be picked up by
`run-e2e.sh` when named explicitly, or added to the default list.

## Writing ad-hoc probes (gotchas)

- **Always run scripts through `run-e2e.sh`, not `node <script>` directly.**
  The image installs `puppeteer-core` into `/work/node_modules`; run-e2e.sh
  passes `-e NODE_PATH=/work/node_modules` so `require('./lib')` resolves.
  Running on the host or a plain `docker run` without NODE_PATH fails with
  `Cannot find module 'puppeteer-core'`.
- **`creds(role)` returns an array `[user, pass]`, keyed by env vars
  `E2E_<ROLE>_USER` / `E2E_<ROLE>_PASS`** (defaults to the role name for
  both). Destructure it: `const [user, pass] = creds('admin')`. Passing
  `creds.admin` (object-style) yields `undefined` credentials and confusing
  puppeteer errors like `text is not iterable`.
