import type { FullConfig } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

/** Remove only this run's ownership-verified database after the suite. */
export default async function globalTeardown(config: FullConfig) {
  execFileSync(process.env.E2E_PYTHON || 'python3', [join(config.rootDir, 'database.py'), 'drop'], { stdio: 'inherit' });
}
