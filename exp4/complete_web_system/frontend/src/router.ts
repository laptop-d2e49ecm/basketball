import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import VideoV3View from './views/VideoV3View.vue'
import AgentChatView from './views/AgentChatView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/video-v3' },
  {
    path: '/video',
    name: 'video',
    redirect: '/video-v3',
  },
  {
    path: '/video-v3',
    name: 'video-v3',
    component: VideoV3View,
    meta: { title: '视频分析工作台', subtitle: '事件时间轴、人数变化与解说同步呈现。' },
  },
  {
    path: '/agent',
    name: 'agent',
    component: AgentChatView,
    meta: { title: 'AI 解说', subtitle: '用一句话问球，Agent 自己决定调哪个工具。' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
