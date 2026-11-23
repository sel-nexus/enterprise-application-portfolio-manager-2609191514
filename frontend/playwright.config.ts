import { defineConfig } from '@playwright/test';
import { randomBytes, randomUUID } from 'node:crypto';

// Each invocation owns exactly one database; never accept a caller-supplied name.
if (!process.env.TEST_WORKER_INDEX) {
  process.env.E2E_RUN_ID = randomUUID().replaceAll('-', '');
  process.env.E2E_DB_TOKEN = randomBytes(32).toString('hex');
}

export default defineConfig({
  testDir: './e2e',
  testIgnore: 'seeded-estate.spec.ts',
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', screenshot: 'on' },
  workers: 1,
  reporter: [['json', { outputFile: 'e2e-results.json' }], ['list']],
  webServer: [
    { command: `${JSON.stringify(process.env.E2E_PYTHON || 'python3')} e2e/start-api.py`, url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false, timeout: 120_000, gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 }, env: { E2E_SEEDED_ESTATE: 'false' } },
    { command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort', url: 'http://127.0.0.1:5173', reuseExistingServer: false, timeout: 120_000, env: { API_PROXY_TARGET: 'http://127.0.0.1:8000' } },
  ],
});
