import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DetectView from './views/DetectView.vue'
import MatchView from './views/MatchView.vue'
import TextView from './views/TextView.vue'
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
    path: '/detect',
    name: 'detect',
    component: DetectView,
    meta: { title: '球员图像检测', subtitle: '上传比赛画面，查看球员检测框和置信度。' },
  },
  {
    path: '/text',
    name: 'text',
    component: TextView,
    meta: { title: '解说文本分类', subtitle: '识别解说文本中的篮球动作类别。' },
  },
  {
    path: '/match',
    name: 'match',
    component: MatchView,
    meta: { title: '图文匹配', subtitle: '对照单张比赛图像与解说文本的内容。' },
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
