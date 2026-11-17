import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import WorkspaceView from './views/WorkspaceView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: WorkspaceView },
  { path: '/recent', component: WorkspaceView },
  { path: '/analyzing/:taskId', component: WorkspaceView },
  { path: '/tasks/:taskId', component: WorkspaceView },
  { path: '/video', redirect: '/' },
  { path: '/video-v3', redirect: '/' },
  { path: '/agent', redirect: '/' },
  { path: '/detect', redirect: '/' },
  { path: '/text', redirect: '/' },
  { path: '/match', redirect: '/' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(), routes })
