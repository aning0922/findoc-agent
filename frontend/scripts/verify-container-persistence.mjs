/**
 * 在已启动的独立受控 Compose 项目中验证浏览器创建与更换容器后读回。
 * 输入：本机 18081 入口及现有 C1 测试装配；输出：JSON 证据与合成结果截图。
 * 会替换精确识别的受控项目容器，但不删除卷、不访问真实模型或真实业务卷。
 */
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'
import { chromium } from '@playwright/test'

const runFile = promisify(execFile)
const projectRoot = fileURLToPath(new URL('../../', import.meta.url))
const evidenceRoot = new URL('../../artifacts/container-runtime/', import.meta.url)
const composeArgs = ['compose', '--env-file', '/dev/null', '-f', 'compose.controlled.yaml']

async function containerIdentity(service) {
  // 只记录所需身份和挂载，绝不输出 docker inspect 中的完整环境变量。
  const name = `findoc-d1-controlled-${service}-1`
  const { stdout } = await runFile('docker', ['inspect', name], { cwd: projectRoot })
  const [info] = JSON.parse(stdout)
  assert.equal(info.Config.Labels['com.docker.compose.project'], 'findoc-d1-controlled')
  assert.equal(info.Config.Labels['com.docker.compose.service'], service)
  return {
    id: info.Id,
    image: info.Image,
    volumes: info.Mounts.filter((mount) => mount.Type === 'volume')
      .map((mount) => ({ name: mount.Name, destination: mount.Destination })),
  }
}

await mkdir(evidenceRoot, { recursive: true })
const before = { api: await containerIdentity('api'), web: await containerIdentity('web') }
assert.deepEqual(before.api.volumes, [{
  name: 'findoc-d1-controlled_controlled-runtime-data', destination: '/var/lib/findoc',
}])
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  let postCount = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/agent/runs') {
      postCount += 1
    }
  })
  await page.goto('http://127.0.0.1:18081/')
  await page.getByRole('radio', { name: /controlled-synthetic-finance.pdf/ }).check()
  await page.getByRole('button', { name: 'Agent 有限任务' }).click()
  await page.getByLabel('年份').fill('2025')
  await page.getByLabel('指标').selectOption('营业收入')
  const createdResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/agent/runs')
  await page.getByRole('button', { name: '创建并执行 Agent Run' }).click()
  const createdResponse = await createdResponsePromise
  assert.equal(createdResponse.status(), 201)
  const created = await createdResponse.json()
  assert.equal(created.user_result.status, 'answered')
  await page.locator('.result-card').getByText('answered', { exact: true }).waitFor()
  assert.match(await page.locator('.result-card').innerText(), /120万元/)
  const resultUrl = `http://127.0.0.1:18081/api/agent/runs/${created.run_id}`
  const eventsBeforeResponse = await page.request.get(`${resultUrl}/events`)
  assert.equal(eventsBeforeResponse.status(), 200)
  const eventsBefore = await eventsBeforeResponse.json()
  console.log('Browser POST created answered Run:', created.run_id)

  // 同时重建 web，使 Nginx 在启动时重新解析新 API 容器地址。
  // --force-recreate 替换容器；不使用 down -v，因此原业务卷继续保留。
  const recreated = await runFile('docker', [...composeArgs,
    'up', '-d', '--no-build', '--pull', 'never', '--force-recreate',
    '--wait', '--wait-timeout', '90'], { cwd: projectRoot, timeout: 120_000 })
  process.stdout.write(recreated.stdout)
  process.stdout.write(recreated.stderr)
  const after = { api: await containerIdentity('api'), web: await containerIdentity('web') }
  assert.notEqual(after.api.id, before.api.id)
  assert.notEqual(after.web.id, before.web.id)
  assert.equal(after.api.image, before.api.image)
  assert.deepEqual(after.api.volumes, before.api.volumes)

  // 同一浏览器保留已知 Run 身份；刷新后必须 GET 旧结果，不能再次 POST。
  const restoredResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'GET' && response.url() === resultUrl)
  await page.reload()
  const restoredResponse = await restoredResponsePromise
  assert.equal(restoredResponse.status(), 200)
  const restored = await restoredResponse.json()
  assert.deepEqual(restored, created)
  await page.locator('.result-card').getByText('answered', { exact: true }).waitFor()
  assert.match(await page.locator('.result-card').innerText(), /120万元/)
  assert.ok((await page.locator('.result-card').innerText()).includes(created.run_id))
  const eventsAfterResponse = await page.request.get(`${resultUrl}/events`)
  assert.equal(eventsAfterResponse.status(), 200)
  assert.deepEqual(await eventsAfterResponse.json(), eventsBefore)
  assert.equal(postCount, 1)
  await page.screenshot({ path: fileURLToPath(new URL('controlled-restored.png', evidenceRoot)), fullPage: true })
  await writeFile(new URL('controlled-run.json', evidenceRoot), JSON.stringify({
    observed_at_utc: new Date().toISOString(), before, after,
    browser_post_count: postCount, created, restored, events: eventsBefore,
    boundary: 'Real browser/Nginx/HTTP/business/SQLite; fake embedding/store/provider; seeded document is not ingestion evidence.',
  }, null, 2) + '\n')
  console.log('PASS: containers replaced, same volume, same Run/result/events, browser POST count = 1')
} finally {
  await browser.close()
}
