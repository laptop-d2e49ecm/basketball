<script setup>
// 球员检测页：上传图像 → POST /api/v1/detect → canvas 画框（经 coords 唯一换算点）
import { nextTick, ref } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import client from '../api/client'
import { assertValidNorm, denormBox } from '../api/coords'

const file = ref(null)
const previewUrl = ref('')
const loading = ref(false)
const result = ref(null)
const canvasRef = ref(null)
const imgRef = ref(null)

function beforeUpload(f) {
  if (!['image/jpeg', 'image/png'].includes(f.type)) {
    message.error('图像格式错误，请上传 PNG/JPG')
    return false
  }
  if (f.size > 10 * 1024 * 1024) {
    message.error('图像超过 10MB 限制')
    return false
  }
  file.value = f
  previewUrl.value = URL.createObjectURL(f)
  result.value = null
  return false // 阻止自动上传
}

async function submit() {
  if (!file.value) return message.warning('请先选择图像')
  loading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    result.value = await client.post('/detect', fd)
    await nextTick()
    drawBoxes()
  } finally {
    loading.value = false
  }
}

// 防线：所有框先过合法性断言再换算（实验 1 教训），画布用内部分辨率（dpr 适配）
function drawBoxes() {
  const img = imgRef.value, canvas = canvasRef.value
  if (!img || !canvas || !result.value) return
  const dpr = window.devicePixelRatio || 1
  const rect = img.getBoundingClientRect()
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  for (const b of result.value.boxes) {
    assertValidNorm(b)
    const { x1, y1, x2, y2 } = denormBox(b, canvas.width, canvas.height)
    const hue = Math.round((1 - Math.min(b.conf, 1)) * 60) // 置信度越高越绿
    ctx.strokeStyle = `hsl(${hue}, 90%, 50%)`
    ctx.lineWidth = Math.max(1.5, canvas.width / 500)
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
    ctx.fillStyle = `hsl(${hue}, 90%, 50%)`
    ctx.font = `${Math.max(10, canvas.width / 70)}px sans-serif`
    ctx.fillText(b.conf.toFixed(2), x1, Math.max(12, y1 - 4))
  }
}
</script>

<template>
  <a-row :gutter="[16, 16]">
    <a-col :xs="24" :md="10">
      <a-card title="上传比赛图像（PNG/JPG ≤10MB）">
        <a-upload-dragger :before-upload="beforeUpload" :show-upload-list="false" accept=".png,.jpg,.jpeg">
          <p class="ant-upload-drag-icon"><upload-outlined /></p>
          <p class="ant-upload-text">点击或拖拽图像到此处</p>
          <p class="ant-upload-hint">实验 3 INT8 模型推理 · 前端展示目标 ≤2 秒</p>
        </a-upload-dragger>
        <a-button type="primary" block style="margin-top: 16px" :loading="loading" @click="submit">
          开始检测
        </a-button>
      </a-card>
      <a-card v-if="result" title="检测结果" style="margin-top: 16px">
        <a-statistic title="检出球员数" :value="result.player_count" />
        <a-descriptions :column="1" size="small" style="margin-top: 12px">
          <a-descriptions-item label="模型推理">{{ result.infer_ms }} ms</a-descriptions-item>
          <a-descriptions-item label="端到端耗时">{{ result.total_ms }} ms</a-descriptions-item>
          <a-descriptions-item label="过滤过小框">{{ result.dropped_boxes }} 个（<8px）</a-descriptions-item>
          <a-descriptions-item label="原图尺寸">{{ result.image_w }}×{{ result.image_h }}</a-descriptions-item>
        </a-descriptions>
      </a-card>
    </a-col>
    <a-col :xs="24" :md="14">
      <a-card title="检测可视化（框色：绿=高置信，红=低置信）">
        <div v-if="previewUrl" class="canvas-wrap">
          <img ref="imgRef" :src="previewUrl" class="preview" @load="drawBoxes" />
          <canvas ref="canvasRef" class="overlay" />
        </div>
        <a-empty v-else description="上传后在此显示检测框" />
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
.canvas-wrap { position: relative; display: inline-block; max-width: 100%; }
.preview { max-width: 100%; display: block; }
.overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
