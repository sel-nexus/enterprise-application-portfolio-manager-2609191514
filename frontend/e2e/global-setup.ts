import { expect, request } from '@playwright/test';
import type { FullConfig } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

/** Initialize only the bootstrap provisioner in the fresh E2E database. */
export default async function globalSetup(config: FullConfig) {
  const email = process.env.E2E_EMAIL;
  const temporary = process.env.E2E_TEMP_PASSWORD;
  const password = process.env.E2E_NEW_PASSWORD;
  if (!email || !temporary || !password || temporary === password) {
    throw new Error('Set E2E_EMAIL and distinct E2E_TEMP_PASSWORD and E2E_NEW_PASSWORD.');
  }
  const api = await request.newContext({ baseURL: 'http://127.0.0.1:5173' });
  try {
    const login = await api.post('/api/v1/accounts/login', { data: { email, password: temporary } });
    expect(login.status(), 'bootstrap login').toBe(200);
    const setup = await login.json();
    expect(setup.must_change_password).toBe(true);
    const changed = await api.put('/api/v1/accounts/password', {
      headers: { Authorization: `Bearer ${setup.access_token}` },
      data: { current_password: temporary, new_password: password, confirm_password: password },
    });
    expect(changed.status(), 'bootstrap password setup').toBe(200);
    expect((await changed.json()).must_change_password).toBe(false);
    execFileSync(process.env.E2E_PYTHON || 'python3', [join(config.rootDir, 'database.py'), 'checkpoint'], { stdio: 'inherit' });
  } finally {
    await api.dispose();
  }
}
