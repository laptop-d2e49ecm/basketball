/**
 * Axios 封装：统一信封解包与异常处理（任务书"重点关注"：网络错误/5xx 友好提示）。
 * 后端契约：成功 {code:0, result, msg}；失败 HTTP 4xx/5xx + {code, result:null, msg}。
 */
import axios from 'axios'
import { message } from 'ant-design-vue'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

client.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body.code === 'number' && body.code !== 0) {
      message.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg || `code=${body.code}`))
    }
    return body.result // 解包：调用方直接拿 result
  },
  (err) => {
    let msg = '网络异常，请检查后端服务是否启动'
    if (err.response) {
      msg = err.response.data?.msg || `服务器错误（HTTP ${err.response.status}）`
    } else if (err.code === 'ECONNABORTED') {
      msg = '请求超时，请稍后重试'
    }
    message.error(msg)
    return Promise.reject(err)
  },
)

export default client
