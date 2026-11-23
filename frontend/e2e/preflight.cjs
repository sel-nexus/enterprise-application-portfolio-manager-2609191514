const { chromium } = require('@playwright/test');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    await page.goto('http://127.0.0.1:5173/');
    await page.getByLabel('Email').fill(process.env.E2E_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_TEMP_PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForTimeout(1000);
    const accessibility = page.accessibility ? await page.accessibility.snapshot() : await page.locator('body').ariaSnapshot();
    const styles = await page.evaluate(() => ({ font: getComputedStyle(document.body).fontFamily, background: getComputedStyle(document.body).backgroundColor }));
    results.push({ viewport, accessibility, styles, html: await page.content() });
    await page.screenshot({ path: `preflight-${viewport.width}.png`, fullPage: true });
    await page.close();
  }
  fs.writeFileSync('preflight.txt', JSON.stringify(results, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
