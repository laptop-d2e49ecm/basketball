<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'

const props = defineProps<{ url: string; text: string; rate: number }>()
const state = ref<'idle' | 'loading' | 'playing'>('idle')
const notice = ref('')
let player: HTMLAudioElement | null = null
let speech: SpeechSynthesisUtterance | null = null

function stop() {
  if (player) {
    player.onended = null
    player.pause()
    player.removeAttribute('src')
    player.load()
    player = null
  }
  if (speech) {
    speech.onend = speech.onerror = null
    window.speechSynthesis.cancel()
    speech = null
  }
  state.value = 'idle'
}

async function toggle() {
  if (state.value !== 'idle') { stop(); notice.value = ''; return }
  notice.value = ''
  state.value = 'loading'
  const audio = new Audio(props.url)
  audio.playbackRate = props.rate
  player = audio
  audio.onended = stop
  try {
    await audio.play()
    if (player === audio) state.value = 'playing'
  } catch {
    if (player !== audio) return
    stop()
    if (!('speechSynthesis' in window)) { notice.value = '语音暂不可用，请重试'; return }
    const lines = props.text.match(/[^。！？!?；;\n]+[。！？!?；;]*/g) ?? []
    let index = 0
    function speakNext() {
      const line = lines[index++]
      if (!line) { speech = null; state.value = 'idle'; notice.value = ''; return }
      const highlights = /[！!]|快攻|三分出手|封盖|扣篮|抢断/.test(line)
      speech = new SpeechSynthesisUtterance(line)
      speech.lang = 'zh-CN'
      speech.rate = props.rate * (highlights ? 1.35 : 1.1)
      speech.pitch = highlights ? 1.15 : 1
      speech.onend = speakNext
      speech.onerror = () => { speech = null; state.value = 'idle'; notice.value = '朗读失败，请重试' }
      window.speechSynthesis.speak(speech)
    }
    notice.value = 'MP3 暂不可用，使用浏览器朗读'
    state.value = 'playing'
    speakNext()
  }
}
onBeforeUnmount(stop)
</script>

<template>
  <div class="cv-speech">
    <button class="cv-btn cv-outline" @click="toggle">{{ state === 'loading' ? '正在合成 · 取消' : state === 'playing' ? '停止朗读' : '朗读解说' }}</button>
    <small role="status">{{ notice }}</small>
  </div>
</template>
