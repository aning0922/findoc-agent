import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: 'd30-public-demo.spec.ts', workers: 1, retries: 0,
  timeout: 30000,
  outputDir: process.env.D30_PUBLIC_OUT + '/traces',
  reporter: [['line'], ['json', { outputFile: process.env.D30_PUBLIC_OUT + '/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:14290', trace: 'retain-on-failure' },
});
