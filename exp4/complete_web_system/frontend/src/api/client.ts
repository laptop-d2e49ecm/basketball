import axios, { type AxiosProgressEvent, type AxiosResponse } from 'axios'

export interface ApiEnvelope<T> {
  code: number
  result: T
  msg: string
}

export type TaskState = 'pending' | 'running' | 'ready' | 'failed'

export interface TaskCreated {
  task_id: string
  status: TaskState
  frame_step: number
}

export interface TaskStatus {
  task_id: string
  video_name: string
  metadata: Record<string, string | number | null>
  status: TaskState
  stage: string
  progress: number
  error: string | null
  created_at: string
  finished_at: string | null
  frames_total: number | null
  frames_done: number
  avg_infer_ms: number | null
  total_seconds: number | null
}

export interface TaskPreviewStatus {
  status: 'processing' | 'ready' | 'failed'
  converted: boolean
  error: string | null
}

export interface TaskListItem {
  task_id: string
  video_name: string
  status: TaskState
  stage: string
  progress: number
  created_at: string
  finished_at: string | null
}

export interface DeleteTaskResult {
  task_id: string
  deleted: boolean
}

export interface DetectionBox {
  cx: number
  cy: number
  w: number
  h: number
  conf: number
  track_id: number | null
}

export interface DetectionFrame {
  frame_idx: number
  t_ms: number
  image_w: number
  image_h: number
  boxes: DetectionBox[]
}

export interface CommentaryEvent {
  t_ms: number
  type: string
  source: string
  player_count?: number
  track_ids?: number[]
  text: string
  action?: string | null
  action_zh?: string | null
  conf?: number | null
  track_id?: number | null
  scene?: string | null
}

export interface NarrationSection {
  start_ms: number
  end_ms: number
  event_count: number
  text: string
}

export interface TaskNarration {
  created_at?: string
  task_id: string
  status: 'pending' | 'not_started' | 'running' | 'ready' | 'failed' | 'empty'
  event_count?: number
  text: string
  sections: NarrationSection[]
  error?: string | null
}

export interface ModelMeta {
  name: string
  parameters: string
  map50: number
  classes: string[]
  weights_available: boolean
  avg_infer_ms: number | null
}

export interface ImageDetectionBox {
  cx: number
  cy: number
  w: number
  h: number
  conf: number
}

export interface ImageDetectionResult {
  boxes: ImageDetectionBox[]
  player_count: number
  dropped_boxes: number
  image_w: number
  image_h: number
  conf_thr: number
  iou_thr: number
  infer_ms: number
  total_ms: number
}

export interface ImageBatchCreated {
  task_id: string
  total: number
  backend: 'background'
}

export interface ImageBatchItem {
  filename: string
  ok: boolean
  player_count: number | null
  error: string | null
}

export interface ImageBatchStatus {
  task_id: string
  status: 'running' | 'done'
  done: number
  total: number
  results: ImageBatchItem[]
}

export interface TextClassificationResult {
  label: string
  is_basketball_text: boolean
  confidence: number
  top3: Array<{ label: string; prob: number }>
  chars: number
  infer_ms: number
}

export interface ImageTextMatchResult {
  match: boolean
  image_side: {
    is_court: boolean
    player_count: number
    avg_conf: number
    infer_ms: number
  }
  text_side: {
    label: string
    is_basketball_text: boolean
    confidence: number
  }
  evidence: string[]
  total_ms: number
}

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
})

function unwrap<T>(response: AxiosResponse<ApiEnvelope<T>>): T {
  if (response.data.code !== 0) {
    throw new Error(response.data.msg || '请求失败')
  }
  return response.data.result
}

function apiError(error: unknown): Error {
  if (axios.isAxiosError<ApiEnvelope<unknown>>(error)) {
    if (error.response?.status === 405) {
      return new Error('当前后端尚未加载任务删除功能。请停止旧后端并重新运行 start_project_v3.bat 后再试。')
    }
    const responseData = error.response?.data as (ApiEnvelope<unknown> & { detail?: string }) | undefined
    return new Error(responseData?.msg || responseData?.detail || error.message || '无法连接后端服务')
  }
  return error instanceof Error ? error : new Error('请求失败')
}

export async function createVideoTask(
  form: FormData,
  onProgress: (percent: number) => void,
): Promise<TaskCreated> {
  try {
    const response = await http.post<ApiEnvelope<TaskCreated>>('/tasks', form, {
      timeout: 0,
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (event.total) onProgress(Math.round((event.loaded / event.total) * 100))
      },
    })
    return unwrap(response)
  } catch (error) {
    throw apiError(error)
  }
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  try {
    return unwrap(await http.get<ApiEnvelope<TaskStatus>>(`/tasks/${taskId}`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function getTaskPreviewStatus(taskId: string): Promise<TaskPreviewStatus> {
  try {
    return unwrap(await http.get<ApiEnvelope<TaskPreviewStatus>>(`/tasks/${taskId}/preview/status`))
  } catch (error) {
    throw apiError(error)
  }
}

export function getTaskPreviewUrl(taskId: string): string {
  return `/api/v1/tasks/${encodeURIComponent(taskId)}/preview`
}

export function getTaskFrameUrl(taskId: string, timeMs: number): string {
  return `/api/v1/tasks/${encodeURIComponent(taskId)}/frame?t_ms=${Math.max(0, Math.round(timeMs))}`
}

export async function getNarration(taskId: string): Promise<TaskNarration> {
  try {
    return unwrap(await http.get<ApiEnvelope<TaskNarration>>(`/tasks/${encodeURIComponent(taskId)}/narration`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function retryNarration(taskId: string): Promise<{ task_id: string; status: string }> {
  try {
    return unwrap(await http.post<ApiEnvelope<{ task_id: string; status: string }>>(`/tasks/${encodeURIComponent(taskId)}/narration/retry`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function listTasks(): Promise<TaskListItem[]> {
  try {
    return unwrap(await http.get<ApiEnvelope<TaskListItem[]>>('/tasks'))
  } catch (error) {
    throw apiError(error)
  }
}

export async function deleteTask(taskId: string): Promise<DeleteTaskResult> {
  try {
    return unwrap(await http.delete<ApiEnvelope<DeleteTaskResult>>(`/tasks/${encodeURIComponent(taskId)}`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function getDetections(
  taskId: string,
  startSeconds: number,
  endSeconds: number,
): Promise<DetectionFrame[]> {
  try {
    return unwrap(
      await http.get<ApiEnvelope<DetectionFrame[]>>(`/tasks/${taskId}/detections`, {
        params: { t_start: startSeconds, t_end: endSeconds },
      }),
    )
  } catch (error) {
    throw apiError(error)
  }
}

export async function getEvents(taskId: string): Promise<CommentaryEvent[]> {
  try {
    return unwrap(await http.get<ApiEnvelope<CommentaryEvent[]>>(`/tasks/${taskId}/events`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function getModelMeta(): Promise<ModelMeta> {
  try {
    return unwrap(await http.get<ApiEnvelope<ModelMeta>>('/meta/model'))
  } catch (error) {
    throw apiError(error)
  }
}

export async function detectImage(
  file: File,
  conf = 0.25,
  iou = 0.55,
): Promise<ImageDetectionResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  try {
    return unwrap(await http.post<ApiEnvelope<ImageDetectionResult>>('/detect', form))
  } catch (error) {
    throw apiError(error)
  }
}

export async function detectImageBatch(files: File[]): Promise<ImageBatchCreated> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  try {
    return unwrap(await http.post<ApiEnvelope<ImageBatchCreated>>('/detect/batch', form))
  } catch (error) {
    throw apiError(error)
  }
}

export async function getImageBatch(taskId: string): Promise<ImageBatchStatus> {
  try {
    return unwrap(await http.get<ApiEnvelope<ImageBatchStatus>>(`/batch/${encodeURIComponent(taskId)}`))
  } catch (error) {
    throw apiError(error)
  }
}

export async function classifyCommentary(text: string): Promise<TextClassificationResult> {
  try {
    return unwrap(
      await http.post<ApiEnvelope<TextClassificationResult>>('/text/classify', { text }),
    )
  } catch (error) {
    throw apiError(error)
  }
}

export async function matchImageAndCommentary(
  file: File,
  text: string,
  conf = 0.25,
): Promise<ImageTextMatchResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('text', text)
  form.append('conf', String(conf))
  try {
    return unwrap(await http.post<ApiEnvelope<ImageTextMatchResult>>('/match', form))
  } catch (error) {
    throw apiError(error)
  }
}

/* ---------------- 实验5：AI 解说 Agent（契约 exp5/CONTRACT.md） ---------------- */

export interface AgentToolCall {
  tool: string
  args: Record<string, unknown>
  status: 'ok' | 'error'
  result_summary: string
  elapsed_ms: number | null
}

export interface AgentChatResult {
  session_id: string
  task_id?: string | null
  agent: string
  tool_calls: AgentToolCall[]
  elapsed_ms: number
  provider: string
}

export class AgentApiError extends Error {
  code: number

  constructor(code: number, text: string) {
    super(text)
    this.name = 'AgentApiError'
    this.code = code
  }
}

export async function agentChat(payload: {
  message: string
  session_id?: string
  task_id?: string
}): Promise<AgentChatResult> {
  try {
    const response = await http.post<ApiEnvelope<AgentChatResult>>('/agent/chat', payload, {
      timeout: 60_000,
    })
    return unwrap(response)
  } catch (error) {
    if (axios.isAxiosError<ApiEnvelope<unknown>>(error)) {
      const status = error.response?.status ?? 0
      const data = error.response?.data as (ApiEnvelope<unknown> & { detail?: string }) | undefined
      throw new AgentApiError(status, data?.msg || data?.detail || error.message || '无法连接 AI 服务')
    }
    throw new AgentApiError(0, error instanceof Error ? error.message : '请求失败')
  }
}

export interface AgentSessionListItem {
  session_id: string
  task_id: string | null
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface AgentSession extends AgentSessionListItem {
  history: Array<{ role: 'user' | 'agent'; content: string; tool_calls?: AgentToolCall[] }>
}

export async function listAgentSessions(taskId: string): Promise<AgentSessionListItem[]> {
  try {
    return unwrap(await http.get<ApiEnvelope<AgentSessionListItem[]>>('/agent/sessions', { params: { task_id: taskId } }))
  } catch (error) {
    throw apiError(error)
  }
}

export async function getAgentSession(sessionId: string): Promise<AgentSession> {
  try {
    return unwrap(await http.get<ApiEnvelope<AgentSession>>(`/agent/sessions/${encodeURIComponent(sessionId)}`))
  } catch (error) {
    throw apiError(error)
  }
}

export function createTaskSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${protocol}//${window.location.host}/ws/task/${taskId}`)
}
