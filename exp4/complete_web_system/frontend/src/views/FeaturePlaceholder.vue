<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRightOutlined, ExperimentOutlined } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const title = computed(() => String(route.meta.title || '课程演示模块'))
const subtitle = computed(() => String(route.meta.subtitle || '此模块将在联调时接入。'))
</script>

<template>
  <div class="placeholder-page">
    <a-card class="placeholder-card" :bordered="false">
      <div class="placeholder-icon"><ExperimentOutlined /></div>
      <span class="placeholder-kicker">COURSE MODULE · INTEGRATION SLOT</span>
      <h2>{{ title }}</h2>
      <p>{{ subtitle }}</p>
      <div class="placeholder-note">
        <span class="note-dot"></span>
        这是视频解说主流程之外的独立页面，不会阻塞视频任务。
      </div>
      <a-button type="link" class="back-link" @click="router.push('/video')">
        返回视频解说 <ArrowRightOutlined />
      </a-button>
    </a-card>
  </div>
</template>

<style scoped>
.placeholder-page { min-height: 62vh; display: grid; place-items: center; }
.placeholder-card { width: min(620px, 100%); padding: 28px 24px; text-align: center; }
.placeholder-icon { display: grid; width: 58px; height: 58px; place-items: center; margin: 8px auto 20px; border-radius: 18px; color: #c9793c; background: #fff1e5; font-size: 24px; }
.placeholder-kicker { color: #a0aab8; font: 10px 'DM Mono', monospace; letter-spacing: 1.4px; }
h2 { margin: 12px 0 8px; color: #1c2939; font-size: 23px; }
p { color: #7b8797; font-size: 13px; }
.placeholder-note { display: flex; align-items: center; justify-content: center; gap: 9px; margin: 26px 0 16px; padding: 13px; border-radius: 9px; color: #6c788a; background: #f6f8fb; font-size: 12px; }
.note-dot { width: 6px; height: 6px; border-radius: 50%; background: #d99a62; }
.back-link { color: #8c633f; font-size: 12px; }
</style>
