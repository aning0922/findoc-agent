import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: 'd30-live-readonly.spec.ts', workers: 1, retries: 0,
  timeout: 60000,
  outputDir: process.env.D30_LIVE_OUT + '/traces',
  reporter: [['line'], ['json', { outputFile: process.env.D30_LIVE_OUT + '/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:14280', trace: 'retain-on-failure', viewport: { width: 1440, height: 1000 } },
});
