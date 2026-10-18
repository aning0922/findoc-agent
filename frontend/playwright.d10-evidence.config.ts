import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: 'evidence*.spec.ts', workers: 1, retries: 0, timeout: 60_000,
  reporter: [['line'], ['json', { outputFile: '../product/validation/d10-legacy-evidence-browser-results.json' }]],
  outputDir: 'test-results/d10-evidence',
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:14174', trace: 'retain-on-failure' },
})
