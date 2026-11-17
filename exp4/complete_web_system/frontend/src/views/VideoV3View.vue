<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const pageSource = computed(() =>
  route.query.view === 'recent' ? '/courtvision.html?view=recent' : '/courtvision.html',
)
</script>

<template>
  <iframe class="video-v3-frame" :src="pageSource" title="视频分析工作台" />
</template>

<style scoped>
.video-v3-frame {
  display: block;
  width: 100%;
  height: 100vh;
  border: 0;
  background: #101419;
}
</style>
