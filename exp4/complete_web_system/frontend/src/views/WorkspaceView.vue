<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  agentChat, createVideoTask, deleteTask, getAgentSession, getDetections,
  getEvents, getNarration, getTask, getTaskFrameUrl, getTaskPreviewStatus,
  getTaskPreviewUrl, listAgentSessions, listTasks, retryNarration,
  type AgentSessionListItem, type AgentToolCall, type CommentaryEvent,
  type DetectionFrame, type TaskListItem,
  type TaskNarration, type TaskStatus,
} from '../api/client'

import NarrationSpeech from './NarrationSpeech.vue'
import VideoNarration from './VideoNarration.vue'
const exporting = ref(false)

const exportDialog = ref<HTMLDialogElement | null>(null)
const audioError = ref('')
const downloading = ref(false)
const audioUrl = computed(() => `/api/v1/tasks/${encodeURIComponent(currentTaskId.value)}/narration/audio`)

async function downloadAudio(): Promise<void> {
  if (downloading.value) return
  const id = currentTaskId.value
  downloading.value = true
  audioError.value = ''
  try {
    const reply = await fetch(audioUrl.value)
    if (!reply.ok) throw new Error('语音生成失败，请稍后重试')
    const blob = await reply.blob()
    if (id !== currentTaskId.value) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${task.value?.video_name ?? '比赛'}-整场解说.mp3`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    if (id === currentTaskId.value) audioError.value = error instanceof Error ? error.message : '语音下载失败'
  } finally {
    downloading.value = false
  }
}

type ChatTurn = { role: 'user' | 'agent'; content: string; tool_calls?: AgentToolCall[]; pending?: boolean }
type StripItem = { start_ms: number; end_ms: number; text: string; label: string }

const route = useRoute()
const router = useRouter()
const tasks = ref<TaskListItem[]>([])
const task = ref<TaskStatus | null>(null)
const events = ref<CommentaryEvent[]>([])
const narration = ref<TaskNarration | null>(null)
const sessions = ref<AgentSessionListItem[]>([])
const chatTurns = ref<ChatTurn[]>([])
const sessionId = ref('')
const chatDraft = ref('')
const chatBusy = ref(false)
const matchQuestion = ref('')
const matchAnswer = ref('')
const retryBusy = ref(false)
const narrationStatus = computed(() => ({
  ready: '已生成', failed: '生成失败', running: '生成中', pending: '等待生成',
  not_started: '尚未生成', empty: '缺少事件',
}[narration.value?.status ?? 'not_started']))
const historyOpen = ref(false)
const chatError = ref('')
const pageError = ref('')
const uploading = ref(false)
const uploadPercent = ref(0)
const showUpload = ref(false)
const selectedFile = ref<File | null>(null)
const videoName = ref('')
const videoElement = ref<HTMLVideoElement | null>(null)
const overlayCanvas = ref<HTMLCanvasElement | null>(null)
const stripElement = ref<HTMLDivElement | null>(null)
const frameElement = ref<HTMLDivElement | null>(null)
const duration = ref(0)
const currentTime = ref(0)
const playing = ref(false)
const showBoxes = ref(false)
const videoSource = ref('')
const previewMessage = ref('')
const detections = ref<DetectionFrame[]>([])
const frameWindow = ref(-1)
const fileInput = ref<HTMLInputElement | null>(null)
const team1 = ref('')
const team2 = ref('')
const score = ref('')
const uploadPreview = ref('')
const uploadDuration = ref(0)
const basketballTips = [
  '空切是无球队员向篮下跑动。',
  '挡拆后，掩护人可以顺下接球。',
  '抢到前场篮板，可以再攻一次。',
  '变向运球能帮助持球人摆脱防守。',
  '快攻讲究在对手落位前推进。',
  '卡位能帮助球员争抢篮板。',
]
const tipIndex = ref(0)
let tipTimer = 0
const copyNotice = ref('')
const detailsOpen = ref(false)
const playbackRate = ref(1)
const playbackRates = [0.5, 0.75, 1, 1.25, 1.5, 2]
let taskTimer = 0
let previewTimer = 0
let narrationTimer = 0
let generation = 0
let localVideoUrl = ''
let localVideoTaskId = ''
let lastScrolledStrip = -1
let lastScrolledFrame = -1

const view = computed(() => route.path === '/recent' ? 'recent' : route.path.startsWith('/analyzing/') ? 'analyzing' : route.path.startsWith('/tasks/') ? 'result' : 'home')
const currentTaskId = computed(() => String(route.params.taskId ?? ''))
const latestTask = computed(() => tasks.value.find(item => item.status === 'ready') ?? null)
const stageIndex = computed(() => {
  const stage = task.value?.stage ?? 'queued'
  if (stage === 'ready') return 4
  if (stage === 'commentary' || stage === 'narrating' || stage === 'action') return 3
  if (stage === 'detecting') return 2
  if (stage === 'decoding') return 1
  return 0
})
const stageNames = ['提交视频', '读取视频', '检测球员', '整理解说', '完成']
const stageText = computed(() => ({ queued: '等待分析', decoding: '正在读取视频', detecting: '正在检测球员', action: '正在识别动作', commentary: '正在生成事件解说', narrating: '正在生成整场解说', ready: '分析完成', failed: '分析失败' }[task.value?.stage ?? 'queued'] ?? '正在分析中'))
const progress = computed(() => Math.max(0, Math.min(100, Math.round((task.value?.progress ?? 0) * 100))))
const eventLabels: Record<string, string> = {
  player_count: '场上人数', player_count_change: '人数变化', player_count_snapshot: '人数快照',
  group_direction_change: '移动方向变化', player_cluster: '球员聚集', action: '动作预测',
}
const stripItems = computed<StripItem[]>(() => {
  const sections = narration.value?.sections?.filter(item => item.text.trim()) ?? []
  const cards: StripItem[] = []
  if (sections.length) {
    for (const section of sections) {
      const last = cards.at(-1)
      if (last && section.start_ms - last.start_ms < 4000) {
        last.end_ms = section.end_ms
        last.text += ' ' + section.text
      } else cards.push({ ...section, label: 'AI 解说' })
    }
    return cards
  }
  // While the full script is unavailable, group nearby observations into readable passages.
  const windowMs = Math.max(6000, Math.min(15000, duration.value * 1000 / 6))
  let group: CommentaryEvent[] = []
  function finishGroup() {
    if (!group.length) return
    const actions = group.filter(event => event.type === 'action' && event.action_zh)
    const actionsSeen = [...new Set(actions.map(event => event.action_zh!))].slice(0, 3)
    const observation = group.find(event => event.type !== 'action' && event.text)?.text ?? ''
    const actionText = actionsSeen.length ? '这一段画面中疑似出现' + actionsSeen.join('、') + '。' : ''
    const text = observation + actionText || group.find(event => event.text)?.text || '这一时段记录了比赛事件。'
    cards.push({ start_ms: group[0]!.t_ms, end_ms: group.at(-1)!.t_ms, text, label: '事件摘要' })
    group = []
  }
  for (const event of events.value) {
    if (group.length && event.t_ms - group[0]!.t_ms >= windowMs) finishGroup()
    group.push(event)
  }
  finishGroup()
  return cards
})
const voiceSections = computed(() => narration.value?.status === 'ready' && !!narration.value.sections?.length)
const voiceCues = computed(() => {
  if (voiceSections.value) return narration.value!.sections
  if (narration.value?.text) return [{ start_ms: 0, text: narration.value.text }]
  return stripItems.value
})
const activeStripIndex = computed(() => {
  const time = Math.round(currentTime.value * 1000)
  let index = -1
  for (const item of stripItems.value) {
    if (item.start_ms > time) break
    index++
  }
  return index
})
const currentCaption = computed(() => {
  const item = stripItems.value[activeStripIndex.value]
  return item && item.start_ms <= currentTime.value * 1000 ? item.text : ''
})
const countEvents = computed(() => events.value.filter(
  (item): item is CommentaryEvent & { player_count: number } =>
    item.type.startsWith('player_count') && typeof item.player_count === 'number' && Number.isFinite(item.player_count),
))
const peakCount = computed(() => countEvents.value.reduce((peak, item) => Math.max(peak, item.player_count), 0))
const countNow = computed(() => [...countEvents.value].reverse().find(item => item.t_ms <= currentTime.value * 1000)?.player_count ?? null)
const chartPoints = computed(() => countEvents.value.map(item => ({
  x: Math.min(100, item.t_ms / Math.max(duration.value * 1000, 1) * 100),
  y: 92 - 84 * item.player_count / Math.max(1, peakCount.value),
})))
const chartLine = computed(() => chartPoints.value.map(point => point.x + ',' + point.y).join(' '))
const keyFrames = computed(() => {
  const candidates = events.value.filter(item => item.type === 'action' || item.type.startsWith('player_count') || item.type === 'group_direction_change')
  if (candidates.length <= 12) return candidates
  return Array.from({ length: 12 }, (_, index) => candidates[Math.round(index * (candidates.length - 1) / 11)]!).filter(Boolean)
})
const activeFrameIndex = computed(() => {
  let index = 0
  keyFrames.value.forEach((item, i) => { if (item.t_ms <= currentTime.value * 1000 + 150) index = i })
  return index
})

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0))
  return `${String(Math.floor(whole / 60)).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`
}
function timeLabel(value?: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '时间未知'
}
function stateLabel(value: string): string {
  return ({ ready: '分析完成', running: '正在分析', pending: '等待分析', failed: '分析失败' } as Record<string, string>)[value] ?? value
}
function frameUrl(ms: number): string { return getTaskFrameUrl(currentTaskId.value, ms) }
function pinPosition(ms: number): string { return `${Math.max(0, Math.min(100, ms / Math.max(1, duration.value * 1000) * 100))}%` }

async function reloadTasks(): Promise<void> {
  try { tasks.value = await listTasks() } catch (error) { pageError.value = error instanceof Error ? error.message : '无法读取最近任务' }
}
function clearFile(): void {
  if (uploadPreview.value) URL.revokeObjectURL(uploadPreview.value)
  uploadPreview.value = ''
  uploadDuration.value = 0
  selectedFile.value = null
}
function chooseVideo(): void {
  clearFile()
  videoName.value = team1.value = team2.value = score.value = pageError.value = ''
  showUpload.value = true
}
function selectFile(file?: File): void {
  if (!file || uploading.value) return
  if (!file.name.toLowerCase().endsWith('.mp4')) { pageError.value = '请选择 MP4 视频'; return }
  clearFile()
  selectedFile.value = file
  uploadPreview.value = URL.createObjectURL(file)
  showUpload.value = true
  pageError.value = ''
}
function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  selectFile(input.files?.[0])
  input.value = ''
}
function closeUpload(): void {
  if (!uploading.value) { showUpload.value = false; clearFile(); pageError.value = '' }
}
async function confirmUpload(): Promise<void> {
  if (!selectedFile.value || uploading.value) return
  const scores = score.value.trim().match(/^(\d{1,3})\s*[:：比]\s*(\d{1,3})$/)
  if (score.value.trim() && !scores) { pageError.value = '请按 102:98 的格式填写比分'; return }
  uploading.value = true; uploadPercent.value = 0; pageError.value = ''
  const file = selectedFile.value
  const form = new FormData()
  form.append('file', file)
  if (team1.value.trim()) form.append('team1', team1.value.trim())
  if (team2.value.trim()) form.append('team2', team2.value.trim())
  if (scores) { form.append('score1', scores[1]!); form.append('score2', scores[2]!) }
  form.append('video_name', videoName.value.trim() || file.name)
  try {
    const created = await createVideoTask(form, percent => { uploadPercent.value = percent })
    if (localVideoUrl) URL.revokeObjectURL(localVideoUrl)
    localVideoUrl = URL.createObjectURL(file)
    localVideoTaskId = created.task_id
    showUpload.value = false; clearFile()
    await router.push(`/analyzing/${created.task_id}`)
  } catch (error) { pageError.value = error instanceof Error ? error.message : '上传失败' }
  finally { uploading.value = false }
}
function stopTimers(): void {
  window.clearInterval(tipTimer)
  window.clearInterval(taskTimer); taskTimer = 0
  window.clearInterval(previewTimer); previewTimer = 0
  window.clearInterval(narrationTimer); narrationTimer = 0
}
async function pollTask(id: string, token: number): Promise<void> {
  try {
    const result = await getTask(id)
    if (generation !== token || currentTaskId.value !== id) return
    task.value = result
    if (result.status === 'ready') { stopTimers(); await router.replace(`/tasks/${id}`) }
    else if (result.status === 'failed') { stopTimers(); pageError.value = result.error || '视频分析失败' }
  } catch (error) { if (generation === token) pageError.value = error instanceof Error ? error.message : '连接暂时中断' }
}
async function pollPreview(id: string, token: number): Promise<void> {
  try {
    const state = await getTaskPreviewStatus(id)
    if (generation !== token || currentTaskId.value !== id) return
    if (state.status === 'ready') {
      if (!videoSource.value || !videoSource.value.startsWith('blob:')) videoSource.value = getTaskPreviewUrl(id)
      previewMessage.value = ''
      window.clearInterval(previewTimer); previewTimer = 0
    } else if (state.status === 'failed') {
      previewMessage.value = state.error || '浏览器预览暂不可用'
      window.clearInterval(previewTimer); previewTimer = 0
    } else previewMessage.value = '正在准备浏览器可播放的视频…'
  } catch (error) { if (generation === token) previewMessage.value = error instanceof Error ? error.message : '预览连接中断' }
}
async function pollNarration(id: string, token: number): Promise<void> {
  try {
    const result = await getNarration(id)
    if (generation !== token || currentTaskId.value !== id) return
    narration.value = result
    if (!['running', 'pending'].includes(result.status)) { window.clearInterval(narrationTimer); narrationTimer = 0 }
  } catch (error) { if (generation === token) pageError.value = error instanceof Error ? error.message : '解说读取失败' }
}
async function loadSession(id: string): Promise<void> {
  try {
    const result = await getAgentSession(id)
    if (result.task_id !== currentTaskId.value) return
    sessionId.value = id
    chatTurns.value = result.history.map(item => ({ role: item.role, content: item.content, tool_calls: item.tool_calls }))
    historyOpen.value = false
  } catch (error) { chatError.value = error instanceof Error ? error.message : '对话读取失败' }
}
async function reloadSessions(id: string, restore = false): Promise<void> {
  try {
    const rows = await listAgentSessions(id)
    if (id !== currentTaskId.value) return
    sessions.value = rows
    if (restore && sessions.value.length) await loadSession(sessions.value[0]!.session_id)
  } catch (error) { chatError.value = error instanceof Error ? error.message : '对话历史读取失败' }
}
function newChat(): void { sessionId.value = ''; chatTurns.value = []; chatDraft.value = ''; chatError.value = ''; historyOpen.value = false }
async function sendChat(text?: string): Promise<string | undefined> {
  const question = (text ?? chatDraft.value).trim()
  if (!question || chatBusy.value || !currentTaskId.value) return
  if (text === undefined) chatDraft.value = ''
  chatError.value = ''; chatBusy.value = true
  const taskId = currentTaskId.value
  chatTurns.value.push({ role: 'user', content: question })
  const pending = reactive<ChatTurn>({ role: 'agent', content: 'AI 正在思考…', pending: true })
  chatTurns.value.push(pending)
  try {
    const result = await agentChat({ task_id: taskId, message: question, ...(sessionId.value ? { session_id: sessionId.value } : {}) })
    if (taskId !== currentTaskId.value) return
    pending.content = result.agent; pending.tool_calls = result.tool_calls; pending.pending = false
    sessionId.value = result.session_id
    await reloadSessions(taskId)
    return result.agent
  } catch (error) {
    if (taskId !== currentTaskId.value) return
    pending.content = error instanceof Error ? error.message : 'AI 暂时无法回答'
    pending.pending = false; chatError.value = '发送失败，可以重试。'
      return pending.content
  } finally { if (taskId === currentTaskId.value) chatBusy.value = false }
}
async function askAboutMatch(): Promise<void> {
  const question = matchQuestion.value.trim()
  if (!question || chatBusy.value) return
  const token = generation
  matchQuestion.value = ''
  matchAnswer.value = 'AI 正在思考…'
  const reply = await sendChat(question)
  if (generation === token) matchAnswer.value = reply ?? ''
}
function askQuick(question: string): void { void sendChat(question) }
async function loadResult(id: string, token: number): Promise<void> {
  try {
    const [status, eventRows, narrationResult] = await Promise.all([getTask(id), getEvents(id), getNarration(id)])
    if (generation !== token || currentTaskId.value !== id) return
    task.value = status; events.value = [...eventRows].sort((a, b) => a.t_ms - b.t_ms); narration.value = narrationResult
    duration.value = Number(status.metadata.video_duration_seconds) || Math.max(
      0, (events.value.at(-1)?.t_ms ?? 0) / 1000, (narrationResult.sections?.at(-1)?.end_ms ?? 0) / 1000,
    )
    if (status.status !== 'ready') { await router.replace(`/analyzing/${id}`); return }
    if (localVideoTaskId === id && localVideoUrl) videoSource.value = localVideoUrl
    else videoSource.value = ''
    await reloadSessions(id, true)
    if (generation !== token || currentTaskId.value !== id) return
    if (route.query.chat === 'history') historyOpen.value = true
    void pollPreview(id, token)
    previewTimer = window.setInterval(() => { void pollPreview(id, token) }, 2500)
    if (['running', 'pending'].includes(narrationResult.status)) narrationTimer = window.setInterval(() => { void pollNarration(id, token) }, 2500)
  } catch (error) { if (generation === token) pageError.value = error instanceof Error ? error.message : '无法加载分析结果' }
}
async function openRoute(): Promise<void> {
  tipIndex.value = 0
  detailsOpen.value = false
  copyNotice.value = ''
  generation += 1
  const token = generation
  stopTimers(); pageError.value = ''; task.value = null; events.value = []; narration.value = null
  matchAnswer.value = ''; matchQuestion.value = ''; retryBusy.value = false; chatBusy.value = false; chatError.value = ''; chatDraft.value = ''
  sessions.value = []; chatTurns.value = []; sessionId.value = ''; historyOpen.value = false
  videoSource.value = ''; currentTime.value = 0; duration.value = 0; detections.value = []; frameWindow.value = -1
  void reloadTasks()
  if (view.value === 'analyzing') {
    tipTimer = window.setInterval(() => { tipIndex.value = (tipIndex.value + 1) % basketballTips.length }, 6000)
    const id = currentTaskId.value
    await pollTask(id, token)
    if (generation === token) taskTimer = window.setInterval(() => { void pollTask(id, token) }, 1800)
  } else if (view.value === 'result') await loadResult(currentTaskId.value, token)
}
function jumpTo(ms: number): void {
  const video = videoElement.value
  if (!video) return
  video.pause()
  video.currentTime = Math.min(Math.max(0, ms / 1000), duration.value || Infinity)
  currentTime.value = video.currentTime
  drawBoxes()
}
function seek(event: MouseEvent): void {
  const element = event.currentTarget as HTMLElement
  const box = element.getBoundingClientRect()
  jumpTo((event.clientX - box.left) / Math.max(1, box.width) * duration.value * 1000)
}
function applyPlaybackRate(): void {
  if (videoElement.value) videoElement.value.playbackRate = playbackRate.value
}
function togglePlayback(): void {
  const video = videoElement.value
  if (!video) return
  if (video.paused) void video.play().catch(() => { previewMessage.value = '视频暂时无法播放，请等待兼容预览完成' })
  else video.pause()
}
function onVideoError(): void {
  if (videoSource.value.startsWith('blob:') && currentTaskId.value) videoSource.value = getTaskPreviewUrl(currentTaskId.value)
  else previewMessage.value = '视频暂时无法播放，请稍后重试'
}
function followActiveItem(container: HTMLElement | null, horizontal: boolean): void {
  const active = container?.querySelector<HTMLElement>('.active')
  if (!container || !active) return
  const item = active.getBoundingClientRect()
  const box = container.getBoundingClientRect()
  if (horizontal && (item.left < box.left || item.right > box.right)) {
    container.scrollLeft += item.left - box.left - (container.clientWidth - item.width) / 2
  } else if (!horizontal && (item.top < box.top || item.bottom > box.bottom)) {
    container.scrollTop += item.top - box.top - (container.clientHeight - item.height) / 2
  }
}
function onVideoTime(): void {
  currentTime.value = videoElement.value?.currentTime ?? 0
  void loadDetectionWindow()
  drawBoxes()
  if (lastScrolledStrip === activeStripIndex.value && lastScrolledFrame === activeFrameIndex.value) return
  lastScrolledStrip = activeStripIndex.value
  lastScrolledFrame = activeFrameIndex.value
  void nextTick(() => {
    followActiveItem(stripElement.value, true)
    const frames = frameElement.value
    if (frames) followActiveItem(frames, frames.scrollWidth > frames.clientWidth)
  })
}
async function loadDetectionWindow(): Promise<void> {
  if (!showBoxes.value || !currentTaskId.value) return
  const start = Math.floor(currentTime.value / 15) * 15
  if (frameWindow.value === start) return
  frameWindow.value = start
  const id = currentTaskId.value
  try {
    const rows = await getDetections(id, start, start + 15)
    if (id === currentTaskId.value && frameWindow.value === start) { detections.value = rows; drawBoxes() }
  } catch { if (id === currentTaskId.value) detections.value = [] }
}
function drawBoxes(): void {
  const canvas = overlayCanvas.value, video = videoElement.value
  if (!canvas || !video) return
  const rect = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.round(rect.width * ratio)); canvas.height = Math.max(1, Math.round(rect.height * ratio))
  const ctx = canvas.getContext('2d'); if (!ctx) return
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height)
  if (!showBoxes.value || !video.videoWidth || !detections.value.length) return
  const scale = Math.min(rect.width / video.videoWidth, rect.height / video.videoHeight)
  const width = video.videoWidth * scale, height = video.videoHeight * scale
  const left = (rect.width - width) / 2, top = (rect.height - height) / 2
  const now = currentTime.value * 1000
  let frame = detections.value[0]!
  for (const row of detections.value) { if (row.t_ms <= now) frame = row; else break }
  ctx.lineWidth = 2; ctx.font = '11px sans-serif'
  for (const box of frame.boxes || []) {
    const x = left + (box.cx - box.w / 2) * width, y = top + (box.cy - box.h / 2) * height
    ctx.strokeStyle = '#f089bd'; ctx.strokeRect(x, y, box.w * width, box.h * height)
    ctx.fillStyle = '#e8558f'; ctx.fillRect(x, Math.max(top, y - 17), 44, 16)
    ctx.fillStyle = '#fff'; ctx.fillText(`#${box.track_id ?? '?'}`, x + 4, Math.max(top + 12, y - 5))
  }
}
function toggleBoxes(): void { showBoxes.value = !showBoxes.value; frameWindow.value = -1; if (showBoxes.value) void loadDetectionWindow(); else drawBoxes() }
function exportNarration(): void {
  if (!narration.value?.text) return
  const url = URL.createObjectURL(new Blob([narration.value.text], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `${task.value?.video_name ?? '视频'}-AI解说.txt`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function copyNarration(): Promise<void> {
  const text = narration.value?.text
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
    else {
      const field = document.createElement('textarea')
      field.value = text
      field.style.position = 'fixed'
      field.style.opacity = '0'
      document.body.appendChild(field)
      try {
        field.select()
        if (!document.execCommand('copy')) throw new Error()
      } finally { field.remove() }
    }
    copyNotice.value = '已复制全文'
  } catch { copyNotice.value = '复制失败，可选中正文复制。' }
}
async function regenerateNarration(): Promise<void> {
  if (retryBusy.value) return
  const id = currentTaskId.value
  const token = generation
  retryBusy.value = true
  try {
    await retryNarration(id)
    if (generation !== token) return
    narration.value = { task_id: id, status: 'running', text: '', sections: [] }
    window.clearInterval(narrationTimer)
    narrationTimer = window.setInterval(() => { void pollNarration(id, token) }, 2500)
  } catch (error) {
    if (generation === token) pageError.value = error instanceof Error ? error.message : '重新生成失败'
  } finally {
    if (generation === token) retryBusy.value = false
  }
}
async function removeTask(id: string): Promise<void> {
  if (!window.confirm('确定删除这条已完成的任务吗？')) return
  try { await deleteTask(id); await reloadTasks() } catch (error) { pageError.value = error instanceof Error ? error.message : '删除失败' }
}
function onResize(): void { drawBoxes() }
watch(() => route.fullPath, () => { void openRoute() }, { immediate: true })
onMounted(() => { window.addEventListener('resize', onResize) })
onBeforeUnmount(() => { clearFile(); stopTimers(); window.removeEventListener('resize', onResize); if (localVideoUrl) URL.revokeObjectURL(localVideoUrl) })
</script>

<template>
  <div class="cv-app">
    <input ref="fileInput" class="cv-hidden" type="file" accept="video/mp4,.mp4" @change="onFileChange">
    <nav v-if="view !== 'result'" class="cv-nav">
      <RouterLink to="/" class="cv-brand"><span class="cv-ball">◉</span><span><b>COURTVISION</b><small>AI BASKETBALL STUDIO</small></span></RouterLink>
      <div class="cv-nav-links"><RouterLink to="/" :class="{ selected: view === 'home' }">主页</RouterLink><RouterLink to="/recent" :class="{ selected: view === 'recent' }">最近任务</RouterLink></div>
      <div class="cv-nav-actions"><button class="cv-btn cv-outline" @click="router.push('/recent')">最近任务 <span class="cv-count">{{ tasks.length }}</span></button><button class="cv-btn cv-primary" @click="chooseVideo">开始分析</button></div>
    </nav>
    <div v-if="pageError && !showUpload" class="cv-alert" role="alert">{{ pageError }} <button @click="pageError = ''">×</button></div>

    <main v-if="view === 'home'" class="cv-home">
      <div class="cv-hero"><p class="cv-kicker">BASKETBALL INTELLIGENCE · COURTVISION</p><h1>篮球<span>视频分析</span></h1><p>导入一段比赛录像，自动检测球员位置与人数变化，在关键时刻生成中文赛事解说，<br>还可以就这场球继续向 AI 追问。</p><div class="cv-hero-buttons"><button class="cv-btn cv-primary cv-large" @click="chooseVideo">↥　导入视频</button><button class="cv-btn cv-outline cv-large" @click="router.push('/recent')">查看最近任务</button></div><small>支持 MP4 · 单个文件上限 5 GiB · 分析在后台进行</small></div>
      <section class="cv-home-showcase"><div v-if="latestTask" class="cv-latest"><div class="cv-latest-media"><img :src="getTaskFrameUrl(latestTask.task_id, 0)" alt="最近任务的视频画面"><span>最近完成</span></div><div><p class="cv-kicker">LATEST ANALYSIS</p><h2>{{ latestTask.video_name }}</h2><p>检测结果、关键事件、整场解说和 AI 对话都已放在同一个工作台。</p><button class="cv-btn cv-primary" @click="router.push(`/tasks/${latestTask.task_id}`)">查看分析结果 →</button></div></div><div v-else class="cv-empty"><div class="cv-empty-icon">▣</div><h2>还没有分析任务</h2><p>导入一段比赛视频，分析完成后这里会显示最新的视频画面、事件解说和 AI 对话。</p><button class="cv-btn cv-primary" @click="chooseVideo">↥　导入视频</button><div class="cv-tags"><span>球员检测</span><span>人数变化</span><span>事件时间轴</span><span>AI 解说</span></div></div></section>
    </main>

    <main v-else-if="view === 'analyzing'" class="cv-waiting"><div class="cv-wait-icon">◌</div><p class="cv-kicker">VIDEO ANALYSIS IN PROGRESS</p><h1>{{ task?.status === 'failed' ? '分析失败' : '正在分析中，请稍等' }}</h1><p>{{ task?.status === 'failed' ? (task.error || pageError) : stageText }}</p><div class="cv-progress"><i :style="{ width: `${progress}%` }"></i></div><div class="cv-progress-caption"><span>任务 {{ currentTaskId.slice(0, 8) }}</span><strong>{{ progress }}%</strong></div><p v-if="task?.status !== 'failed'" class="cv-tip">{{ basketballTips[tipIndex] }}</p><div class="cv-stages"><span v-for="(name, index) in stageNames" :key="name" :class="{ done: index < stageIndex, now: index === stageIndex }">{{ name }}</span></div><div class="cv-wait-actions"><button class="cv-btn cv-outline" @click="router.push('/')">返回主页</button><button class="cv-btn cv-outline" @click="router.push('/recent')">查看最近任务</button></div><small>离开此页不会中断后台分析，稍后可从最近任务返回。</small></main>

    <main v-else-if="view === 'recent'" class="cv-recent"><div class="cv-page-heading"><p class="cv-kicker">YOUR ANALYSIS HISTORY</p><h1>最近任务</h1><p>按创建时间排序，打开任务可继续查看视频、事件、解说和对话。</p></div><div class="cv-recent-list"><div v-if="!tasks.length" class="cv-empty-small">还没有任务。<button class="cv-btn cv-primary" @click="chooseVideo">导入视频</button></div><article v-for="item in tasks" :key="item.task_id" class="cv-task-row"><button class="cv-task-main" @click="router.push(item.status === 'ready' ? `/tasks/${item.task_id}` : `/analyzing/${item.task_id}`)"><img v-if="item.status === 'ready'" :src="getTaskFrameUrl(item.task_id, 0)" alt="视频首帧"><span v-else class="cv-task-icon">▣</span><span><b>{{ item.video_name }}</b><small>{{ item.task_id.slice(0, 8) }} · {{ timeLabel(item.created_at) }}</small></span></button><div class="cv-task-side"><span class="cv-task-status" :class="item.status">{{ stateLabel(item.status) }}<template v-if="item.status === 'running'"> · {{ Math.round(item.progress * 100) }}%</template></span><button class="cv-btn cv-outline" @click="router.push(item.status === 'ready' ? `/tasks/${item.task_id}?chat=history` : `/analyzing/${item.task_id}`)">{{ item.status === 'ready' ? '对话' : '查看进度' }}</button><button v-if="item.status === 'ready' || item.status === 'failed'" class="cv-icon-btn" aria-label="删除任务" @click="removeTask(item.task_id)">×</button></div></article></div></main>

    <main v-else class="cv-console">
      <nav class="cv-console-top" aria-label="工作台导航"><RouterLink to="/" class="cv-brand"><span class="cv-ball">◉</span><b>COURTVISION</b></RouterLink><RouterLink to="/" class="cv-btn cv-outline cv-return-home">← 返回主页</RouterLink><div class="cv-console-actions"><button class="cv-btn cv-outline" @click="router.push('/recent')">最近任务 <span class="cv-count">{{ tasks.length }}</span></button><button class="cv-btn cv-outline" :disabled="!narration?.text" @click="videoElement?.pause(); audioError = ''; exporting = true; exportDialog?.showModal()">导出解说</button><button class="cv-btn cv-primary" @click="chooseVideo">重新分析</button></div></nav>
      <div class="cv-console-grid"><section class="cv-frame-panel cv-panel"><header>画面帧 <span>随播放滚动</span></header><div ref="frameElement" class="cv-frame-list"><button v-for="(frame, index) in keyFrames" :key="`${frame.t_ms}-${index}`" class="cv-frame" :class="{ active: index === activeFrameIndex }" @click="jumpTo(frame.t_ms)"><img :src="frameUrl(frame.t_ms)" alt="事件附近视频帧"><span>{{ clock(frame.t_ms / 1000) }}</span></button><p v-if="!keyFrames.length" class="cv-panel-empty">暂无关键帧</p></div></section>
        <section class="cv-video-panel cv-panel"><div class="cv-video-stage"><video ref="videoElement" :src="videoSource" playsinline preload="metadata" @loadedmetadata="duration = videoElement?.duration || 0; applyPlaybackRate(); drawBoxes()" @timeupdate="onVideoTime" @play="playing = true" @pause="playing = false" @error="onVideoError"></video><canvas ref="overlayCanvas" class="cv-overlay"></canvas><button class="cv-box-toggle" :aria-pressed="showBoxes" @click="toggleBoxes">检测框 <span :class="{ on: showBoxes }"></span></button><div class="cv-live"><i></i> 分析结果</div><div v-if="currentCaption" class="cv-subtitle"><b>{{ clock(currentTime) }}</b><span>{{ currentCaption }}</span></div><div v-if="previewMessage" class="cv-preview-message">{{ previewMessage }}</div></div><div class="cv-video-controls"><button class="cv-play" :aria-label="playing ? '暂停' : '播放'" @click="togglePlayback">{{ playing ? 'Ⅱ' : '▶' }}</button><select v-model.number="playbackRate" class="cv-playback-rate" aria-label="视频倍速" title="视频倍速" @change="applyPlaybackRate"><option v-for="rate in playbackRates" :key="rate" :value="rate">{{ rate }}×</option></select><VideoNarration :key="currentTaskId" :video="videoElement" :cues="voiceCues" :segmented="voiceSections" :url="audioUrl" :revision="narration?.created_at || ''" /><span>{{ clock(currentTime) }} / {{ clock(duration) }}</span><div class="cv-seek" role="slider" tabindex="0" aria-label="视频进度" :aria-valuenow="Math.round(currentTime)" :aria-valuemax="Math.round(duration)" @click="seek" @keydown.left.prevent="jumpTo((currentTime - 5) * 1000)" @keydown.right.prevent="jumpTo((currentTime + 5) * 1000)"><div class="cv-seek-fill" :style="{ width: pinPosition(currentTime * 1000) }"></div><button v-for="(item, index) in stripItems" :key="`${item.start_ms}-${index}`" class="cv-seek-node" :class="{ active: item.start_ms === stripItems[activeStripIndex]?.start_ms }" :style="{ left: pinPosition(item.start_ms) }" :title="clock(item.start_ms / 1000)" @click.stop="jumpTo(item.start_ms)"></button></div><span>{{ countNow === null ? '—' : `${countNow} 人` }}</span></div></section>
        <section class="cv-chat-panel cv-panel"><header>AI 对话 <button class="cv-history-trigger" :aria-expanded="historyOpen" @click="historyOpen = !historyOpen">对话历史</button><span>当前视频</span></header><div v-if="historyOpen" class="cv-history"><div class="cv-history-head"><b>对话历史</b><button @click="historyOpen = false">×</button></div><button class="cv-btn cv-primary" @click="newChat">＋ 新建对话</button><button v-for="item in sessions" :key="item.session_id" class="cv-history-item" @click="loadSession(item.session_id)"><b>{{ item.title }}</b><small>{{ timeLabel(item.updated_at) }} · {{ item.message_count }} 条消息</small></button><p v-if="!sessions.length">暂无对话记录</p></div><div v-else class="cv-chat-content"><div class="cv-messages"><div v-if="!chatTurns.length" class="cv-chat-welcome"><span>✦</span><b>和 AI 聊聊这场球</b><p>提问会关联当前视频的真实事件，回答不会直接把模型预测当成进球事实。</p></div><div v-for="(turn, index) in chatTurns" :key="index" class="cv-message" :class="turn.role"><p>{{ turn.content }}</p><details v-if="turn.tool_calls?.length"><summary>{{ turn.tool_calls.length }} 次工具调用</summary><div v-for="(call, callIndex) in turn.tool_calls" :key="callIndex">{{ call.tool }} · {{ call.status === 'ok' ? '成功' : '失败' }}</div></details></div></div><div class="cv-quick"><button @click="askQuick('总结这段比赛的关键事件')">总结比赛</button><button @click="askQuick('人数变化最大的时段是什么时候？')">人数变化</button><button @click="askQuick('有哪些疑似三分出手？')">三分出手</button></div><form class="cv-chat-compose" @submit.prevent="sendChat()"><input v-model="chatDraft" maxlength="500" placeholder="就这场比赛继续提问…" aria-label="向 AI 提问"><button :disabled="chatBusy || !chatDraft.trim()" aria-label="发送">↑</button></form><small v-if="chatError" class="cv-chat-error">{{ chatError }}</small></div></section>
      <section class="cv-commentary cv-panel" aria-label="赛事解说"><div class="cv-ruler" @click="seek"><div class="cv-ruler-fill" :style="{ width: pinPosition(currentTime * 1000) }"></div><span v-for="(item, index) in stripItems" :key="index" class="cv-ruler-node" :class="{ active: item.start_ms === stripItems[activeStripIndex]?.start_ms }" :style="{ left: pinPosition(item.start_ms) }" @click.stop="jumpTo(item.start_ms)"></span></div><div class="cv-ruler-labels"><span v-for="tick in [0, .25, .5, .75, 1]" :key="tick">{{ clock(duration * tick) }}</span></div><div ref="stripElement" class="cv-strip"><button v-for="(item, index) in stripItems" :key="`${item.start_ms}-${index}`" class="cv-strip-card" :class="{ active: index === activeStripIndex }" @click="jumpTo(item.start_ms)"><time>{{ clock(item.start_ms / 1000) }}</time><span>{{ item.text }}</span><small>{{ item.label }}</small></button><p v-if="!stripItems.length">暂无解说，等待视频分析结果。</p></div></section></div>
      <section class="cv-panel cv-match-report" aria-label="整场 AI 解说">
        <header>✦ 整场 AI 解说 <div class="cv-report-tools"><em class="cv-audio-mark" title="解说语音（MP3 合成与浏览器朗读）尚未完成端到端测试，功能待验证">音频待测试</em><small role="status">{{ copyNotice }}</small><button class="cv-btn cv-outline" :disabled="!narration?.text" @click="copyNarration">复制全文</button><span>{{ narrationStatus }}</span></div></header>
        <div class="cv-report-body">
          <p class="cv-report-text">{{ narration?.text || narration?.error || ({ running: '正在根据比赛事件生成解说…', pending: '解说等待生成。', empty: '当前任务没有可供解说的事件。' } as Record<string,string>)[narration?.status ?? ''] || '整场解说尚未生成。' }}</p>
          <form class="cv-match-ask" @submit.prevent="askAboutMatch">
            <button type="button" class="cv-btn cv-outline" :disabled="!task || retryBusy || narration?.status === 'running' || narration?.status === 'pending'" @click="regenerateNarration">重新生成解说</button>
            <input v-model="matchQuestion" class="cv-import-input" maxlength="500" aria-label="针对当前比赛提问" placeholder="针对当前比赛提问，例如：有哪些关键动作？">
            <button class="cv-btn cv-outline" :disabled="!task || chatBusy || !matchQuestion.trim()">提问</button>
          </form>
          <p v-if="matchAnswer" class="cv-match-answer" aria-live="polite">{{ matchAnswer }}</p>
        </div>
      </section>
      <details v-if="events.length" :key="currentTaskId" class="cv-panel cv-event-details" @toggle="detailsOpen = ($event.currentTarget as HTMLDetailsElement).open">
        <summary>逐事件明细 · {{ events.length }} 条</summary>
        <div v-if="detailsOpen" class="cv-event-list">
          <button v-for="(event, index) in events" :key="index" @click="jumpTo(event.t_ms)">
            <time>{{ clock(event.t_ms / 1000) }}</time><span>{{ event.text || '画面事件' }}</span><small>{{ event.action_zh || eventLabels[event.type] || '事件' }}</small>
          </button>
        </div>
      </details>
      <section class="cv-panel cv-match-report" aria-label="场上人数变化">
        <header>场上人数变化 <span>人数随播放进度更新</span></header>
        <div class="cv-report-body" v-if="countEvents.length">
          <div class="cv-chart-legend"><span>● 检测人数</span><span>┊ 当前播放位置</span><b>{{ clock(currentTime) }} · {{ countNow ?? '—' }} 人</b></div>
          <div class="cv-count-plot" role="img" :aria-label="'检测人数变化，峰值 ' + peakCount + ' 人'">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polyline :points="chartLine" fill="none" stroke="#f089bd" stroke-width="2" vector-effect="non-scaling-stroke" /></svg>
            <i v-for="(point, index) in chartPoints" :key="index" :style="{ left: point.x + '%', top: point.y + '%' }"></i>
            <div class="cv-count-cursor" :style="{ left: pinPosition(currentTime * 1000) }"></div>
          </div>
          <div class="cv-time-ticks"><span v-for="tick in [0,.25,.5,.75,1]" :key="tick">{{ clock(tick * duration) }}</span></div>
          <footer>当前画面 {{ countNow ?? '—' }} 人 · 峰值 {{ peakCount }} 人</footer>
        </div>
        <p v-else class="cv-report-body">暂无人数检测记录。</p>
      </section>
    </main>

    <dialog ref="exportDialog" @close="exporting = false" class="cv-export-dialog" aria-label="导出解说">
      <h2>导出解说</h2>
      <p>{{ narration?.text }}</p>
      <small class="cv-audio-note">音频待测试：语音合成与浏览器朗读尚未完成端到端验证。</small>
      <NarrationSpeech :rate="playbackRate" v-if="exporting && narration?.status === 'ready'" :key="currentTaskId" :url="audioUrl" :text="narration.text" />
      <button class="cv-btn cv-outline" :disabled="downloading || narration?.status !== 'ready'" @click="downloadAudio">{{ downloading ? '正在准备 MP3…' : '下载 MP3' }}</button>
      <button class="cv-btn cv-primary" @click="exportNarration">下载文本</button>
      <button class="cv-btn cv-outline" @click="exportDialog?.close()">关闭</button>
      <small role="status">{{ audioError }}</small>
    </dialog>
    <div v-if="showUpload" class="cv-modal-backdrop" @click.self="closeUpload"><div class="cv-modal" role="dialog" aria-modal="true" aria-label="选择视频"><div class="cv-modal-head"><b>导入比赛视频</b><button @click="closeUpload">×</button></div><div class="cv-modal-body"><button class="cv-drop" type="button" :disabled="uploading" @click="fileInput?.click()" @dragover.prevent @drop.prevent="selectFile($event.dataTransfer?.files[0])">
        <span>{{ selectedFile ? '✓' : '＋' }}</span><b>{{ selectedFile ? '已选择 1 个视频' : '点击选择视频文件' }}</b><small>从本地文件夹挑选比赛录像 · 支持 MP4</small>
      </button>
      <div v-if="selectedFile" class="cv-file-row"><span aria-hidden="true">▶</span><div><b>{{ selectedFile.name }}</b><small>{{ (selectedFile.size / 1048576).toFixed(1) }} MB · {{ uploadDuration ? clock(uploadDuration) + ' · ' : '' }}MP4</small></div><button aria-label="移除视频" :disabled="uploading" @click="clearFile">×</button></div>
      <video v-if="uploadPreview" :key="uploadPreview" hidden preload="metadata" :src="uploadPreview" @loadedmetadata="uploadDuration = ($event.target as HTMLVideoElement).duration"></video>
      <input class="cv-import-input" v-model="videoName" aria-label="视频名称" maxlength="120" placeholder="给视频起个名字（可选）">
      <div class="cv-match-fields">
        <input class="cv-import-input" v-model="team1" aria-label="主队" maxlength="24" placeholder="主队（可选）">
        <input class="cv-import-input" v-model="team2" aria-label="客队" maxlength="24" placeholder="客队（可选）">
        <input class="cv-import-input" v-model="score" aria-label="比分" maxlength="12" placeholder="比分 如 102:98">
      </div><div v-if="uploading" class="cv-upload-progress"><span>正在上传 {{ uploadPercent }}%</span><div><i :style="{ width: `${uploadPercent}%` }"></i></div></div><p v-if="pageError" class="cv-modal-error">{{ pageError }}</p></div><div class="cv-modal-actions"><button class="cv-btn cv-outline" :disabled="uploading" @click="closeUpload">取消</button><button class="cv-btn cv-primary" :disabled="uploading || !selectedFile" @click="confirmUpload">{{ uploading ? '正在上传…' : '确认分析' }}</button></div></div></div>
  </div>
</template>
