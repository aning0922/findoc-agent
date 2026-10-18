import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: 'financial-review*.spec.ts', workers: 1, retries: 0, timeout: 90_000,
  reporter: [['line'], ['json', { outputFile: '../product/validation/d9-browser-results.json' }]],
  outputDir: 'test-results/d9',
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:14175', trace: 'retain-on-failure' },
})
