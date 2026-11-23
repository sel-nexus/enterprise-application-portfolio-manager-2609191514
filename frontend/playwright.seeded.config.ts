import { defineConfig } from '@playwright/test';
import base from './playwright.config';

// From frontend, set E2E_EMAIL, distinct E2E_TEMP_PASSWORD/E2E_NEW_PASSWORD,
// and optionally E2E_PYTHON/MONGODB_TEST_URI as in the root README. Run:
// node node_modules/@playwright/test/cli.js test -c playwright.seeded.config.ts
// Use a disposable MongoDB deployment; never run concurrently with the default suite.
export default defineConfig({
  ...base,
  testIgnore: [],
  testMatch: 'seeded-estate.spec.ts',
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'off', screenshot: 'off', video: 'off' },
  reporter: [['json', { outputFile: 'e2e-seeded-results.json' }], ['list']],
  webServer: [
    { command: `${JSON.stringify(process.env.E2E_PYTHON || 'python3')} e2e/start-api.py`, url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false, timeout: 120_000, gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 }, env: { E2E_SEEDED_ESTATE: 'true' } },
    { command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort', url: 'http://127.0.0.1:5173', reuseExistingServer: false, timeout: 120_000, env: { API_PROXY_TARGET: 'http://127.0.0.1:8000', VITE_API_BASE_URL: '' } },
  ],
});
