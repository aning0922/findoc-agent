import { defineConfig } from '@playwright/test'
import { isAbsolute } from 'node:path'

const out = process.env.FINDOC_CONVERSATION_OUT
const origin = process.env.FINDOC_CONVERSATION_WEB_ORIGIN
if (!out || !isAbsolute(out) || !origin || !/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) {
  throw new Error('Use scripts/run_conversation_v12_e2e.py with an isolated output and loopback origin')
}

export default defineConfig({
  testDir: './e2e',
  testMatch: 'conversation*.spec.ts',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  timeout: 90_000,
  outputDir: `${out}/traces`,
  reporter: [['line'], ['json', { outputFile: `${out}/results.json` }]],
  use: {
    baseURL: origin,
    browserName: 'chromium',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
