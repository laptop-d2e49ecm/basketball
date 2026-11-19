import { expect, test, type Page, type Route } from '@playwright/test'

const task = { task_id: 'video-test', video_name: 'game.mp4', status: 'running', stage: 'detecting', progress: .4, error: null, created_at: new Date(Date.now() - 15_000).toISOString(), finished_at: null, metadata: { expected_seconds: 120 }, frames_total: 100, frames_done: 40, avg_infer_ms: 40, total_seconds: 20 }
const event = { t_ms: 6000, type: 'action', source: 'action_model', text: '球员正在持球推进。', action: 'dribble', action_zh: '运球' }
const narration = { task_id: 'video-test', status: 'ready', text: '球员正在持球推进。', sections: [{ start_ms: 6000, end_ms: 9000, event_count: 1, text: '球员正在持球推进。' }] }

async function mockBackend(page: Page) {
  let phase = 'running'
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let result: unknown = null
    if (path === '/api/v1/tasks' && route.request().method() === 'POST') result = { task_id: task.task_id, status: 'pending', frame_step: 2 }
    else if (path === '/api/v1/tasks') result = [{ ...task, status: phase }]
    else if (path === `/api/v1/tasks/${task.task_id}`) result = { ...task, status: phase, stage: phase === 'ready' ? 'ready' : 'detecting', progress: phase === 'ready' ? 1 : .4 }
    else if (path.endsWith('/events')) result = [event, { type: 'player_count_change', t_ms: 0, player_count: 8, text: '检测到 8 人' }, { type: 'player_count_change', t_ms: 8000, player_count: 10, text: '检测到 10 人' }]
    else if (path.endsWith('/narration')) result = narration
    else if (path.endsWith('/preview/status')) result = { status: 'processing', converted: false, error: null }
    else if (path.endsWith('/detections')) result = []
    else if (path.endsWith('/agent/sessions')) result = []
    else if (path.endsWith('/agent/chat')) result = { session_id: 'sess_one', task_id: task.task_id, agent: '这段比赛中，球员正在持球推进。', tool_calls: [{ tool: 'query_video_events', args: { task_id: task.task_id }, status: 'ok', result_summary: '1 条', elapsed_ms: 2 }], elapsed_ms: 100, provider: 'test' }
    else if (path.endsWith('/frame')) return route.fulfill({ status: 404, body: '' })
    else return route.fulfill({ status: 404, json: { code: 404, result: null, msg: '不存在' } })
    await route.fulfill({ status: 200, json: { code: 0, result, msg: 'ok' } })
  })
  return { finish: () => { phase = 'ready' } }
}

test('video upload, waiting screen, analysis and task chat share one workspace', async ({ page }) => {
  const backend = await mockBackend(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '篮球视频分析' })).toBeVisible()
  if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/home.png`, fullPage: true })
  await expect(page.getByText('图文匹配')).toHaveCount(0)
  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(page.getByRole('button', { name: '确认分析' })).toBeDisabled()
  await page.locator('input[type=file]').setInputFiles({ name: 'game.mp4', mimeType: 'video/mp4', buffer: Buffer.from('test video') })
  await expect(page.getByRole('dialog', { name: '选择视频' })).toBeVisible()
  await expect(page.getByText('已选择 1 个视频')).toBeVisible()
  await page.getByRole('textbox', { name: '主队' }).fill('主队A')
  await page.getByPlaceholder('比分 如 102:98').fill('102:98')
  const submission = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/api/v1/tasks'))
  await page.getByRole('button', { name: '确认分析' }).click()
  const form = (await submission).postDataBuffer()?.toString() ?? ''
  expect(form).toContain('主队A')
  expect(form).toContain('name="score2"')
  await expect(page.getByText('正在分析中，请稍等')).toBeVisible()
  await expect(page.locator('.cv-tip')).toHaveText('空切是无球队员向篮下跑动。')
  await expect(page.getByText(/已用时间|预计剩余/)).toHaveCount(0)
  backend.finish()
  await expect(page.getByRole('region', { name: '赛事解说' })).toBeVisible({ timeout: 7000 })
  if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/result.png`, fullPage: true })
  await expect(page.getByText('球员正在持球推进。').first()).toBeVisible()
  await page.getByRole('textbox', { name: '向 AI 提问' }).fill('总结比赛')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('这段比赛中，球员正在持球推进。')).toBeVisible()
})

test('narrow screen keeps video, frames, narration and chat available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const backend = await mockBackend(page)
  backend.finish()
  await page.goto('/tasks/video-test')
  await expect(page.getByRole('region', { name: '赛事解说' })).toBeVisible()
  await expect(page.getByText('画面帧')).toBeVisible()
  await expect(page.getByText('AI 对话')).toBeVisible()
  const panel = page.getByRole('region', { name: '赛事解说' })
  await expect(panel.locator(':scope > :first-child')).toHaveClass('cv-ruler')
  await expect(panel.getByRole('button', { name: '朗读解说' })).toHaveCount(0)
  await page.locator('video').dispatchEvent('timeupdate')
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.getByRole('button', { name: '导出解说' }).click()
  const dialog = page.getByRole('dialog', { name: '导出解说' })
  await expect(dialog.getByRole('button', { name: '下载 MP3' })).toBeVisible()
  await dialog.getByRole('button', { name: '关闭' }).click()
  await page.evaluate(() => window.scrollTo({ top: 220, behavior: 'instant' }))
  await expect(page.locator('.cv-console-top')).toBeInViewport()
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect(page.locator('.cv-console-top')).not.toHaveClass(/faded/)
  const width = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(width).toBeLessThanOrEqual(390)
})

test('desktop commentary spans the three panels and navigation stays visible', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const backend = await mockBackend(page)
  backend.finish()
  await page.goto('/tasks/video-test')
  const rect = async (selector: string) => page.locator(selector).evaluate(el => el.getBoundingClientRect().toJSON())
  const [frames, video, chat, commentary] = await Promise.all(
    ['.cv-frame-panel', '.cv-video-panel', '.cv-chat-panel', '.cv-commentary'].map(rect),
  )
  expect(frames.right).toBeLessThan(video.left)
  expect(video.right).toBeLessThan(chat.left)
  expect(chat.top).toBe(video.top)
  expect(frames.top).toBe(video.top)
  expect(commentary.top).toBeGreaterThan(Math.max(frames.bottom, video.bottom, chat.bottom))
  expect(commentary.left).toBe(frames.left)
  expect(commentary.right).toBe(chat.right)

  await page.mouse.move(640, 360)
  const nav = page.getByRole('navigation', { name: '工作台导航', includeHidden: true })
  await expect(nav).toHaveCSS('opacity', '1')
  await page.mouse.move(640, 5)
  await expect(nav).toHaveCSS('opacity', '1')
  await page.getByRole('link', { name: '返回主页' }).click()
  await expect(page.getByRole('heading', { name: '篮球视频分析' })).toBeVisible()
})

test('full narration, match question and counts use the current video', async ({ page }) => {
  const backend = await mockBackend(page)
  backend.finish()
  await page.goto('/tasks/video-test')
  const report = page.getByRole('region', { name: '整场 AI 解说' })
  const chart = page.getByRole('region', { name: '场上人数变化' })
  await expect(report).toContainText(narration.text)
  await expect(chart).toContainText('当前画面 8 人 · 峰值 10 人')
  await page.locator('.cv-video-stage video').evaluate(el => {
    const video = el as HTMLVideoElement
    video.currentTime = 9
    video.dispatchEvent(new Event('timeupdate'))
  })
  await expect(chart).toContainText('当前画面 10 人')
  await report.getByRole('textbox').fill('总结一下')
  const call = page.waitForRequest(req => req.url().endsWith('/agent/chat'))
  await report.getByRole('button', { name: '提问', exact: true }).click()
  expect((await call).postDataJSON().task_id).toBe(task.task_id)
  await expect(report.locator('.cv-match-answer')).toContainText('球员正在持球推进')
})

test('six short tips rotate every six seconds and restart the cycle', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-01-01T12:00:00Z') })
  await page.clock.pauseAt(new Date('2026-01-01T12:01:00Z'))
  await mockBackend(page)
  await page.setViewportSize({ width: 320, height: 700 })
  await page.goto('/analyzing/video-test')
  const tip = page.locator('.cv-tip')
  const first = await tip.innerText()
  await page.clock.fastForward(5900)
  await expect(tip).toHaveText(first)
  await page.clock.fastForward(100)
  const tips = new Set([first])
  for (let index = 1; index < 6; index++) {
    tips.add(await tip.innerText())
    expect(await tip.evaluate(el => el.clientHeight <= Math.ceil(parseFloat(getComputedStyle(el).lineHeight)))).toBeTruthy()
    await page.clock.fastForward(6000)
  }
  expect(tips.size).toBe(6)
  await expect(tip).toHaveText(first)
})

test('playback follows narration sections without event details', async ({ page, context, browserName }) => {
  const backend = await mockBackend(page)
  backend.finish()
  const rows = Array.from({ length: 45 }, (_, i) => ({ ...event, t_ms: i * 200, text: '比赛事件 ' + i }))
  await page.route('**/api/v1/tasks/video-test/events', route =>
    route.fulfill({ json: { code: 0, result: rows, msg: 'ok' } }))
  await page.goto('/tasks/video-test')
  const cards = page.locator('.cv-strip-card')
  await expect(cards).toHaveCount(1)
  await expect(page.locator('.cv-seek-node')).toHaveCount(1)
  await expect(cards).toContainText(narration.text)
  await expect(page.locator('.cv-event-details')).toHaveCount(0)
  await expect(page.getByText('音频待测试', { exact: true })).toHaveCount(0)
  const player = page.locator('.cv-video-stage video')
  await player.evaluate(el => { (el as HTMLVideoElement).currentTime = 4 })
  await page.getByRole('combobox', { name: '视频倍速' }).selectOption('1.5')
  expect(await player.evaluate(el => (el as HTMLVideoElement).playbackRate)).toBe(1.5)
  expect(await player.evaluate(el => (el as HTMLVideoElement).currentTime)).toBe(4)
  await cards.last().click()
  await expect(cards.last()).toHaveClass(/active/)
  if (browserName === 'chromium') {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.getByRole('button', { name: '复制全文' }).click()
    await expect(page.getByText('已复制全文')).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(narration.text)
  }
})

test('commentary audio follows playback speed, pause, seek and mute', async ({ page }) => {
  const backend = await mockBackend(page)
  backend.finish()
  function tone(seconds: number) {
    const samples = 8000 * seconds
    const wav = Buffer.alloc(44 + samples * 2)
    wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8)
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
    wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32)
    wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(samples * 2, 40)
    for (let i = 0; i < samples; i++) wav.writeInt16LE(Math.round(3000 * Math.sin(i * .3)), 44 + i * 2)
    return wav
  }
  function mediaFile(data: Buffer) {
    return async (route: Route) => {
      const range = route.request().headers().range?.match(/^bytes=(\d+)-(\d*)$/)
      const start = Number(range?.[1] || 0)
      const end = Math.min(Number(range?.[2] || data.length - 1), data.length - 1)
      const body = data.subarray(start, end + 1)
      await route.fulfill({ status: range ? 206 : 200, contentType: 'audio/wav', body,
        headers: { 'Accept-Ranges': 'bytes', 'Content-Length': String(body.length),
          ...(range ? { 'Content-Range': `bytes ${start}-${end}/${data.length}` } : {}) } })
    }
  }
  await page.route('**/preview/status', route => route.fulfill({ json: { code: 0, result: { status: 'ready' } } }))
  await page.route('**/preview', mediaFile(tone(20)))
  await page.route('**/narration', route => route.fulfill({ json: { code: 0, result: { ...narration,
    sections: [0, 10000].map(start_ms => ({ start_ms, text: '持球推进。' })) } } }))
  await page.route('**/narration/audio?**', mediaFile(tone(9)))
  await page.addInitScript(() => {
    const media: HTMLAudioElement[] = []
    Object.defineProperty(window, 'testNarrationMedia', { value: media })
    window.Audio = new Proxy(window.Audio, { construct(target, args) {
      const player = Reflect.construct(target, args) as HTMLAudioElement
      media.push(player)
      return player
    } })
  })
  const state = () => page.evaluate(() => {
    const list = (window as Window & { testNarrationMedia: HTMLAudioElement[] }).testNarrationMedia
    return list.filter(el => el.getAttribute('src')).map(el => ({ src: el.src, paused: el.paused, time: el.currentTime, rate: el.playbackRate }))
  })
  await page.goto('/tasks/video-test')
  const video = page.locator('.cv-video-stage video')
  await expect.poll(() => video.evaluate(el => (el as HTMLVideoElement).readyState)).toBeGreaterThan(1)
  await page.getByRole('button', { name: '播放', exact: true }).click()
  await expect.poll(async () => (await state()).some(a => !a.paused && a.time > 0)).toBe(true)
  await expect.poll(async () => (await state()).some(a => !a.paused && Math.abs(a.rate - .9) < .01)).toBe(true)
  await page.getByLabel('视频倍速').selectOption('2')
  await expect.poll(async () => (await state()).some(a => !a.paused && Math.abs(a.rate - 1.8) < .01)).toBe(true)
  await page.getByRole('button', { name: '暂停', exact: true }).click()
  await expect.poll(async () => (await state()).every(a => a.paused)).toBe(true)
  await video.evaluate(el => { (el as HTMLVideoElement).currentTime = 12 })
  await page.getByRole('button', { name: '播放', exact: true }).click()
  await expect.poll(async () => (await state()).some(a => a.src.includes('section=1') && !a.paused && a.time >= 1.7 && Math.abs(a.rate - 1.8) < .01)).toBe(true)
  // A real video emits pause and ended before an utterance necessarily finishes.
  await video.evaluate(el => {
    const media = el as HTMLVideoElement
    media.pause()
    Object.defineProperty(media, 'ended', { configurable: true, value: true })
    media.dispatchEvent(new Event('ended'))
  })
  await expect.poll(async () => (await state()).some(a => a.src.includes('section=1') && !a.paused)).toBe(true)
  const finishing = (await state()).find(a => a.src.includes('section=1'))!
  expect(finishing.time).toBeLessThan(8)
  await expect(page.getByText('正在播完最后一句…')).toBeVisible()
  await video.evaluate(el => { Object.defineProperty(el, 'ended', { configurable: true, value: false }) })
  await page.getByRole('button', { name: '关闭解说声音' }).click()
  await expect.poll(async () => (await state()).every(a => a.paused)).toBe(true)
  await page.getByRole('button', { name: '播放', exact: true }).click()
  expect(await video.evaluate(el => (el as HTMLVideoElement).paused)).toBe(false)
})


async function mockHistory(page: Page, count = 2, failOnce = false) {
  await mockBackend(page)
  let rows = [
    ...Array.from({ length: count }, (_, index) => ({ ...task, task_id: `history-${index}`, status: index % 2 ? 'failed' : 'ready' })),
    { ...task, task_id: 'active-task', status: 'running' },
    { ...task, task_id: 'queued-task', status: 'pending' },
  ]
  const deleted: string[] = []
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/tasks' && route.request().method() === 'GET') {
      const offset = Number(url.searchParams.get('offset') || 0)
      const limit = Number(url.searchParams.get('limit') || 50)
      return route.fulfill({ json: { code: 0, result: rows.slice(offset, offset + limit), msg: 'ok' } })
    }
    if (route.request().method() === 'DELETE') {
      const id = url.pathname.split('/').at(-1)!
      if (failOnce && id === 'history-0') {
        failOnce = false
        return route.fulfill({ status: 503, json: { detail: '暂时无法删除' } })
      }
      deleted.push(id)
      rows = rows.filter(item => item.task_id !== id)
      return route.fulfill({ json: { code: 0, result: { task_id: id, deleted: true }, msg: 'ok' } })
    }
    return route.fallback()
  })
  return deleted
}

test('clearing history supports cancellation and retains unfinished tasks', async ({ page }) => {
  const deleted = await mockHistory(page)
  await page.goto('/recent')
  const clear = page.getByRole('button', { name: '清空历史任务', exact: true })
  await expect(page.locator('.cv-task-row')).toHaveCount(4)
  page.once('dialog', dialog => dialog.dismiss())
  await clear.click()
  expect(deleted).toHaveLength(0)
  await expect(page.locator('.cv-task-row')).toHaveCount(4)
  page.once('dialog', dialog => dialog.accept())
  await clear.click()
  await expect(page.getByRole('status')).toContainText('已清空 2 条历史任务')
  await expect(page.locator('.cv-task-row')).toHaveCount(2)
  expect(deleted.sort()).toEqual(['history-0', 'history-1'])
  await page.reload()
  await expect(page.locator('.cv-task-row')).toHaveCount(2)
})

test('clearing history visits all pages and allows retry after partial failure', async ({ page }) => {
  const deleted = await mockHistory(page, 201, true)
  await page.goto('/recent')
  await expect(page.locator('.cv-task-row')).toHaveCount(50)
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '清空历史任务', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已清空 200 条历史任务。1 条未能删除', { timeout: 30000 })
  await expect(page.locator('.cv-task-row')).toHaveCount(3)
  expect(deleted).toHaveLength(200)
  expect(deleted).not.toContain('active-task')
  expect(deleted).not.toContain('queued-task')
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '清空历史任务', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已清空 1 条历史任务。')
  await expect(page.locator('.cv-task-row')).toHaveCount(2)
})


test('tool traces show readable names, arguments, results and restored history', async ({ page }) => {
  const backend = await mockBackend(page)
  backend.finish()
  const calls = [
    { tool: 'query_video_events', args: { task_id: 'video-test', offset: 20, limit: 20 }, status: 'ok', result_summary: '已读取第 21 至 40 条事件', elapsed_ms: null },
    { tool: 'commentary_classify', args: { text: '球员送出一记传球' }, status: 'error', result_summary: '工具调用失败：分类模型未就绪', elapsed_ms: 12 },
  ]
  const session = { session_id: 'trace-session', task_id: task.task_id, title: '工具调用示例', message_count: 2, updated_at: task.created_at, created_at: task.created_at }
  await page.route('**/agent/chat', route => route.fulfill({ json: { code: 0, result: {
    session_id: session.session_id, task_id: task.task_id, agent: '已查询比赛事件，文本分类暂不可用。', tool_calls: calls,
  }, msg: 'ok' } }))
  await page.route('**/agent/sessions?**', route => route.fulfill({ json: { code: 0, result: [session], msg: 'ok' } }))
  await page.route('**/agent/sessions/trace-session', route => route.fulfill({ json: { code: 0, result: {
    ...session, history: [{ role: 'agent', content: '已查询比赛事件，文本分类暂不可用。', tool_calls: calls }],
  }, msg: 'ok' } }))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/tasks/video-test')
  await page.locator('.cv-tool-guide summary').click()
  await expect(page.locator('.cv-tool-guide li')).toHaveCount(5)
  await expect(page.locator('.cv-tool-guide')).toContainText('检索真人解说')
  await page.getByRole('textbox', { name: '向 AI 提问' }).fill('查询事件并分类这句解说')
  await page.getByRole('button', { name: '发送' }).click()
  const trace = page.locator('.cv-tool-trace').last()
  await trace.locator('summary').click()
  await expect(trace).toContainText('查询视频事件')
  await expect(trace).toContainText('跳过条数')
  await expect(trace).toContainText('已读取第 21 至 40 条事件')
  await expect(trace).toContainText('分类模型未就绪')
  await expect(trace).toContainText('失败')
  await expect(trace).toContainText('12 ms')
  await expect(trace.locator('.cv-tool-call').first()).not.toContainText('耗时')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: '对话历史', exact: true }).click()
  await page.getByRole('button', { name: /工具调用示例/ }).click()
  await page.locator('.cv-tool-trace summary').click()
  await expect(page.locator('.cv-tool-trace')).toContainText('已读取第 21 至 40 条事件')
})
