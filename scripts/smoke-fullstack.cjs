// Optional local browser check: install Playwright under .local/browser-check first.
const { chromium } = require('../.local/browser-check/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const origin = process.env.FURSAH_SMOKE_ORIGIN || 'http://127.0.0.1:5173';
  const browser = await chromium.launch({ headless: true,
    ...(process.env.FURSAH_BROWSER_EXECUTABLE ? { executablePath: process.env.FURSAH_BROWSER_EXECUTABLE } : {}),
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('عمّ تبحث؟').fill('ورشة ترجمة المحتوى التعليمي');
    const pending = page.waitForResponse(response => response.url() === origin + '/api/v1/discover' && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'اكتشف الفرص', exact: true }).click();
    const response = await pending;
    const body = await response.json();
    assert.equal(response.status(), 503);
    assert.equal(body.error_code, 'FURSAH_NOT_IMPLEMENTED');
    assert.deepEqual(body.recommendations, []);
    assert.equal(response.request().postDataJSON().query, 'ورشة ترجمة المحتوى التعليمي');
    await page.getByRole('alert').getByText('مسار البحث أو التفاصيل لم يُنفّذ بعد.', { exact: false }).waitFor();
    assert.deepEqual(errors, []);
    const health = await page.request.get(origin + '/health');
    const ready = await page.request.get(origin + '/ready');
    assert.equal(health.status(), 200);
    assert.equal(ready.status(), 503);
    const output = path.resolve(__dirname, '../results');
    await fs.mkdir(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'fullstack-shell.png'), fullPage: true });
    const report = { generated_at: new Date().toISOString(), scope: 'Imported frontend and unfinished API shell; not recommendation acceptance testing',
      origin, frontend_rendered: true, same_origin_discovery_reached_backend: true,
      discovery_status: response.status(), error_code: body.error_code, expected_error_rendered: true,
      health_status: health.status(), readiness_status: ready.status(), uncaught_page_errors: errors,
    };
    await fs.writeFile(path.join(output, 'fullstack-smoke.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
