<script setup>
// 本侧临时外壳：仅承载三核心页联调；合并时用视频主线骨架的 App.vue 替换，
// 只需保留三页路由（见 router/index.js 注释）。
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const current = ref(router.currentRoute.value.path)
router.afterEach((to) => { current.value = to.path })
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-header class="header">
      <div class="brand">🏀 篮球 AI 赛事解说员</div>
      <a-menu v-model:selectedKeys="current" mode="horizontal" theme="dark"
              style="flex: 1; min-width: 0" @select="({ key }) => router.push(key)">
        <a-menu-item key="/detect">球员检测</a-menu-item>
        <a-menu-item key="/text">解说文本分类</a-menu-item>
        <a-menu-item key="/match">图文匹配</a-menu-item>
        <a-menu-item key="/video" disabled title="视频分析页由视频主线合并后启用">视频分析（合并后）</a-menu-item>
      </a-menu>
    </a-layout-header>
    <a-layout-content style="padding: 24px; max-width: 1200px; margin: 0 auto; width: 100%">
      <router-view />
    </a-layout-content>
    <a-layout-footer style="text-align: center; color: #999">
      实验 4 · 实验3 INT8 模型（mAP50=0.420） · 统一信封 {code,result,msg}
    </a-layout-footer>
  </a-layout>
</template>

<style>
.header { display: flex; align-items: center; gap: 24px; }
.brand { color: #fff; font-size: 17px; font-weight: 600; white-space: nowrap; }
</style>
