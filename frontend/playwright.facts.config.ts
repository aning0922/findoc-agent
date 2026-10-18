import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: ['financial-persistence*.spec.ts', 'financial-review*.spec.ts'], workers: 1, retries: 0, timeout: 90_000,
  reporter: [['line'], ['json', { outputFile: process.env.FINDOC_D10_REPORT_FILE || '../product/validation/d10-browser-results.json' }]],
  outputDir: 'test-results/d10',
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:14175', trace: 'retain-on-failure' },
})
