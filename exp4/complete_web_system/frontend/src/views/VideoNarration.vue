<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

type Cue = { start_ms: number; text: string }
const props = defineProps<{ video: HTMLVideoElement | null; cues: Cue[]; url: string; segmented: boolean; revision: string }>()
const enabled = ref(true)
const message = ref('')
const blocked = ref(false)
const audible = ref(false)
let current: HTMLAudioElement | null = null
let stalled = false
let wantsPlay = false
let hasPlayed = false

function reset() {
  const audio = current
  current = null
  audible.value = false
  wantsPlay = hasPlayed = false
  if (audio) {
    audio.onloadedmetadata = audio.oncanplay = audio.onerror = audio.onended = audio.onplaying = audio.onpause = audio.onwaiting = null
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
  }
  message.value = ''
  blocked.value = false
}
function prepare() {
  if (current) return current
  const audio = new Audio()
  current = audio
  audio.preload = 'auto'
  audio.onplaying = () => { if (current === audio) audible.value = true }
  audio.onpause = audio.onwaiting = () => { if (current === audio) audible.value = false }
  audio.onloadedmetadata = () => synchronize(true)
  audio.oncanplay = () => synchronize(false)
  audio.onended = () => { audible.value = false; wantsPlay = false; if (props.video?.ended) message.value = '' }
  audio.onerror = () => {
    if (current !== audio) return
    blocked.value = true
    audible.value = false
    message.value = '解说音轨暂不可用，点击重试'
  }
  audio.src = props.url + '?timeline=1&track=continuous-v2&v=' + encodeURIComponent(props.revision)
  return audio
}
function play(audio: HTMLAudioElement, finishing = false) {
  if (!audio.paused || wantsPlay || blocked.value) return
  wantsPlay = true
  void audio.play().then(() => {
    if (current !== audio) return
    hasPlayed = true
    message.value = finishing ? '正在播完最后一句…' : ''
  }).catch((error: Error) => {
    if (current !== audio || error.name === 'AbortError') return
    blocked.value = true
    audible.value = false
    message.value = error.name === 'NotAllowedError' ? '点击开启解说声音' : '解说音轨暂不可用，点击重试'
  }).finally(() => { if (current === audio) wantsPlay = false })
}
function synchronize(force: boolean) {
  const video = props.video
  if (!video || !enabled.value || !props.cues.length) return
  if (!props.segmented) { message.value = '整场解说稿就绪后可播放语音'; return }
  const audio = prepare()
  if (blocked.value) return
  if (video.ended && hasPlayed && !audio.ended && audio.currentTime >= props.cues.at(-1)!.start_ms / 1000 - .5) {
    message.value = '正在播完最后一句…'
    play(audio, true)
    return
  }
  const shouldPlay = !video.paused && !video.ended && !video.seeking && !stalled
  if (!shouldPlay) { audio.pause(); wantsPlay = false }
  if (!Number.isFinite(audio.duration)) {
    if (shouldPlay) message.value = '正在准备解说语音…'
    return
  }
  const target = Math.min(audio.duration, Math.max(0, video.currentTime))
  // One prepared track runs at its natural rate. Align only on a real seek or
  // when resuming a paused track; never skip spoken samples during playback.
  if ((force || (shouldPlay && audio.paused)) && Math.abs(audio.currentTime - target) > .06) audio.currentTime = target
  if (shouldPlay && target < audio.duration - .025) play(audio)
}
function toggle() {
  if (blocked.value) {
    // Reuse loaded media so play() stays inside the user's click gesture.
    if (current?.error) reset()
    blocked.value = false
    message.value = ''
    synchronize(true)
    return
  }
  enabled.value = !enabled.value
  if (enabled.value) synchronize(true)
  else reset()
}
function startFromGesture() {
  if (!enabled.value || !props.segmented || !props.cues.length) return
  if (current?.error) reset()
  blocked.value = false
  const audio = prepare()
  audio.muted = false
  audio.volume = 1
  if (Number.isFinite(audio.duration) && props.video && Math.abs(audio.currentTime - props.video.currentTime) > .06) {
    audio.currentTime = Math.min(audio.duration, props.video.currentTime)
  }
  // Call inside the same click as video.play(), even while media is loading.
  play(audio)
}
defineExpose({ startFromGesture })
const label = computed(() => blocked.value ? '重试解说声音' : enabled.value ? '关闭解说声音' : '开启解说声音')
watch(() => [props.video, props.cues, props.url, props.revision, props.segmented] as const, ([video], _, clean) => {
  reset()
  stalled = false
  if (!video) return
  function update(event: Event) {
    if (event.type === 'waiting' || event.type === 'seeking') stalled = true
    if (event.type === 'playing' || event.type === 'seeked') stalled = false
    synchronize(event.type === 'seeked' || event.type === 'loadedmetadata')
  }
  const events = ['playing', 'play', 'pause', 'ended', 'waiting', 'seeking', 'seeked', 'timeupdate', 'loadedmetadata']
  events.forEach(type => video.addEventListener(type, update))
  synchronize(true)
  clean(() => events.forEach(type => video.removeEventListener(type, update)))
}, { immediate: true })
watch(() => [props.video, enabled.value, audible.value] as const, ([video, on, available], _, clean) => {
  if (!video || !on || !available) return
  const original = video.muted
  video.muted = true
  clean(() => { video.muted = original })
}, { immediate: true })
onBeforeUnmount(reset)
</script>
<template>
  <button class="cv-voice-toggle" type="button" :disabled="!cues.length" :aria-label="label" :aria-pressed="enabled && !blocked" :title="label" @click="toggle">
    {{ !cues.length ? '解说准备中' : blocked ? '重试声音' : enabled ? '解说开' : '解说关' }}
  </button>
  <span v-if="message" class="cv-voice-status" role="status">{{ message }}</span>
</template>
