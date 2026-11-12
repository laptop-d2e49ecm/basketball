import { createRouter, createWebHistory } from 'vue-router'
import DetectView from '../views/DetectView.vue'
import TextView from '../views/TextView.vue'
import MatchView from '../views/MatchView.vue'

// 三核心页路由；/video 由视频主线骨架（队友）提供，合并时并入其 router
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/detect' },
    { path: '/detect', name: 'detect', component: DetectView, meta: { title: '球员检测' } },
    { path: '/text', name: 'text', component: TextView, meta: { title: '解说文本分类' } },
    { path: '/match', name: 'match', component: MatchView, meta: { title: '图文匹配' } },
  ],
})
