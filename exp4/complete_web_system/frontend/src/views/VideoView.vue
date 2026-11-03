<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { storeToRefs } from 'pinia'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons-vue'
import {
  createTaskSocket,
  createVideoTask,
  getDetections,
  getEvents,
  getModelMeta,
  getTask,
  getTaskPreviewStatus,
  getTaskPreviewUrl,
  listTasks,
  type CommentaryEvent,
  type DetectionFrame,
  type ModelMeta,
  type TaskListItem,
  type TaskStatus,
} from '../api/client'
import { useTaskStore } from '../stores/task'

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024
const WINDOW_SECONDS = 15
const taskStore = useTaskStore()
const { task, commentary } = storeToRefs(taskStore)

const fileInput = ref<HTMLInputElement | null>(null)
const videoElement = ref<HTMLVideoElement | null>(null)
const canvasElement = ref<HTMLCanvasElement | null>(null)
const videoWrap = ref<HTMLElement | null>(null)
const selectedFile = shallowRef<File | null>(null)
const previewUrl = ref('')
const serverPreviewUrl = ref('')
const previewStatus = ref<'idle' | 'processing' | 'ready' | 'failed'>('idle')
const previewError = ref('')
const uploadPercent = ref(0)
const uploadBusy = ref(false)
const errorText = ref('')
const team1 = ref('')
const team2 = ref('')
const score1 = ref('')
const score2 = ref('')
const showBoxes = ref(true)
const detectionFrames = shallowRef<DetectionFrame[]>([])
const modelMeta = ref<ModelMeta | null>(null)
const recentTasks = ref<TaskListItem[]>([])
const loadedWindowStart = ref(-1)

let socket: WebSocket | null = null
let pollingTimer: number | undefined
let previewTimer: number | undefined
let animationFrame = 0
let requestToken = 0
let resizeObserver: ResizeObserver | undefined
let pendingEventTimeMs: number | null = null

const fileSizeLabel = computed(() => selectedFile.value ? formatBytes(selectedFile.value.size) : '')
const taskPercent = computed(() => Math.round((task.value?.progress || 0) * 100))
const stageLabel = computed(() => {
  const stage = task.value?.stage
  const labels: Record<string, string> = {
    queued: '等待处理', decoding: '读取视频', detecting: '检测球员',
    commentary: '整理解说', ready: '处理完成', failed: '处理失败',
  }
  return stage ? labels[stage] || stage : '等待上传'
})
const statusColor = computed(() => {
  if (task.value?.status === 'ready') return 'success'
  if (task.value?.status === 'failed') return 'error'
  if (task.value?.status === 'running') return 'processing'
  return 'default'
})
const taskIsActive = computed(() => task.value?.status === 'pending' || task.value?.status === 'running')

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatTime(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000)
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

function chooseFile() {
  fileInput.value?.click()
}

function acceptFile(file: File | undefined) {
  if (!file) return
  errorText.value = ''
  if (!file.name.toLowerCase().endsWith('.mp4')) {
    errorText.value = '当前版本仅接受 MP4 视频。'
    return
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    errorText.value = '视频超过 5 GiB 上传上限。'
    return
  }
  pendingEventTimeMs = null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  stopPreviewPolling()
  serverPreviewUrl.value = ''
  previewStatus.value = 'idle'
  previewError.value = ''
  stopSocket()
  stopPolling()
  resizeObserver?.disconnect()
  resizeObserver = undefined
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  taskStore.reset()
  detectionFrames.value = []
  loadedWindowStart.value = -1
  uploadPercent.value = 0
}

function handleFileInput(event: Event) {
  const target = event.target as HTMLInputElement
  acceptFile(target.files?.[0])
  target.value = ''
}

function handleDrop(event: DragEvent) {
  acceptFile(event.dataTransfer?.files?.[0])
}

function stopSocket() {
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close()
  socket = null
}

function stopPolling() {
  if (pollingTimer !== undefined) window.clearInterval(pollingTimer)
  pollingTimer = undefined
}

function stopPreviewPolling() {
  if (previewTimer !== undefined) window.clearInterval(previewTimer)
  previewTimer = undefined
}

async function switchToServerPreview(taskId: string) {
  const nextUrl = getTaskPreviewUrl(taskId)
  if (serverPreviewUrl.value === nextUrl) return
  const oldVideo = videoElement.value
  const currentTime = oldVideo?.currentTime || 0
  const wasPlaying = !!oldVideo && !oldVideo.paused
  serverPreviewUrl.value = nextUrl
  await nextTick()

  const video = videoElement.value
  if (!video) return
  const restorePlayback = () => {
    if (currentTime > 0 && Number.isFinite(video.duration)) {
      video.currentTime = Math.min(currentTime, Math.max(0, video.duration - 0.1))
    }
    if (wasPlaying) void video.play().catch(() => undefined)
  }
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA) restorePlayback()
  else video.addEventListener('loadedmetadata', restorePlayback, { once: true })
}

async function refreshPreviewStatus(taskId: string) {
  try {
    const result = await getTaskPreviewStatus(taskId)
    previewStatus.value = result.status
    if (result.status === 'ready') {
      previewError.value = ''
      stopPreviewPolling()
      if (result.converted || !previewUrl.value) await switchToServerPreview(taskId)
    } else if (result.status === 'failed') {
      previewError.value = result.error || '无法生成浏览器兼容预览。'
      stopPreviewPolling()
    }
  } catch {
    // Keep polling while the API reloads or the preview status is temporarily unavailable.
  }
}

function startPreviewPolling(taskId: string) {
  stopPreviewPolling()
  previewStatus.value = 'processing'
  previewTimer = window.setInterval(() => void refreshPreviewStatus(taskId), 1800)
  void refreshPreviewStatus(taskId)
}

function onVideoError() {
  if (serverPreviewUrl.value) {
    previewStatus.value = 'failed'
    previewError.value = '浏览器仍无法播放转换后的预览视频。'
    stopPreviewPolling()
    return
  }
  previewError.value = task.value?.task_id
    ? '原视频编码与浏览器不兼容，正在准备可播放的预览版本。'
    : '当前视频编码与浏览器不兼容；开始分析并上传后会自动准备预览版本。'
}

async function syncResult(taskId: string) {
  const [events] = await Promise.all([getEvents(taskId)])
  taskStore.setCommentary(events)
  loadedWindowStart.value = -1
  await loadDetectionWindow(true)
  void loadRecentTasks()
}

async function refreshTask(taskId: string) {
  try {
    const fresh = await getTask(taskId)
    taskStore.setTask(fresh)
    if (fresh.status === 'ready') {
      stopPolling()
      await syncResult(taskId)
    } else if (fresh.status === 'failed') {
      stopPolling()
      errorText.value = fresh.error || '视频处理失败。'
    }
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '读取任务状态失败。'
  }
}

function startTaskUpdates(taskId: string) {
  stopSocket()
  socket = createTaskSocket(taskId)
  socket.onmessage = event => {
    const data = JSON.parse(String(event.data)) as Record<string, unknown>
    if (data.type === 'progress') {
      const stage = String(data.stage || 'detecting')
      taskStore.setTask({
        ...(task.value as TaskStatus),
        status: stage === 'queued' ? 'pending' : 'running',
        stage,
        progress: Number(data.progress || 0),
        frames_done: Number(data.frames_done || task.value?.frames_done || 0),
        frames_total: data.frames_total == null ? task.value?.frames_total ?? null : Number(data.frames_total),
      })
    } else if (data.type === 'commentary') {
      taskStore.appendCommentary({
        t_ms: Number(data.t_ms || 0),
        type: String(data.event || 'commentary'),
        source: String(data.source || 'heuristic'),
        text: String(data.text || ''),
      })
    } else if (data.type === 'done') {
      void refreshTask(taskId)
    } else if (data.type === 'failed') {
      errorText.value = String(data.error || '视频处理失败。')
      if (task.value) taskStore.setTask({ ...task.value, status: 'failed', stage: 'failed', error: errorText.value })
      stopPolling()
    }
  }
  socket.onerror = () => {
    // The status poll remains active if the WebSocket cannot connect.
  }
}

function startPolling(taskId: string) {
  stopPolling()
  pollingTimer = window.setInterval(() => void refreshTask(taskId), 1800)
}

async function submitVideo() {
  const file = selectedFile.value
  if (!file || uploadBusy.value || taskIsActive.value) return
  errorText.value = ''
  previewError.value = ''
  serverPreviewUrl.value = ''
  previewStatus.value = 'processing'
  uploadBusy.value = true
  const form = new FormData()
  form.append('file', file)
  if (team1.value.trim()) form.append('team1', team1.value.trim())
  if (team2.value.trim()) form.append('team2', team2.value.trim())
  if (score1.value.trim()) form.append('score1', score1.value.trim())
  if (score2.value.trim()) form.append('score2', score2.value.trim())

  try {
    const created = await createVideoTask(form, percent => { uploadPercent.value = percent })
    taskStore.setTask({
      task_id: created.task_id,
      video_name: file.name,
      metadata: {
        team1: team1.value || null,
        team2: team2.value || null,
        score1: score1.value || null,
        score2: score2.value || null,
        frame_step: created.frame_step,
      },
      status: created.status,
      stage: 'queued',
      progress: 0,
      error: null,
      created_at: new Date().toISOString(),
      finished_at: null,
      frames_total: null,
      frames_done: 0,
      avg_infer_ms: null,
      total_seconds: null,
    })
    startPreviewPolling(created.task_id)
    startTaskUpdates(created.task_id)
    startPolling(created.task_id)
    void loadRecentTasks()
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '上传失败，请检查后端服务。'
  } finally {
    uploadBusy.value = false
  }
}

async function loadRecentTasks() {
  try {
    recentTasks.value = (await listTasks()).slice(0, 5)
  } catch {
    // Recent tasks are supplementary; keep the main upload workflow usable.
  }
}

async function openRecentTask(taskId: string) {
  stopSocket()
  stopPolling()
  stopPreviewPolling()
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  selectedFile.value = null
  serverPreviewUrl.value = ''
  previewStatus.value = 'processing'
  previewError.value = ''
  errorText.value = ''

  try {
    const existingTask = await getTask(taskId)
    taskStore.setTask(existingTask)
    if (existingTask.status === 'ready') {
      void syncResult(taskId)
    } else if (existingTask.status === 'pending' || existingTask.status === 'running') {
      startTaskUpdates(taskId)
      startPolling(taskId)
    }
    startPreviewPolling(taskId)
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '无法打开最近任务。'
  }
}

async function loadDetectionWindow(force = false) {
  const taskId = task.value?.task_id
  const video = videoElement.value
  if (!taskId || task.value?.status !== 'ready' || !video) return
  const start = Math.floor(video.currentTime / WINDOW_SECONDS) * WINDOW_SECONDS
  if (!force && start === loadedWindowStart.value) return
  const token = ++requestToken
  loadedWindowStart.value = start
  try {
    const result = await getDetections(taskId, start, start + WINDOW_SECONDS)
    if (token !== requestToken) return
    detectionFrames.value = result
  } catch (error) {
    if (token === requestToken) loadedWindowStart.value = -1
    errorText.value = error instanceof Error ? error.message : '读取检测框失败。'
  }
}

function resizeOverlay() {
  const video = videoElement.value
  const canvas = canvasElement.value
  if (!video || !canvas) return
  const rect = video.getBoundingClientRect()
  const ratio = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.round(rect.width * ratio))
  canvas.height = Math.max(1, Math.round(rect.height * ratio))
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`
  const context = canvas.getContext('2d')
  context?.setTransform(ratio, 0, 0, ratio, 0, 0)
}

function drawOverlay() {
  animationFrame = window.requestAnimationFrame(drawOverlay)
  const video = videoElement.value
  const canvas = canvasElement.value
  if (!video || !canvas) return
  const rect = video.getBoundingClientRect()
  const context = canvas.getContext('2d')
  if (!context) return
  const ratio = window.devicePixelRatio || 1
  context.clearRect(0, 0, canvas.width / ratio, canvas.height / ratio)
  if (!showBoxes.value || !detectionFrames.value.length) return

  const currentMs = video.currentTime * 1000
  let frame: DetectionFrame | undefined
  for (const candidate of detectionFrames.value) {
    if (candidate.t_ms <= currentMs) frame = candidate
    else break
  }
  if (!frame) return

  const scaleX = rect.width
  const scaleY = rect.height
  context.lineWidth = 2
  context.font = '600 11px DM Sans, sans-serif'
  for (const box of frame.boxes) {
    const width = box.w * scaleX
    const height = box.h * scaleY
    const x = (box.cx - box.w / 2) * scaleX
    const y = (box.cy - box.h / 2) * scaleY
    context.strokeStyle = '#ff9b55'
    context.strokeRect(x, y, width, height)
    const label = `#${box.track_id ?? '?'}  ${Math.round(box.conf * 100)}%`
    const labelWidth = context.measureText(label).width + 12
    context.fillStyle = '#f08b43'
    context.fillRect(x, Math.max(0, y - 21), labelWidth, 20)
    context.fillStyle = '#fff'
    context.fillText(label, x + 6, Math.max(0, y - 7))
  }
}

function onVideoReady() {
  applyPendingEventSeek()
  resizeOverlay()
  if (!resizeObserver && videoWrap.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resizeOverlay)
    resizeObserver.observe(videoWrap.value)
  }
  void loadDetectionWindow(true)
}

function onTimeChange() {
  void loadDetectionWindow()
}

function seekToEventTime(video: HTMLVideoElement, timestampMs: number) {
  const targetSeconds = Math.max(0, timestampMs / 1000)
  const lastSeekableSecond = Number.isFinite(video.duration)
    ? Math.max(0, video.duration - 0.05)
    : targetSeconds
  video.currentTime = Math.min(targetSeconds, lastSeekableSecond)
  void video.play().catch(() => undefined)
}

function applyPendingEventSeek() {
  const video = videoElement.value
  if (
    pendingEventTimeMs === null
    || !video
    || video.readyState < HTMLMediaElement.HAVE_METADATA
  ) return

  const timestampMs = pendingEventTimeMs
  pendingEventTimeMs = null
  seekToEventTime(video, timestampMs)
}

function jumpToEvent(event: CommentaryEvent) {
  if (!Number.isFinite(event.t_ms) || event.t_ms < 0) return
  pendingEventTimeMs = event.t_ms
  applyPendingEventSeek()
}

function resetTask() {
  stopSocket()
  stopPolling()
  stopPreviewPolling()
  pendingEventTimeMs = null
  taskStore.reset()
  errorText.value = ''
  previewStatus.value = 'idle'
  previewError.value = ''
  serverPreviewUrl.value = ''
  detectionFrames.value = []
  loadedWindowStart.value = -1
}

onMounted(async () => {
  animationFrame = window.requestAnimationFrame(drawOverlay)
  void loadRecentTasks()
  if (task.value) {
    const taskId = task.value.task_id
    try {
      taskStore.setTask(await getTask(taskId))
    } catch {
      // A saved task may have been removed from the backend.
    }
    if (taskIsActive.value) {
      startTaskUpdates(taskId)
      startPolling(taskId)
    } else if (task.value?.status === 'ready') {
      void syncResult(taskId)
    }
    startPreviewPolling(taskId)
  }
  try {
    modelMeta.value = await getModelMeta()
  } catch {
    modelMeta.value = null
  }
})

onBeforeUnmount(() => {
  stopSocket()
  stopPolling()
  stopPreviewPolling()
  pendingEventTimeMs = null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  window.cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
})

</script>

<template>
  <div class="video-dashboard">
    <section class="welcome-row">
      <div>
        <div class="welcome-kicker"><span class="kicker-line"></span> COURT-SIDE VIDEO ANALYSIS</div>
        <h2>让比赛画面，变成可读的解说。</h2>
        <p>上传一段比赛视频，系统将在后台检测球员并生成带时间戳的画面描述。</p>
      </div>
      <div class="model-chip">
        <span class="model-chip-icon"><ThunderboltOutlined /></span>
        <div><small>当前视觉模型</small><strong>{{ modelMeta?.name || 'YOLOv8n' }} <em>· PLAYER</em></strong></div>
      </div>
    </section>

    <a-alert v-if="errorText" class="error-alert" type="error" show-icon closable :message="errorText" @close="errorText = ''" />

    <div class="workspace-grid">
      <main class="primary-column">
        <a-card class="upload-card" :bordered="false">
          <template #title>
            <div class="card-heading"><span class="step-index">01</span><span>添加比赛视频</span></div>
          </template>
          <template #extra><span class="format-label">MP4 · 最大 5 GiB</span></template>

          <div
            v-if="!selectedFile"
            class="drop-zone"
            @click="chooseFile"
            @dragover.prevent
            @drop.prevent="handleDrop"
          >
            <input ref="fileInput" type="file" accept="video/mp4,.mp4" hidden @click.stop @change="handleFileInput" />
            <div class="upload-icon"><CloudUploadOutlined /></div>
            <strong>将比赛视频拖到这里</strong>
            <span>或点击选择本地 MP4 文件</span>
            <small>建议使用横屏视频；视频越长，分析等待时间越久</small>
          </div>

          <div v-else class="selected-file-row">
            <div class="file-icon"><VideoCameraOutlined /></div>
            <div class="file-details">
              <strong>{{ selectedFile.name }}</strong>
              <span>{{ fileSizeLabel }} <i>·</i> MP4 视频</span>
            </div>
            <a-button v-if="!taskIsActive && !uploadBusy" type="text" class="replace-button" @click="chooseFile">更换</a-button>
            <input ref="fileInput" type="file" accept="video/mp4,.mp4" hidden @click.stop @change="handleFileInput" />
          </div>

          <div class="game-fields">
            <div class="fields-caption">比赛信息 <span>选填，仅作为页面备注</span></div>
            <div class="fields-grid">
              <a-input v-model:value="team1" placeholder="主队名称" :disabled="taskIsActive" />
              <a-input v-model:value="team2" placeholder="客队名称" :disabled="taskIsActive" />
              <a-input v-model:value="score1" placeholder="主队比分" :disabled="taskIsActive" />
              <a-input v-model:value="score2" placeholder="客队比分" :disabled="taskIsActive" />
            </div>
            <div class="field-hint">当前模型只检测球员框，不识别队名、比分或具体投篮动作。</div>
          </div>

          <div class="upload-actions">
            <a-button
              v-if="!task || task.status === 'failed' || task.status === 'ready'"
              type="primary"
              size="large"
              :loading="uploadBusy"
              :disabled="!selectedFile"
              @click="submitVideo"
            >
              <template #icon><PlayCircleOutlined /></template>
              {{ task?.status === 'ready' || task?.status === 'failed' ? '重新分析视频' : '开始分析' }}
            </a-button>
            <a-button v-if="task && !taskIsActive && !uploadBusy" size="large" @click="resetTask">清空当前任务</a-button>
            <span v-if="uploadBusy" class="upload-percent">上传中 {{ uploadPercent }}%</span>
          </div>
          <a-progress v-if="uploadBusy" :percent="uploadPercent" :show-info="false" size="small" />
        </a-card>

        <a-card v-if="task" class="task-card" :bordered="false">
          <template #title>
            <div class="card-heading"><span class="step-index">02</span><span>分析进度</span></div>
          </template>
          <template #extra><a-tag :color="statusColor">{{ stageLabel }}</a-tag></template>
          <div class="task-overview">
            <div class="task-id"><span>任务编号</span><code>{{ task.task_id }}</code></div>
            <div class="task-stat"><span>已分析采样帧</span><strong>{{ task.frames_done.toLocaleString() }}<small v-if="task.frames_total"> / {{ task.frames_total.toLocaleString() }}</small></strong></div>
            <div class="task-stat"><span>平均推理</span><strong>{{ task.avg_infer_ms ? `${task.avg_infer_ms.toFixed(1)} ms` : '—' }}</strong></div>
            <div class="task-stat"><span>抽帧间隔</span><strong>每 {{ task.metadata.frame_step ?? '—' }} 帧</strong></div>
          </div>
          <a-progress :percent="taskPercent" :status="task.status === 'failed' ? 'exception' : task.status === 'ready' ? 'success' : 'active'" />
          <div class="progress-caption">
            <span><LoadingOutlined v-if="taskIsActive" /> <CheckCircleOutlined v-else-if="task.status === 'ready'" /> {{ stageLabel }}</span>
            <span>{{ taskPercent }}%</span>
          </div>
        </a-card>

        <a-card v-if="selectedFile || task" class="playback-card" :bordered="false">
          <template #title>
            <div class="card-heading"><span class="step-index">03</span><span>视频回放与检测框</span></div>
          </template>
          <template #extra>
            <a-switch v-model:checked="showBoxes" size="small" />
            <span class="switch-label">显示检测框</span>
          </template>
          <div ref="videoWrap" class="video-wrap">
            <video
              v-if="previewUrl || serverPreviewUrl"
              ref="videoElement"
              :src="serverPreviewUrl || previewUrl"
              controls
              playsinline
              @loadedmetadata="onVideoReady"
              @timeupdate="onTimeChange"
              @seeked="onTimeChange"
              @error="onVideoError"
            ></video>
            <canvas ref="canvasElement" class="detection-canvas"></canvas>
            <div v-if="previewError || (previewStatus === 'processing' && task?.status === 'ready')" class="video-state-overlay">
              <span class="video-state-icon"><ClockCircleOutlined /></span>
              <strong>{{ previewStatus === 'processing' ? '正在准备浏览器预览' : '暂时无法播放视频' }}</strong>
              <span>{{ previewError || '原始文件保留用于分析，完成后播放器会自动切换到兼容预览。' }}</span>
            </div>
            <div v-else-if="task?.status !== 'ready'" class="video-state-overlay">
              <span class="video-state-icon"><ClockCircleOutlined /></span>
              <strong>{{ taskIsActive ? '视频正在分析' : '等待分析后显示检测框' }}</strong>
              <span>{{ taskIsActive ? '完成后可在时间轴回看球员检测结果' : '选择文件后点击“开始分析”' }}</span>
            </div>
            <div v-else class="frame-counter">{{ detectionFrames.length }} 帧数据已载入</div>
          </div>
          <div class="playback-footnote">
            <span><i class="legend-box"></i>球员检测框</span>
            <span>原视频叠加检测框；不兼容编码会自动转换预览</span>
          </div>
        </a-card>
      </main>

      <aside class="secondary-column">
        <a-card class="commentary-card" :bordered="false">
          <template #title>
            <div class="card-heading"><span class="commentary-live"></span><span>解说时间轴</span></div>
          </template>
          <template #extra><span class="timeline-count">{{ commentary.length }} 条</span></template>
          <div v-if="commentary.length" class="timeline-list">
            <button v-for="(item, index) in commentary" :key="`${item.t_ms}-${index}`" class="timeline-item" type="button" :title="`点击跳转到 ${formatTime(item.t_ms)} 并播放`" :aria-label="`跳转到 ${formatTime(item.t_ms)}：${item.text}`" @click="jumpToEvent(item)">
              <span class="timeline-time">{{ formatTime(item.t_ms) }}</span>
              <span class="timeline-marker"><i></i></span>
              <span class="timeline-copy">
                <strong>{{ item.text }}</strong>
                <small>启发式画面观察 · 点击跳转播放</small>
              </span>
            </button>
          </div>
          <a-empty v-else class="empty-timeline">
            <template #description>
              <span>{{ taskIsActive ? '视频分析完成后，解说片段会显示在这里。' : '上传并分析视频后，查看带时间戳的画面描述。' }}</span>
            </template>
          </a-empty>
          <div v-if="commentary.length" class="ai-note">
            <span class="ai-note-mark">AI</span>
            <p>解说由球员检测结果整理，仅描述画面可见人数；不代表球员身份或比赛动作。</p>
          </div>
        </a-card>

        <a-card class="model-card" :bordered="false">
          <template #title><div class="card-heading"><span class="model-small-icon"><ThunderboltOutlined /></span><span>模型信息</span></div></template>
          <div class="model-title-row"><strong>{{ modelMeta?.name || 'YOLOv8n' }}</strong><span class="model-status">{{ modelMeta ? modelMeta.weights_available ? '权重已就绪' : '权重未找到' : '读取中' }}</span></div>
          <div class="model-metrics">
            <div><span>参数量</span><strong>{{ modelMeta?.parameters || '3.2M' }}</strong></div>
            <div><span>mAP50</span><strong>{{ modelMeta ? modelMeta.map50.toFixed(3) : '0.418' }}</strong></div>
            <div><span>检测类别</span><strong>Player</strong></div>
          </div>
          <div class="device-note"><span class="device-dot"></span>Worker 自动选择可用的 CUDA 或 CPU</div>
        </a-card>

        <a-card class="history-card" :bordered="false">
          <template #title><div class="card-heading"><span class="history-icon"><ReloadOutlined /></span><span>最近任务</span></div></template>
          <div v-if="recentTasks.length" class="recent-list">
            <button v-for="item in recentTasks" :key="item.task_id" class="recent-item" type="button" @click="openRecentTask(item.task_id)">
              <span class="recent-file"><VideoCameraOutlined /></span>
              <span class="recent-copy"><strong>{{ item.video_name }}</strong><small>{{ new Date(item.created_at).toLocaleString() }}</small></span>
              <a-tag :color="item.status === 'ready' ? 'success' : item.status === 'failed' ? 'error' : 'processing'">{{ item.status === 'ready' ? '完成' : item.status === 'failed' ? '失败' : '处理中' }}</a-tag>
            </button>
          </div>
          <a-empty v-else description="暂无分析记录" />
        </a-card>

        <div class="privacy-note"><span>本地处理</span><p>视频文件保存在本机后端的任务目录中。任务记录可在列表中查看。</p></div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.video-dashboard { max-width: 1500px; margin: 0 auto; }
.welcome-row { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin: 2px 0 24px; }
.welcome-kicker { display: flex; align-items: center; gap: 8px; color: #a07550; font: 10px 'DM Mono', monospace; letter-spacing: 1.2px; }
.kicker-line { width: 18px; height: 1px; background: #df9d6c; }
.welcome-row h2 { margin: 10px 0 7px; color: #172334; font-size: clamp(23px, 2.1vw, 30px); font-weight: 700; letter-spacing: -.8px; }
.welcome-row p { color: #8994a3; font-size: 12px; }
.model-chip { display: flex; flex: 0 0 auto; align-items: center; gap: 12px; padding: 12px 15px; border: 1px solid #e9edf2; border-radius: 12px; background: rgba(255,255,255,.8); }
.model-chip-icon, .model-small-icon { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 10px; color: #bd7540; background: #fff1e5; }
.model-chip div { display: flex; flex-direction: column; gap: 2px; }
.model-chip small { color: #9aa4b2; font-size: 9px; }
.model-chip strong { color: #293648; font-size: 12px; }
.model-chip em { color: #a3acb8; font-size: 9px; font-style: normal; font-weight: 500; }
.error-alert { margin-bottom: 16px; border-radius: 10px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(275px, .82fr); align-items: start; gap: 18px; }
.primary-column, .secondary-column { display: flex; min-width: 0; flex-direction: column; gap: 16px; }
.card-heading { display: flex; align-items: center; gap: 10px; }
.step-index { display: grid; width: 25px; height: 25px; place-items: center; border-radius: 8px; color: #b86e3d; background: #fff2e7; font: 10px 'DM Mono', monospace; }
.format-label, .timeline-count { color: #9aa4b1; font: 10px 'DM Mono', monospace; }
.drop-zone { display: flex; min-height: 178px; flex-direction: column; align-items: center; justify-content: center; border: 1px dashed #d6dde7; border-radius: 11px; background: #fafbfd; cursor: pointer; transition: border .2s, background .2s; }
.drop-zone:hover { border-color: #e5a26e; background: #fffaf5; }
.upload-icon { display: grid; width: 43px; height: 43px; place-items: center; margin-bottom: 11px; border-radius: 13px; color: #bd7540; background: #fff0e4; font-size: 19px; }
.drop-zone strong { color: #334154; font-size: 13px; }
.drop-zone span { margin-top: 4px; color: #919cad; font-size: 11px; }
.drop-zone small { margin-top: 13px; color: #a9b2bf; font-size: 9px; }
.selected-file-row { display: flex; align-items: center; gap: 12px; min-height: 65px; padding: 11px 13px; border: 1px solid #edf0f4; border-radius: 10px; background: #fafbfd; }
.file-icon { display: grid; width: 39px; height: 39px; place-items: center; border-radius: 10px; color: #b96e39; background: #fff0e4; font-size: 17px; }
.file-details { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 4px; }
.file-details strong { overflow: hidden; color: #344155; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.file-details span { color: #99a3b1; font-size: 10px; }
.file-details i { margin: 0 5px; color: #ccd2da; font-style: normal; }
.replace-button { color: #986540; font-size: 11px; }
.game-fields { margin-top: 22px; }
.fields-caption { margin-bottom: 9px; color: #4c5a6d; font-size: 10px; font-weight: 700; }
.fields-caption span { margin-left: 7px; color: #a1aab6; font-size: 9px; font-weight: 400; }
.fields-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.fields-grid :deep(.ant-input) { height: 34px; border-color: #e8ecf1; border-radius: 8px; font-size: 10px; }
.field-hint { margin-top: 8px; color: #a0aab7; font-size: 9px; }
.upload-actions { display: flex; align-items: center; gap: 10px; margin-top: 20px; }
.upload-actions :deep(.ant-btn) { height: 39px; border-radius: 9px; font-size: 11px; }
.upload-percent { color: #748095; font: 10px 'DM Mono', monospace; }
.task-overview { display: grid; grid-template-columns: 1.5fr repeat(3, 1fr); gap: 10px; margin: 2px 0 18px; }
.task-id, .task-stat { display: flex; min-width: 0; flex-direction: column; gap: 5px; }
.task-id span, .task-stat span { color: #9aa4b2; font-size: 9px; }
.task-id code { overflow: hidden; color: #58677a; font: 9px 'DM Mono', monospace; text-overflow: ellipsis; }
.task-stat strong { color: #3c4a5d; font: 600 11px 'DM Mono', monospace; }
.task-stat small { color: #9aa4b2; font-size: 9px; }
.progress-caption { display: flex; justify-content: space-between; margin-top: 3px; color: #7b8797; font-size: 10px; }
.progress-caption .anticon { margin-right: 5px; color: #d8874d; }
.playback-card :deep(.ant-card-extra) { display: flex; align-items: center; }
.switch-label { margin-left: 7px; color: #7f8b9c; font-size: 10px; }
.video-wrap { position: relative; overflow: hidden; border-radius: 10px; background: #0e1723; line-height: 0; }
.video-wrap video { display: block; width: 100%; height: auto; max-height: 540px; object-fit: contain; }
.detection-canvas { position: absolute; top: 0; left: 0; pointer-events: none; }
.video-state-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #fff; background: rgba(8, 15, 24, .52); text-align: center; line-height: 1.4; pointer-events: none; }
.video-state-icon { display: grid; width: 38px; height: 38px; place-items: center; border: 1px solid rgba(255,255,255,.2); border-radius: 50%; color: #f1a36c; font-size: 16px; }
.video-state-overlay strong { font-size: 12px; }
.video-state-overlay > span:last-child { color: #bdc8d6; font-size: 10px; }
.frame-counter { position: absolute; right: 10px; bottom: 43px; padding: 5px 8px; border-radius: 6px; color: #f5f6f7; background: rgba(8, 15, 24, .68); font: 9px 'DM Mono', monospace; line-height: 1; }
.playback-footnote { display: flex; justify-content: space-between; margin-top: 11px; color: #9ca6b2; font-size: 9px; }
.playback-footnote > span:first-child { display: flex; align-items: center; gap: 7px; color: #7d8897; }
.legend-box { width: 10px; height: 9px; border: 1.5px solid #ee9556; }
.commentary-live { width: 8px; height: 8px; border-radius: 50%; background: #4ab48c; box-shadow: 0 0 0 4px #e7f5ef; }
.empty-timeline { margin: 28px 0 36px; color: #97a2b1; font-size: 10px; }
.timeline-list { max-height: 415px; overflow: auto; }
.timeline-item { display: grid; width: 100%; grid-template-columns: 45px 16px minmax(0, 1fr); gap: 9px; padding: 12px 1px; border: 0; border-bottom: 1px solid #f0f2f6; background: transparent; text-align: left; cursor: pointer; }
.timeline-item:hover .timeline-copy strong { color: #b46b3a; }
.timeline-item:focus-visible { outline: 2px solid #e79155; outline-offset: -2px; border-radius: 6px; }
.timeline-time { padding-top: 1px; color: #b47a50; font: 10px 'DM Mono', monospace; }
.timeline-marker { position: relative; display: flex; justify-content: center; }
.timeline-marker::before { position: absolute; top: 0; bottom: -13px; width: 1px; background: #e9edf2; content: ''; }
.timeline-item:last-child .timeline-marker::before { bottom: 12px; }
.timeline-marker i { z-index: 1; width: 7px; height: 7px; margin-top: 4px; border: 2px solid #fff; border-radius: 50%; background: #e79155; box-shadow: 0 0 0 1px #e79155; }
.timeline-copy { display: flex; flex-direction: column; gap: 5px; }
.timeline-copy strong { color: #465367; font-size: 10px; font-weight: 500; line-height: 1.5; }
.timeline-copy small { color: #a2acb8; font-size: 8px; }
.ai-note { display: flex; gap: 9px; margin-top: 14px; padding: 10px; border-radius: 8px; background: #f7f8fa; }
.ai-note-mark { display: grid; width: 21px; height: 21px; flex: 0 0 auto; place-items: center; border-radius: 6px; color: #94633e; background: #f6e6d7; font: 8px 'DM Mono', monospace; }
.ai-note p { color: #8792a1; font-size: 9px; line-height: 1.55; }
.model-title-row { display: flex; align-items: center; justify-content: space-between; }
.model-title-row > strong { color: #344154; font-size: 13px; }
.model-status { color: #29916d; font-size: 9px; }
.model-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 15px; padding: 12px 0; border-top: 1px solid #f0f2f5; border-bottom: 1px solid #f0f2f5; }
.model-metrics div { display: flex; flex-direction: column; gap: 5px; }
.model-metrics span { color: #9ba5b2; font-size: 8px; }
.model-metrics strong { color: #47566a; font: 600 10px 'DM Mono', monospace; }
.device-note { display: flex; align-items: center; gap: 7px; margin-top: 12px; color: #8994a2; font-size: 9px; }
.device-dot { width: 6px; height: 6px; border-radius: 50%; background: #45a983; }
.model-small-icon { width: 22px; height: 22px; border-radius: 7px; font-size: 11px; }
.history-icon { color: #8998a9; font-size: 13px; }
.recent-list { display: flex; flex-direction: column; }
.recent-item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 10px 0; border: 0; border-bottom: 1px solid #f0f2f6; background: transparent; text-align: left; cursor: pointer; }
.recent-item:hover .recent-copy strong { color: #b46b3a; }
.recent-item:last-child { border-bottom: 0; }
.recent-file { display: grid; width: 29px; height: 29px; flex: 0 0 auto; place-items: center; border-radius: 8px; color: #a66a42; background: #fff2e8; font-size: 12px; }
.recent-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }
.recent-copy strong { overflow: hidden; color: #59677a; font-size: 9px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.recent-copy small { color: #aab3bf; font-size: 8px; }
.recent-item :deep(.ant-tag) { margin: 0; padding-inline: 5px; font-size: 8px; }
.privacy-note { padding: 12px 13px; border: 1px solid #e9edf2; border-radius: 10px; background: rgba(255,255,255,.55); }
.privacy-note span { color: #69778b; font-size: 9px; font-weight: 700; }
.privacy-note p { margin-top: 5px; color: #9aa4b2; font-size: 9px; line-height: 1.6; }

@media (max-width: 1050px) {
  .workspace-grid { grid-template-columns: minmax(0, 1.4fr) minmax(250px, .9fr); gap: 13px; }
  .page-content { padding-inline: 25px; }
  .fields-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .welcome-row { align-items: start; flex-direction: column; }
  .model-chip { align-self: stretch; }
  .workspace-grid { grid-template-columns: 1fr; }
  .secondary-column { grid-row: auto; }
  .task-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .task-id { grid-column: 1 / -1; }
}
@media (max-width: 450px) {
  .task-overview { grid-template-columns: 1fr 1fr; }
  .task-id { grid-column: 1 / -1; }
  .format-label { font-size: 8px; }
  .upload-actions { flex-wrap: wrap; }
}
</style>
