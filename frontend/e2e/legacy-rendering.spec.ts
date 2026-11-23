import { expect, test } from './fixtures';

test('legacy stored markup is rendered as text and does not execute', async ({ page, request, admin }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const payload = '<img src=x onerror="window.__legacyPayloadExecuted=true">';
  const login = await request.post('/api/v1/accounts/login', { data: { email: admin.email, password: admin.password } });
  expect(login.status()).toBe(200);
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const list = await request.get('/api/v1/applications', { headers, params: { search: 'zz E2E legacy application' } });
  expect(list.status()).toBe(200);
  const items = (await list.json()).items;
  expect(items).toHaveLength(1);
  expect(items[0].description).toBe(payload);
  await page.goto('/');
  await page.getByLabel('Email').fill(admin.email);
  await page.getByLabel('Password', { exact: true }).fill(admin.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await page.getByLabel('Search name or business owner').fill('zz E2E legacy application');
  await page.getByRole('link', { name: 'zz E2E legacy application', exact: true }).click();
  const header = page.locator('header.application-record-header');
  await expect(header.getByText(payload, { exact: true })).toBeVisible();
  await expect(header.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __legacyPayloadExecuted?: boolean }).__legacyPayloadExecuted)).toBeUndefined();
  expect(errors).toEqual([]);
});
