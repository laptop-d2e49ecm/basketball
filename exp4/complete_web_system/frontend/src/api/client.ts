import axios, { type AxiosResponse } from 'axios'

export interface ApiEnvelope<T> {
  code: number
  result: T
  msg: string
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

/* ---------------- AI 解说 Agent（契约 exp5/CONTRACT.md） ---------------- */

export interface AgentToolCall {
  tool: string
  args: Record<string, unknown>
  status: 'ok' | 'error'
  result_summary: string
  elapsed_ms: number | null
}

export interface AgentChatResult {
  session_id: string
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
