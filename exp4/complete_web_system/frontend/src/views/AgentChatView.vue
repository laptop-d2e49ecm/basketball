/**
 * 实验5 · AI 解说对话页（/agent）
 *
 * 对应任务书 5.4.2 / 总包 §1：照 exp5/CONTRACT.md 渲染
 *  - 气泡区渲染 result.agent
 *  - result.tool_calls 渲染为可展开的过程条（🔧 球员检测 · 成功 · 146ms）
 *  - 错误码 400/404/429/500/504 各自动作见 CONTRACT §4
 *  - 首轮不带 session_id，之后每轮原样带回（断点续聊）
 */
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  ClearOutlined,
  ReloadOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { agentChat, AgentApiError, type AgentToolCall } from '../api/client'

interface ChatTurn {
  id: number
  role: 'user' | 'agent'
  content: string
  toolCalls?: AgentToolCall[]
  elapsed?: number
  pending?: boolean
  failed?: boolean
}

const TOOL_LABELS: Record<string, string> = {
  player_detect: '球员检测',
  commentary_classify: '解说文本分类',
  image_text_match: '图文匹配',
  query_video_events: '视频事件查询',
  retrieve_commentary: '解说语料检索',
}

const EXAMPLES = [
  { label: '图像检测', text: 'f000005 这张图里有几个球员？' },
  { label: '文本分类', text: '帮我看看这句解说是什么动作：抢断之后一条龙快攻上篮得手！' },
  { label: '解说风格', text: '来一句三分绝杀时刻的解说，参考真人解说的说法' },
]

const turns = ref<ChatTurn[]>([])
const draft = ref('')
const loading = ref(false)
const sessionId = ref('')
const provider = ref('')
const lastMessage = ref('')
const failedText = ref('')
const scrollBox = ref<HTMLDivElement | null>(null)
const openToolKey = ref('')
let seq = 0

const canSend = computed(() => draft.value.trim().length > 0 && !loading.value)

function scrollToBottom(): void {
  void nextTick(() => {
    const box = scrollBox.value
    if (box) box.scrollTop = box.scrollHeight
  })
}

function pushTurn(turn: Omit<ChatTurn, 'id'>): ChatTurn {
  seq += 1
  const item: ChatTurn = { id: seq, ...turn }
  turns.value.push(item)
  scrollToBottom()
  return item
}

function errorTextOf(code: number, fallback: string): string {
  if (code === 400) return '消息格式不对，请换个说法再试。'
  if (code === 404) return '会话已失效，已为你重新开始一轮。'
  if (code === 429) return 'AI 服务调用有点频繁，等几秒再试。'
  if (code === 504) return 'AI 响应超时了，点下面「重试」再来一次。'
  if (code === 500) return 'AI 服务暂时不可用，点下面「重试」再来一次。'
  return fallback || '网络好像不通，检查后端是否在 127.0.0.1:8000 运行。'
}

async function send(text?: string): Promise<void> {
  const content = (text ?? draft.value).trim()
  if (!content || loading.value) return

  draft.value = ''
  failedText.value = ''
  lastMessage.value = content
  pushTurn({ role: 'user', content })
  const placeholder = pushTurn({ role: 'agent', content: '', pending: true })
  loading.value = true

  try {
    const result = await agentChat({
      message: content,
      ...(sessionId.value ? { session_id: sessionId.value } : {}),
    })
    sessionId.value = result.session_id
    provider.value = result.provider
    placeholder.content = result.agent
    placeholder.toolCalls = result.tool_calls
    placeholder.elapsed = result.elapsed_ms
    placeholder.pending = false
  } catch (error) {
    const code = error instanceof AgentApiError ? error.code : 0
    const detail = error instanceof Error ? error.message : '请求失败'
    if (code === 404) sessionId.value = ''
    placeholder.pending = false
    placeholder.failed = true
    placeholder.content = errorTextOf(code, detail)
    if (code === 500 || code === 504 || code === 0) failedText.value = content
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function retry(): void {
  if (!failedText.value) return
  const text = failedText.value
  failedText.value = ''
  void send(text)
}

function reset(): void {
  turns.value = []
  sessionId.value = ''
  provider.value = ''
  failedText.value = ''
  message.success('已开始新会话')
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name
}

/** 极简 Markdown：转义 HTML 后只支持 **粗体**、`代码` 与换行，避免直接 v-html 原文。 */
function renderText(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

function toggleTool(turnId: number, index: number): void {
  const key = `${turnId}-${index}`
  openToolKey.value = openToolKey.value === key ? '' : key
}

function toolArgsText(call: AgentToolCall): string {
  try {
    return JSON.stringify(call.args)
  } catch {
    return ''
  }
}

function onEnter(event: KeyboardEvent): void {
  if (event.shiftKey) return
  event.preventDefault()
  void send()
}
</script>

<template>
  <div class="feature-intro">
    <div>
      <span class="feature-kicker">LANGCHAIN AGENT · DEEPSEEK</span>
      <h2>和 AI 解说员聊一场球</h2>
      <p>它会自己判断该调哪个工具：检出球员、判动作类别、翻真人解说语料。</p>
    </div>
    <a-tag color="blue">实验 5 · Agent</a-tag>
  </div>

  <a-row :gutter="[18, 18]">
    <a-col :xs="24" :md="24" :xl="17">
      <a-card class="chat-card" :bordered="false">
        <div ref="scrollBox" class="chat-scroll">
          <div v-if="!turns.length" class="chat-empty">
            <ThunderboltOutlined class="empty-icon" />
            <p class="empty-title">问点什么试试</p>
            <p class="empty-tip">
              可以直接给图像路径（如 <code>f000005</code>），也可以贴一句解说，或者让它来一段解说词。
            </p>
          </div>

          <div
            v-for="turn in turns"
            :key="turn.id"
            class="turn"
            :class="turn.role === 'user' ? 'turn-user' : 'turn-agent'"
          >
            <div class="bubble" :class="{ 'bubble-failed': turn.failed }">
              <div v-if="turn.pending" class="thinking">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                <span class="thinking-text">AI 正在思考…</span>
              </div>
              <template v-else>
                <p class="bubble-text" v-html="renderText(turn.content)"></p>
                <div v-if="turn.toolCalls && turn.toolCalls.length" class="tool-list">
                  <button
                    v-for="(call, index) in turn.toolCalls"
                    :key="index"
                    type="button"
                    class="tool-chip"
                    :class="{ 'tool-error': call.status === 'error' }"
                    @click="toggleTool(turn.id, index)"
                  >
                    <span class="tool-dot"></span>
                    🔧 {{ toolLabel(call.tool) }} ·
                    {{ call.status === 'ok' ? '成功' : '失败' }}
                    <template v-if="call.elapsed_ms"> · {{ Math.round(call.elapsed_ms) }}ms</template>
                  </button>
                  <div
                    v-for="(call, index) in turn.toolCalls"
                    v-show="openToolKey === `${turn.id}-${index}`"
                    :key="`d-${index}`"
                    class="tool-detail"
                  >
                    <div><b>入参</b> {{ toolArgsText(call) }}</div>
                    <div><b>结果</b> {{ call.result_summary }}</div>
                  </div>
                </div>
              </template>
            </div>
            <div v-if="turn.role === 'agent' && !turn.pending" class="turn-meta">
              <span v-if="turn.elapsed">{{ (turn.elapsed / 1000).toFixed(1) }}s</span>
              <span v-if="turn.toolCalls && turn.toolCalls.length">
                · {{ turn.toolCalls.length }} 次工具调用
              </span>
            </div>
          </div>
        </div>

        <div class="composer">
          <a-textarea
            v-model:value="draft"
            class="composer-input"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            placeholder="比如：f000005 这张图里有几个球员？（Enter 发送，Shift+Enter 换行）"
            :disabled="loading"
            @keydown.enter="onEnter"
          />
          <a-button type="primary" :disabled="!canSend" :loading="loading" @click="send()">
            <template #icon><SendOutlined /></template>
            发送
          </a-button>
        </div>
        <div v-if="failedText" class="retry-row">
          <a-button size="small" danger @click="retry">
            <template #icon><ReloadOutlined /></template>
            重试上一句
          </a-button>
        </div>
      </a-card>
    </a-col>

    <a-col :xs="24" :md="24" :xl="7">
      <a-card title="快捷提问" size="small">
        <div v-for="item in EXAMPLES" :key="item.label" class="example-row">
          <a-tag color="default">{{ item.label }}</a-tag>
          <a class="example-text" @click="send(item.text)">{{ item.text }}</a>
        </div>
      </a-card>

      <a-card title="本轮会话" size="small" class="session-card">
        <a-descriptions :column="1" size="small">
          <a-descriptions-item label="会话 ID">
            {{ sessionId || '（首轮发送后生成）' }}
          </a-descriptions-item>
          <a-descriptions-item label="模型通道">
            {{ provider || '—' }}
          </a-descriptions-item>
        </a-descriptions>
        <a-button block size="small" class="reset-button" @click="reset">
          <template #icon><ClearOutlined /></template>
          开始新会话
        </a-button>
        <p class="session-tip">同一会话内会记住上下文，换话题或结果跑偏时点这里重开。</p>
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
.chat-card { overflow: hidden; }
.chat-scroll { height: min(60vh, 560px); padding: 4px 4px 8px; overflow-y: auto; }
.chat-empty { padding: 56px 16px; color: #8490a0; text-align: center; }
.empty-icon { color: #3b82f6; font-size: 26px; }
.empty-title { margin: 10px 0 6px; color: #1b293b; font-size: 15px; }
.empty-tip { margin: 0 auto; max-width: 420px; font-size: 12px; line-height: 1.7; }
.empty-tip code { padding: 1px 5px; border-radius: 4px; color: #334155; background: #eef2f7; }

.turn { display: flex; margin: 10px 0; flex-direction: column; }
.turn-user { align-items: flex-end; }
.turn-agent { align-items: flex-start; }
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.75;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.turn-user .bubble { color: #fff; background: #2563eb; border-bottom-right-radius: 4px; }
.turn-agent .bubble { color: #1f2937; background: #f4f6fa; border-bottom-left-radius: 4px; }
.bubble-failed { color: #b42318 !important; background: #fff1f0 !important; }
.bubble-text { margin: 0; white-space: pre-wrap; }
.turn-meta { margin: 4px 4px 0; color: #a0aab8; font-size: 11px; }

.thinking { display: flex; align-items: center; gap: 4px; color: #6b7280; }
.dot {
  width: 5px; height: 5px; border-radius: 50%; background: #93a0b4;
  animation: bounce 1.1s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }
.thinking-text { margin-left: 6px; font-size: 12px; }
@keyframes bounce { 0%, 80%, 100% { opacity: 0.35; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }

.tool-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tool-chip {
  padding: 3px 9px; border: 1px solid #d7e3f4; border-radius: 999px;
  color: #2f5f9e; background: #eef4ff; font-size: 11px; cursor: pointer;
}
.tool-chip:hover { background: #e2edff; }
.tool-error { color: #b42318; border-color: #f3c1bd; background: #fff1f0; }
.tool-dot { display: inline-block; width: 6px; height: 6px; margin-right: 4px; border-radius: 50%; background: #22c55e; vertical-align: 1px; }
.tool-error .tool-dot { background: #ef4444; }
.tool-detail {
  flex-basis: 100%; padding: 8px 10px; border-radius: 8px;
  color: #4b5563; background: #fff; border: 1px dashed #dbe3ee; font: 11px/1.7 'DM Mono', monospace;
}

.composer { display: flex; align-items: flex-end; gap: 10px; padding: 12px 4px 0; border-top: 1px solid #eef1f6; }
.composer-input { flex: 1; }
.retry-row { padding: 8px 4px 0; }

.example-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 10px; }
.example-row:last-child { margin-bottom: 0; }
.example-text { color: #3b6ea5; font-size: 12px; line-height: 1.6; cursor: pointer; }
.example-text:hover { text-decoration: underline; }
.session-card { margin-top: 14px; }
.session-tip { margin: 10px 0 0; color: #98a3b3; font-size: 11px; line-height: 1.6; }
.reset-button { margin-top: 12px; }

@media (max-width: 620px) {
  .chat-scroll { height: 56vh; }
  .bubble { max-width: 92%; }
  .composer { flex-direction: column; align-items: stretch; }
}
</style>
