<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getTaskFrameUrl, uploadChatImage, type ChatImage } from '../api/client'
const props = defineProps<{ modelValue: ChatImage[]; taskId: string; disabled: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [ChatImage[]]; busy: [boolean] }>()
const busy = ref(false)
const error = ref('')
let generation = 0
function reset() { generation++; busy.value = false; error.value = ''; emit('busy', false) }
async function selectFrame(timeMs: number) {
  if (busy.value || props.disabled) return
  const time = Math.floor(timeMs / 1000) * 1000
  if (props.modelValue.some(image => image.frame_ms === time)) return
  if (props.modelValue.length >= 6) { error.value = '每次最多选择 6 张画面'; return }
  const token = ++generation
  const taskId = props.taskId
  busy.value = true; emit('busy', true); error.value = ''
  try {
    const response = await fetch(getTaskFrameUrl(taskId, time))
    if (!response.ok) throw new Error('无法读取该视频帧，请选择其他时刻')
    const file = new File([await response.blob()], `视频帧-${time / 1000}秒.jpg`, { type: 'image/jpeg' })
    if (token !== generation) return
    const image = await uploadChatImage(taskId, file)
    if (token === generation) emit('update:modelValue', [...props.modelValue, { ...image, frame_ms: time }])
  } catch (reason) {
    if (token === generation) error.value = reason instanceof Error ? reason.message : '图片添加失败，请重试'
  } finally { if (token === generation) { busy.value = false; emit('busy', false) } }
}
defineExpose({ selectFrame })
watch(() => props.taskId, reset)
onBeforeUnmount(reset)
</script>

<template>
  <div class="cv-chat-image-input">
    <small v-if="busy" role="status">正在添加画面…</small>
    <div v-if="modelValue.length" class="cv-chat-image-previews">
      <div v-for="(image, index) in modelValue" :key="image.id" class="cv-chat-image-preview">
        <img :src="image.url" :alt="`待发送画面 ${index + 1}`"><span>{{ image.name || `画面 ${index + 1}` }}</span>
        <button type="button" :disabled="disabled || busy" :aria-label="`移除画面 ${index + 1}`" @click="emit('update:modelValue', modelValue.filter(item => item.id !== image.id))">×</button>
      </div>
    </div>
    <small v-if="error" class="cv-chat-error" role="alert">{{ error }}</small>
  </div>
</template>
