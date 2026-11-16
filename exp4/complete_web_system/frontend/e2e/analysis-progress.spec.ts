import { expect, test, type Page } from '@playwright/test'

const file = { name: 'game.mp4', mimeType: 'video/mp4', buffer: Buffer.from('ui-test-video') }
const events = [{ t_ms: 0, type: 'player_count', text: '画面中检测到 7 名球员。', player_count: 7 }]

async function mockTask(page: Page) {
  const state = { status: 'running', stage: 'detecting', progress: 0, error: '' }
  let send = (_data: object) => {}
  await page.routeWebSocket('**/ws/task/**', socket => {
    send = data => socket.send(JSON.stringify(data))
  })
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    let result: unknown = state
    if (route.request().method() === 'POST') result = { task_id: 'test-task', status: 'pending' }
    else if (path.endsWith('/events')) result = events
    else if (path.endsWith('/detections')) result = []
    else if (path.endsWith('/tasks')) result = [{ ...state, task_id: 'test-task', video_name: 'game.mp4' }]
    return route.fulfill({ json: { code: 0, result, msg: 'ok' } })
  })
  return { state, send: (data: object) => send(data) }
}

test('upload opens progress immediately, follows real updates, then opens results', async ({ page }) => {
  const mock = await mockTask(page)
  let finishUpload!: () => void
  const uploading = new Promise<void>(resolve => { finishUpload = resolve })
  await page.route('**/api/v1/tasks', async route => {
    if (route.request().method() !== 'POST') return route.fallback()
    await uploading
    await route.fulfill({ status: 202, json: { code: 0, result: { task_id: 'test-task' }, msg: 'ok' } })
  })
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  const chooserPromise = page.waitForEvent('filechooser')
  await frame.locator('#uploadBtn').click()
  const chooser = await chooserPromise
  await expect(frame.getByRole('dialog')).toBeHidden()
  await chooser.setFiles(file)
  await expect(frame.getByRole('dialog', { name: '导入比赛视频' })).toBeVisible()
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.getByRole('dialog', { name: '正在分析中，请稍等' })).toBeVisible()
  await expect(frame.locator('#analysisDetail')).toHaveText('正在上传视频…')
  await expect(frame.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  finishUpload()
  await expect(frame.locator('#analysisDetail')).toHaveText('正在检测球员')
  mock.send({ type: 'progress', stage: 'detecting', progress: 0.46 })
  await expect(frame.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '46')
  mock.send({ type: 'progress', stage: 'queued', progress: 0 })
  await expect(frame.locator('#analysisPercent')).toHaveText('46%')
  await expect.poll(() => frame.locator('#analysisProgress').evaluate(el =>
    Math.round(el.firstElementChild!.getBoundingClientRect().width / el.getBoundingClientRect().width * 100),
  )).toBe(46)
  await expect(frame.locator('#analysisDetail')).toHaveText('正在检测球员')
  if (process.env.ANALYSIS_SCREENSHOTS) await page.screenshot({ path: `${process.env.ANALYSIS_SCREENSHOTS}/waiting-${test.info().project.name}.png` })
  mock.state.status = 'ready'; mock.state.stage = 'ready'; mock.state.progress = 1
  mock.send({ type: 'done' })
  await expect(frame.getByRole('dialog')).toBeHidden()
  await expect(frame.locator('#eventList')).toContainText(events[0]!.text)
  await expect(frame.locator('#videoStatus')).toHaveText('分析完成')
  await expect(frame.getByText('后端事件', { exact: true })).toHaveCount(0)
  await expect(frame.getByText('人数统计来自后端检测事件', { exact: true })).toHaveCount(0)
  await expect(frame.getByText('视频分析工作台 V3', { exact: true })).toHaveCount(0)
  await frame.getByRole('button', { name: '历史任务', exact: true }).click()
  await expect(frame.locator('#recentPage')).toBeVisible()
  await expect(frame.locator('#taskList')).toContainText('game.mp4')
})

test('polling updates the mobile waiting screen when WebSocket is unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const mock = await mockTask(page)
  await page.routeWebSocket('**/ws/task/**', socket => socket.close())
  mock.state.progress = 0.33
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '33')
  await expect.poll(() => frame.locator('#analysisProgress').evaluate(el =>
    Math.round(el.firstElementChild!.getBoundingClientRect().width / el.getBoundingClientRect().width * 100),
  )).toBe(33)
  const box = await frame.getByRole('dialog').boundingBox()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  if (process.env.ANALYSIS_SCREENSHOTS) await page.screenshot({ path: `${process.env.ANALYSIS_SCREENSHOTS}/mobile-${test.info().project.name}.png` })
  mock.state.status = 'ready'; mock.state.stage = 'ready'; mock.state.progress = 1
  await expect(frame.getByRole('dialog')).toBeHidden({ timeout: 8000 })
})

test('upload failure is visible and the same file can be uploaded again', async ({ page }) => {
  const mock = await mockTask(page)
  let first = true
  await page.route('**/api/v1/tasks', route => {
    if (route.request().method() === 'POST' && first) {
      first = false
      return route.fulfill({ status: 503, json: { code: 503, msg: '服务暂时不可用', result: null } })
    }
    return route.fallback()
  })
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.getByRole('dialog', { name: '上传失败，请重试' })).toBeVisible()
  await expect(frame.locator('#analysisDetail')).toHaveText('服务暂时不可用')
  await frame.getByRole('button', { name: '返回工作台', exact: true }).click()
  mock.state.progress = 0.25
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.getByRole('dialog', { name: '正在分析中，请稍等' })).toBeVisible()
  await expect(frame.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25')
})

test('completed task shows whole narration and answers with its task id', async ({ page }) => {
  const mock = await mockTask(page)
  mock.state.status = 'ready'; mock.state.stage = 'ready'; mock.state.progress = 1
  let askedTask = ''
  await page.route('**/api/v1/tasks/test-task/narration', route =>
    route.fulfill({ json: { code: 0, result: { status: 'ready', text: '球员疑似传球，随后移动方向变化。', sections: [] }, msg: 'ok' } }),
  )
  let audioRequested = false
  await page.route('**/api/v1/tasks/test-task/narration/audio', route => {
    audioRequested = true
    return route.fulfill({ status: 200, contentType: 'audio/mpeg', body: 'id3-fake-mp3' })
  })
  await page.route('**/api/v1/agent/chat', route => {
    askedTask = route.request().postDataJSON().message
    return route.fulfill({ json: { code: 0, result: { session_id: 'session-1', agent: '该任务出现疑似传球。', elapsed_ms: 120 }, msg: 'ok' } })
  })
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.locator('#narrationText')).toHaveText('球员疑似传球，随后移动方向变化。')
  await expect(frame.locator('#speakNarration')).toBeVisible()
  await frame.locator('#speakNarration').click()
  await expect.poll(() => audioRequested).toBe(true)
  await frame.locator('#taskQuestion').fill('开场发生了什么？')
  await frame.locator('#askTask').click()
  await expect(frame.locator('#taskAnswer')).toHaveText('该任务出现疑似传球。')
  expect(askedTask).toContain('test-task')
})

test('analysis failures show the actual error instead of an endless waiting screen', async ({ page }) => {
  const mock = await mockTask(page)
  mock.state.status = 'failed'; mock.state.stage = 'failed'; mock.state.error = '无法解码视频'
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.getByRole('dialog', { name: '分析失败', exact: true })).toBeVisible()
  await expect(frame.locator('#analysisDetail')).toHaveText('无法解码视频')
  await frame.getByRole('button', { name: '返回工作台', exact: true }).click()
  await expect(frame.getByRole('dialog')).toBeHidden()
  await expect(frame.locator('#videoStatus')).toHaveText('分析失败')
})

test('clearing a dismissed task ignores its late results and allows a new upload', async ({ page }) => {
  const mock = await mockTask(page)
  mock.state.status = 'ready'; mock.state.stage = 'ready'; mock.state.progress = 1
  let release!: () => void
  const oldResponse = new Promise<void>(resolve => { release = resolve })
  let started!: () => void
  const waiting = new Promise<void>(resolve => { started = resolve })
  let first = true, deletes = 0
  page.on('request', request => { if (request.method() === 'DELETE') deletes++ })
  await page.route('**/api/v1/tasks/test-task/events', async route => {
    if (!first) return route.fallback()
    first = false; started(); await oldResponse
    await route.fulfill({ json: { code: 0, result: [{ ...events[0], text: '旧任务事件' }], msg: 'ok' } })
  })
  await page.goto('/video-v3')
  const frame = page.frameLocator('iframe')
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await waiting
  await frame.getByRole('button', { name: '返回工作台', exact: true }).click()
  await frame.getByRole('button', { name: '清除当前任务', exact: true }).focus()
  await frame.getByRole('button', { name: '清除当前任务', exact: true }).press('Space')
  release()
  await expect(frame.locator('#video')).not.toHaveAttribute('src')
  await expect(frame.locator('#eventList .event-row')).toHaveCount(0)
  await frame.locator('#fileInput').setInputFiles(file)
  await frame.getByRole('button', { name: '确认分析' }).click()
  await expect(frame.locator('#eventList')).toContainText(events[0]!.text)
  await expect(frame.locator('#eventList')).not.toContainText('旧任务事件')
  await expect(frame.getByRole('dialog')).toBeHidden()
  expect(deletes).toBe(0)
})
