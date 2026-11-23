import { expect, test } from './fixtures';

test('administrator creates and deactivates a user and sees the audit event', async ({ page, admin }) => {
  const { email, password, temporary } = admin;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const name = `00 Test Person ${Date.now()}`;
  const userEmail = `test-${Date.now()}@example.com`;
  await page.goto('/');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Administration' }).click();
  await page.getByRole('button', { name: 'New user' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name', { exact: true }).fill(name);
  await dialog.getByLabel('Email').fill(userEmail);
  await dialog.getByLabel('Temporary password').fill(temporary);
  await dialog.getByRole('button', { name: 'Save' }).click();
  const row = page.getByRole('row').filter({ hasText: userEmail });
  await expect(row).toContainText('Active');
  page.once('dialog', dialog => dialog.accept());
  await row.getByRole('button', { name: 'Deactivate' }).click();
  await expect(row).toContainText('Inactive');
  await page.getByRole('button', { name: 'Audit', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: `Deactivated ${name}` })).toBeVisible();
  expect(errors).toEqual([]);
});
