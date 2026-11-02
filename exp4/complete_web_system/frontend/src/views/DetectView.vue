<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import { detectImage, type ImageDetectionResult } from '../api/client'
import { assertValidNorm, denormBox } from '../api/coords'

const selectedFile = shallowRef<File | null>(null)
const previewUrl = ref('')
const result = shallowRef<ImageDetectionResult | null>(null)
const loading = ref(false)
const imageElement = ref<HTMLImageElement | null>(null)
const canvasElement = ref<HTMLCanvasElement | null>(null)

function beforeUpload(file: File): boolean {
  const supportedType = ['image/jpeg', 'image/png'].includes(file.type)
  const supportedExtension = /\.(jpe?g|png)$/i.test(file.name)
  if (!supportedType && !supportedExtension) {
    message.error('图像格式错误，请上传 PNG 或 JPG 图片')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    message.error('图片不能超过 10 MB')
    return false
  }

  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  result.value = null
  return false
}

async function submit(): Promise<void> {
  if (!selectedFile.value) {
    message.warning('请先选择一张比赛图片')
    return
  }
  loading.value = true
  try {
    result.value = await detectImage(selectedFile.value)
    await nextTick()
    drawBoxes()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '图像检测失败')
  } finally {
    loading.value = false
  }
}

function drawBoxes(): void {
  const image = imageElement.value
  const canvas = canvasElement.value
  if (!image || !canvas || !result.value || !image.naturalWidth) return

  const bounds = image.getBoundingClientRect()
  const ratio = window.devicePixelRatio || 1
  canvas.width = Math.round(bounds.width * ratio)
  canvas.height = Math.round(bounds.height * ratio)
  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, canvas.width, canvas.height)

  for (const box of result.value.boxes) {
    assertValidNorm(box)
    const { x1, y1, x2, y2 } = denormBox(box, canvas.width, canvas.height)
    const hue = Math.round((1 - Math.min(box.conf, 1)) * 60)
    context.strokeStyle = `hsl(${hue}, 90%, 48%)`
    context.lineWidth = Math.max(1.5, canvas.width / 500)
    context.strokeRect(x1, y1, x2 - x1, y2 - y1)
    context.fillStyle = `hsl(${hue}, 90%, 48%)`
    context.font = `${Math.max(11, canvas.width / 70)}px sans-serif`
    context.fillText(`${Math.round(box.conf * 100)}%`, x1, Math.max(13, y1 - 4))
  }
}

function redrawOnResize(): void {
  drawBoxes()
}

window.addEventListener('resize', redrawOnResize)
onBeforeUnmount(() => {
  window.removeEventListener('resize', redrawOnResize)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="feature-intro">
    <div>
      <span class="feature-kicker">IMAGE DETECTION · YOLO INT8</span>
      <h2>检查一张比赛画面里的球员</h2>
      <p>上传 PNG 或 JPG，查看模型返回的检测框、人数和推理耗时。</p>
    </div>
    <a-tag color="green">独立演示模块</a-tag>
  </div>

  <a-row :gutter="[18, 18]">
    <a-col :xs="24" :md="24" :xl="9">
      <a-card title="上传图片">
        <a-upload-dragger
          accept=".png,.jpg,.jpeg"
          :before-upload="beforeUpload"
          :show-upload-list="false"
        >
          <p class="ant-upload-drag-icon"><UploadOutlined /></p>
          <p class="ant-upload-text">点击或拖入 PNG/JPG 图片</p>
          <p class="ant-upload-hint">单张图片最大 10 MB</p>
        </a-upload-dragger>
        <a-button type="primary" block :loading="loading" class="action-button" @click="submit">
          开始检测
        </a-button>
      </a-card>

      <a-card v-if="result" title="检测统计" class="result-card">
        <a-row :gutter="12">
          <a-col :span="12"><a-statistic title="球员数量" :value="result.player_count" /></a-col>
          <a-col :span="12"><a-statistic title="过滤小框" :value="result.dropped_boxes" /></a-col>
        </a-row>
        <a-descriptions :column="1" size="small" class="result-details">
          <a-descriptions-item label="推理耗时">{{ result.infer_ms }} ms</a-descriptions-item>
          <a-descriptions-item label="总耗时">{{ result.total_ms }} ms</a-descriptions-item>
          <a-descriptions-item label="图片尺寸">{{ result.image_w }} × {{ result.image_h }}</a-descriptions-item>
          <a-descriptions-item label="置信度阈值">{{ result.conf_thr }}</a-descriptions-item>
        </a-descriptions>
      </a-card>
    </a-col>

    <a-col :xs="24" :md="24" :xl="15">
      <a-card title="检测画面">
        <div v-if="previewUrl" class="preview-stage">
          <img ref="imageElement" :src="previewUrl" alt="待检测比赛图片" @load="drawBoxes" />
          <canvas ref="canvasElement" class="detection-overlay" />
        </div>
        <a-empty v-else description="选择图片后，这里会显示检测结果" />
        <div v-if="result && result.player_count === 0" class="empty-result">
          当前图片没有检测到球员，可以换一张画面清晰的比赛图片再试。
        </div>
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
.feature-intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 0 20px; }
.feature-kicker { color: #a0aab8; font: 10px 'DM Mono', monospace; letter-spacing: 1.4px; }
.feature-intro h2 { margin: 7px 0 5px; color: #1b293b; font-size: 20px; }
.feature-intro p { margin: 0; color: #8490a0; font-size: 12px; }
.action-button { margin-top: 16px; height: 40px; }
.result-card { margin-top: 16px; }
.result-details { margin-top: 18px; }
.preview-stage { position: relative; display: inline-block; max-width: 100%; overflow: hidden; border-radius: 8px; background: #f4f6f8; }
.preview-stage img { display: block; max-width: 100%; max-height: 68vh; object-fit: contain; }
.detection-overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.empty-result { margin-top: 12px; padding: 12px 14px; border-radius: 9px; color: #768394; background: #f6f8fb; font-size: 12px; }
@media (max-width: 620px) { .feature-intro { align-items: flex-start; flex-direction: column; } }
</style>
