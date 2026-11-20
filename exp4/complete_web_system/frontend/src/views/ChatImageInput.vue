<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getTaskFrameUrl, uploadChatImage, type ChatImage } from '../api/client'
const props = defineProps<{ modelValue: ChatImage | null; taskId: string; currentTime: number; frames: number[]; disabled: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [ChatImage | null]; busy: [boolean] }>()
const input = ref<HTMLInputElement | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0
function reset() { generation++; busy.value = false; error.value = ''; dialog.value?.close(); emit('busy', false) }
async function attach(file?: File, frameTime?: number) {
  if (busy.value || props.disabled) return
  if (file && (!/\.(jpe?g|png|webp)$/i.test(file.name) || file.size > 10 * 1024 * 1024)) {
    error.value = '请选择不超过 10 MB 的 JPG、PNG 或 WebP 图片'; return
  }
  const token = ++generation
  const taskId = props.taskId
  busy.value = true; emit('busy', true); error.value = ''; dialog.value?.close()
  try {
    if (!file) {
      const response = await fetch(getTaskFrameUrl(taskId, frameTime || 0))
      if (!response.ok) throw new Error('无法读取该视频帧，请选择其他时刻')
      file = new File([await response.blob()], `视频帧-${((frameTime || 0) / 1000).toFixed(0)}秒.jpg`, { type: 'image/jpeg' })
    }
    if (token !== generation) return
    const image = await uploadChatImage(taskId, file)
    if (token === generation) emit('update:modelValue', image)
  } catch (reason) {
    if (token === generation) error.value = reason instanceof Error ? reason.message : '图片添加失败，请重试'
  } finally { if (token === generation) { busy.value = false; emit('busy', false) } }
}
function pick(event: Event) {
  const field = event.target as HTMLInputElement
  const file = field.files?.[0]; field.value = ''
  if (file) void attach(file)
}
watch(() => props.taskId, reset)
onBeforeUnmount(reset)
</script>

<template>
  <div class="cv-chat-image-input">
    <input ref="input" class="cv-hidden" type="file" accept="image/jpeg,image/png,image/webp" aria-label="选择聊天图片" @change="pick">
    <div class="cv-chat-attachments"><button type="button" class="cv-btn cv-outline" :disabled="disabled || busy" @click="input?.click()">上传图片</button><button type="button" class="cv-btn cv-outline" :disabled="disabled || busy || !taskId" @click="dialog?.showModal()">选取视频帧</button><small v-if="busy" role="status">正在添加图片…</small></div>
    <div v-if="modelValue" class="cv-chat-image-preview"><img :src="modelValue.url" alt="待发送图片"><span>{{ modelValue.name || '已添加图片' }}</span><button type="button" :disabled="disabled || busy" aria-label="移除聊天图片" @click="emit('update:modelValue', null)">×</button></div>
    <small v-if="error" class="cv-chat-error" role="alert">{{ error }}</small>
    <dialog ref="dialog" class="cv-frame-picker" aria-label="选取视频帧">
      <div class="cv-frame-picker-head"><h3>选取视频帧</h3><button type="button" aria-label="关闭选帧" @click="dialog?.close()">×</button></div>
      <button type="button" class="cv-btn cv-primary" @click="attach(undefined, Math.floor(currentTime) * 1000)">使用当前画面（{{ Math.floor(currentTime) }} 秒）</button>
      <p>也可以选择下方事件附近的画面</p>
      <div class="cv-frame-picker-grid"><button v-for="time in [...new Set(frames.map(ms => Math.floor(ms / 1000) * 1000))]" :key="time" type="button" :aria-label="`选择第 ${time / 1000} 秒画面`" @click="attach(undefined, time)"><img :src="getTaskFrameUrl(taskId, time)" alt="候选视频帧"><span>{{ time / 1000 }} 秒</span></button></div>
    </dialog>
  </div>
</template>
