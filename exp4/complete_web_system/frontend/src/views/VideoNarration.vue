<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

type Cue = { start_ms: number; text: string }
const props = defineProps<{ video: HTMLVideoElement | null; cues: Cue[]; url: string; segmented: boolean; revision: string }>()
const enabled = ref(true)
const message = ref('')
const blocked = ref(false)
let current: HTMLAudioElement | null = null
let upcoming: HTMLAudioElement | null = null
let index = -1
let stalled = false
let wantsPlay = false
function release(audio: HTMLAudioElement | null) {
  if (!audio) return
  audio.onloadedmetadata = audio.oncanplay = audio.onerror = audio.onended = null
  audio.pause()
  audio.removeAttribute('src')
  audio.load()
}
function reset() {
  index = -1
  wantsPlay = false
  release(current)
  release(upcoming)
  current = upcoming = null
  message.value = ''
  blocked.value = false
}
function cueUrl(i: number) {
  return props.url + '?section=' + i + '&v=' + encodeURIComponent(props.revision)
}
function prepareNext() {
  if (!upcoming && props.segmented && index + 1 < props.cues.length) {
    upcoming = new Audio(cueUrl(index + 1))
    upcoming.preload = 'auto'
  }
}
function changeCue(i: number) {
  release(current)
  current = null
  wantsPlay = false
  blocked.value = false
  message.value = ''
  index = i
  if (i < 0 || !props.segmented) return
  if (upcoming?.src.endsWith(cueUrl(i))) {
    current = upcoming
    upcoming = null
  } else {
    release(upcoming)
    upcoming = null
    current = new Audio()
  }
  const audio = current
  audio.preload = 'auto'
  audio.onended = () => { wantsPlay = false; if (props.video?.ended) message.value = '' }
  audio.onloadedmetadata = () => { synchronize(true); prepareNext() }
  audio.oncanplay = () => synchronize(false)
  audio.onerror = () => {
    if (current !== audio) return
    blocked.value = true
    message.value = '在线语音暂不可用，点击重试'
  }
  if (!audio.getAttribute('src')) audio.src = cueUrl(i)
  else if (audio.error) audio.onerror(new Event('error'))
  else if (audio.readyState >= 1) prepareNext()
}
function synchronize(force: boolean) {
  const video = props.video
  if (!video || !enabled.value || !props.cues.length) return
  // Let the final utterance finish at its current position after the picture ends.
  // Seeking it to the video's final timestamp would skip unread words.
  if (video.ended && index === props.cues.length - 1 && current) {
    if (current.ended) { message.value = ''; return }
    message.value = '正在播完最后一句…'
    if (current.paused && !wantsPlay && !blocked.value) {
      const audio = current
      wantsPlay = true
      void audio.play().catch(() => {
        if (current === audio) { blocked.value = true; message.value = '点击播完最后一句' }
      }).finally(() => { if (current === audio) wantsPlay = false })
    }
    return
  }
  const now = video.currentTime
  let i = 0
  while (i + 1 < props.cues.length && props.cues[i + 1]!.start_ms <= now * 1000) i++
  if (i !== index) changeCue(i)
  const cue = props.cues[i]!
  const start = i === 0 ? 0 : cue.start_ms / 1000
  const end = props.cues[i + 1]?.start_ms
  const span = Math.max(.1, end !== undefined ? end / 1000 - start : (video.duration || Infinity) - start)
  const offset = Math.max(0, now - start)
  const shouldPlay = !video.paused && !video.ended && !stalled && !video.seeking && now >= start
  if (!props.segmented) { message.value = '整场解说稿就绪后可播放语音'; return }
  const audio = current
  if (!audio) return
  if (!shouldPlay) { audio.pause(); wantsPlay = false }
  if (blocked.value) return
  if (!Number.isFinite(audio.duration)) {
    if (shouldPlay) message.value = '正在准备解说语音…'
    return
  }
  // Stretch slightly short narration too, retaining a natural minimum speed.
  const fit = Math.max(.8, audio.duration / span)
  const target = Math.min(audio.duration, offset * fit)
  audio.playbackRate = Math.min(16, video.playbackRate * fit)
  if (force || Math.abs(audio.currentTime - target) > .35) audio.currentTime = target
  if (!shouldPlay || target >= audio.duration - .035 || wantsPlay || blocked.value) return
  wantsPlay = true
  void audio.play().then(() => {
    if (audio === current) message.value = ''
  }).catch((error: Error) => {
    if (audio !== current || error.name === 'AbortError') return
    if (error.name === 'NotAllowedError') {
      blocked.value = true
      message.value = '点击开启解说声音'
    } else {
      blocked.value = true
      message.value = '在线语音暂不可用，点击重试'
    }
  }).finally(() => { if (audio === current) wantsPlay = !audio.paused })
}
function toggle() {
  if (blocked.value) { reset(); synchronize(true); return }
  enabled.value = !enabled.value
  if (enabled.value) synchronize(true)
  else reset()
}
const label = computed(() => blocked.value ? '重试解说声音' : enabled.value ? '关闭解说声音' : '开启解说声音')
watch(() => [props.video, props.cues, props.url, props.revision, props.segmented] as const, ([video], _, clean) => {
  reset()
  stalled = false
  if (!video) return
  function update(event: Event) {
    if (event.type === 'waiting' || event.type === 'seeking') stalled = true
    if (event.type === 'playing' || event.type === 'seeked') stalled = false
    synchronize(event.type !== 'timeupdate')
  }
  const events = ['playing', 'play', 'pause', 'ended', 'waiting', 'seeking', 'seeked', 'timeupdate', 'ratechange', 'loadedmetadata']
  events.forEach(type => video.addEventListener(type, update))
  synchronize(true)
  clean(() => events.forEach(type => video.removeEventListener(type, update)))
}, { immediate: true })
watch(() => [props.video, enabled.value, props.cues.length > 0, blocked.value] as const, ([video, on, available, isBlocked], _, clean) => {
  if (!video || !on || !available || isBlocked) return
  const original = video.volume
  video.volume = original * .25
  clean(() => { video.volume = original })
}, { immediate: true })
onBeforeUnmount(reset)
</script>
<template>
  <button class="cv-voice-toggle" type="button" :disabled="!cues.length" :aria-label="label" :aria-pressed="enabled && !blocked" :title="label" @click="toggle">
    {{ blocked ? '重试声音' : enabled ? '解说开' : '解说关' }}
  </button>
  <span v-if="message" class="cv-voice-status" role="status">{{ message }}</span>
</template>
