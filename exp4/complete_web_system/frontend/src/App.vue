<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BarChartOutlined,
  HistoryOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

const navigation = [
  { key: '/agent', label: 'AI 解说', icon: RobotOutlined },
  { key: '/video-v3', label: '视频分析工作台', icon: BarChartOutlined },
  { key: '/video-v3?view=recent', label: '最近任务', icon: HistoryOutlined },
]

const currentTitle = computed(() => String(route.meta.title || '篮球 AI 赛事解说'))
const selectedKeys = computed(() => [route.path])

function navigate(key: string) {
  void router.push(key)
}

function handleMenuClick({ key }: { key: string | number }) {
  navigate(String(key))
}
</script>

<template>
  <RouterView v-if="route.path === '/video-v3'" />
  <a-layout v-else class="app-shell" :class="{ 'nav-collapsed': collapsed }">
    <a-layout-sider v-model:collapsed="collapsed" :width="244" :collapsed-width="76" :trigger="null" class="side-panel">
      <div class="brand-lockup">
        <div class="brand-mark"><span></span><span></span><span></span></div>
        <div v-if="!collapsed" class="brand-copy">
          <strong>COURTVISION</strong>
          <small>AI BASKETBALL STUDIO</small>
        </div>
      </div>

      <div v-if="!collapsed" class="side-caption">工作台</div>
      <a-menu
        :selected-keys="selectedKeys"
        mode="inline"
        class="side-menu"
        @click="handleMenuClick"
      >
        <a-menu-item v-for="item in navigation" :key="item.key">
          <template #icon><component :is="item.icon" /></template>
          <span>{{ item.label }}</span>
          <span v-if="item.key === '/video-v3' && !collapsed" class="menu-live-dot"></span>
        </a-menu-item>
      </a-menu>

      <div class="sider-bottom">
        <button class="collapse-button" type="button" @click="collapsed = !collapsed">
          <MenuUnfoldOutlined v-if="collapsed" />
          <MenuFoldOutlined v-else />
          <span v-if="!collapsed">收起导航</span>
        </button>
      </div>
    </a-layout-sider>

    <a-layout class="main-layout">
      <a-layout-header class="topbar">
        <div class="topbar-title">
          <span class="eyebrow">BASKETBALL INTELLIGENCE</span>
          <h1>{{ currentTitle }}</h1>
        </div>
        <div class="topbar-meta">
          <span class="status-chip"><i></i>视频分析工作台</span>
          <span class="avatar">CV</span>
        </div>
      </a-layout-header>
      <a-layout-content class="page-content">
        <RouterView />
      </a-layout-content>
      <footer class="page-footer">
        <span>COURTVISION · 实验 4</span>
        <span>视频解说主流程</span>
      </footer>
    </a-layout>
  </a-layout>
</template>
