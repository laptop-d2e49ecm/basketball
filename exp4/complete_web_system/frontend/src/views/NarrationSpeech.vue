<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{ url: string; text: string; rate: number }>()
const state = ref<'idle' | 'loading' | 'playing'>('idle')
const notice = ref('')
let player: HTMLAudioElement | null = null

function stop() {
  if (player) {
    player.onended = null
    player.pause()
    player.removeAttribute('src')
    player.load()
    player = null
  }
  state.value = 'idle'
}

async function toggle() {
  if (state.value !== 'idle') { stop(); notice.value = ''; return }
  notice.value = ''
  state.value = 'loading'
  const audio = new Audio(props.url)
  audio.defaultPlaybackRate = props.rate
  audio.playbackRate = props.rate
  player = audio
  audio.onended = stop
  try {
    await audio.play()
    if (player === audio) state.value = 'playing'
  } catch {
    if (player !== audio) return
    stop()
    notice.value = '在线语音暂不可用，请检查网络后重试'
  }
}
watch(() => props.rate, rate => {
  if (player) { player.defaultPlaybackRate = rate; player.playbackRate = rate }
}, { flush: 'sync' })
onBeforeUnmount(stop)
</script>

<template>
  <div class="cv-speech">
    <button class="cv-btn cv-outline" @click="toggle">{{ state === 'loading' ? '正在合成 · 取消' : state === 'playing' ? '停止朗读' : '朗读解说' }}</button>
    <small role="status">{{ notice }}</small>
  </div>
</template>
