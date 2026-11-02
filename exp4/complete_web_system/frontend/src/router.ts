import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DetectView from './views/DetectView.vue'
import MatchView from './views/MatchView.vue'
import TextView from './views/TextView.vue'
import VideoView from './views/VideoView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/video' },
  {
    path: '/video',
    name: 'video',
    component: VideoView,
    meta: { title: '视频赛事解说', subtitle: '上传比赛视频，生成球员检测结果与时间轴解说。' },
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
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
