import { expect, test as base } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

type TestAccount = { email: string; name: string; temporary: string; password: string };

type Fixtures = { admin: TestAccount; freshAdmin: TestAccount; isolation: void };

/** Provision a unique administrator through the real backend for each test. */
export const test = base.extend<Fixtures>({
  // Reset every collection to the bootstrap snapshot, including users, audit,
  // roles and interval. This also runs if test assertions or setup fail.
  isolation: [async ({}, use, testInfo) => {
    if (testInfo.config.workers !== 1) throw new Error('E2E database isolation requires exactly one worker.');
    const reset = () => execFileSync(process.env.E2E_PYTHON || 'python3', [join(testInfo.config.rootDir, 'database.py'), 'reset'], { stdio: 'inherit' });
    reset();
    try {
      await use();
    } finally {
      reset();
    }
  }, { auto: true, timeout: 60_000 }],
  freshAdmin: async ({ request, isolation }, use) => {
    const bootstrapEmail = process.env.E2E_EMAIL;
    const password = process.env.E2E_NEW_PASSWORD;
    const temporary = process.env.E2E_TEMP_PASSWORD;
    if (!bootstrapEmail || !password || !temporary) throw new Error('Set E2E_EMAIL, E2E_TEMP_PASSWORD and E2E_NEW_PASSWORD.');
    const login = await request.post('/api/v1/accounts/login', { data: { email: bootstrapEmail, password } });
    expect(login.status(), 'provisioner login').toBe(200);
    const session = await login.json();
    expect(session.must_change_password).toBe(false);
    const id = randomUUID();
    const account = { email: `e2e-${id}@example.com`, name: `E2E Admin ${id}`, temporary, password };
    const created = await request.post('/api/v1/admin/users', {
      headers: { Authorization: `Bearer ${session.access_token}` },
      data: { name: account.name, email: account.email, role: 'administrator', portfolio_ids: [], temporary_password: temporary },
    });
    expect(created.status(), 'create isolated administrator').toBe(201);
    await use(account);
  },
  admin: async ({ request, freshAdmin }, use) => {
    const login = await request.post('/api/v1/accounts/login', { data: { email: freshAdmin.email, password: freshAdmin.temporary } });
    expect(login.status(), 'fresh administrator login').toBe(200);
    const session = await login.json();
    expect(session.must_change_password).toBe(true);
    const changed = await request.put('/api/v1/accounts/password', {
      headers: { Authorization: `Bearer ${session.access_token}` },
      data: { current_password: freshAdmin.temporary, new_password: freshAdmin.password, confirm_password: freshAdmin.password },
    });
    expect(changed.status(), 'fresh administrator password setup').toBe(200);
    expect((await changed.json()).must_change_password).toBe(false);
    await use(freshAdmin);
  },
});
export { expect };
