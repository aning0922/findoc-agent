import { defineConfig, devices } from '@playwright/test'
import { isAbsolute } from 'node:path'


function readPort(name: string, fallback: number): number {
  /** 读取可覆盖端口；只接受不会让 Vite 静默漂移的有效 TCP 端口。 */
  const rawValue = process.env[name]
  if (rawValue === undefined) return fallback
  const value = Number(rawValue)
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error(`${name} 必须是 1—65535 的整数`)
  }
  return value
}

const runtimeRoot = process.env.FINDOC_CONTROLLED_RUNTIME_ROOT
if (runtimeRoot === undefined || !isAbsolute(runtimeRoot)) {
  throw new Error('FINDOC_CONTROLLED_RUNTIME_ROOT 必须由 E2E 启动脚本设置为绝对临时目录')
}

const apiPort = readPort('FINDOC_E2E_API_PORT', 18080)
const webPort = readPort('FINDOC_E2E_WEB_PORT', 14173)
const apiOrigin = `http://127.0.0.1:${apiPort}`
const webOrigin = `http://127.0.0.1:${webPort}`
const pythonExecutable = process.env.FINDOC_E2E_PYTHON ?? '.venv/bin/python'
// webServer 接受命令字符串，因此覆盖值只允许无空白、无 shell 元字符的路径。
if (!/^[A-Za-z0-9_./-]+$/.test(pythonExecutable)) {
  throw new Error('FINDOC_E2E_PYTHON 必须是简单的 Python 可执行文件路径')
}

const testEnvironment = { ...process.env }
for (const name of Object.keys(testEnvironment)) {
  if (name.startsWith('LLM_') || name === 'OPENAI_API_KEY') {
    delete testEnvironment[name]
  }
}

export default defineConfig({
  testDir: './e2e',
  testMatch: 'agent*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results/legacy',
  use: {
    baseURL: webOrigin,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      name: 'controlled-api',
      cwd: '..',
      command: [
        `${pythonExecutable} -m uvicorn`,
        'tests.support.controlled_agent_app:create_controlled_agent_app_from_env',
        '--factory',
        '--host 127.0.0.1',
        `--port ${apiPort}`,
      ].join(' '),
      env: {
        ...testEnvironment,
        FINDOC_CONTROLLED_RUNTIME_ROOT: runtimeRoot,
      },
      url: `${apiOrigin}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      gracefulShutdown: { signal: 'SIGTERM', timeout: 2_000 },
    },
    {
      name: 'vite',
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      env: {
        ...testEnvironment,
        FINDOC_API_ORIGIN: apiOrigin,
        FINDOC_E2E_DISABLE_ENV_FILES: '1',
      },
      url: webOrigin,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      gracefulShutdown: { signal: 'SIGTERM', timeout: 2_000 },
    },
  ],
})
