<script setup>
// 图文匹配页：图像+文本 → POST /api/v1/match（后端依赖注入串联 检测API→文本API→一致性）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import client from '../api/client'

const file = ref(null)
const previewUrl = ref('')
const text = ref('精彩的突破上篮打进！')
const loading = ref(false)
const result = ref(null)

function beforeUpload(f) {
  if (!['image/jpeg', 'image/png'].includes(f.type)) {
    message.error('图像格式错误，请上传 PNG/JPG')
    return false
  }
  file.value = f
  previewUrl.value = URL.createObjectURL(f)
  result.value = null
  return false
}

async function submit() {
  if (!file.value) return message.warning('请先选择图像')
  if (!text.value.trim()) return message.warning('请输入待匹配文本')
  loading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('text', text.value.trim())
    result.value = await client.post('/match', fd)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-row :gutter="[16, 16]">
    <a-col :xs="24" :md="10">
      <a-card title="上传图像 + 输入文本（工作流：图像检测 → 文本分类 → 一致性判定）">
        <a-upload-dragger :before-upload="beforeUpload" :show-upload-list="false" accept=".png,.jpg,.jpeg">
          <p class="ant-upload-drag-icon"><upload-outlined /></p>
          <p class="ant-upload-text">点击或拖拽图像到此处</p>
        </a-upload-dragger>
        <a-textarea v-model:value="text" :rows="3" style="margin-top: 12px"
                    placeholder="待匹配的解说文本" />
        <a-button type="primary" block style="margin-top: 12px" :loading="loading" @click="submit">
          开始匹配
        </a-button>
      </a-card>
    </a-col>
    <a-col :xs="24" :md="14">
      <a-card title="匹配结论">
        <template v-if="result">
          <a-alert :type="result.match ? 'success' : 'warning'" show-icon
                   :message="result.match ? '✔ 图文一致：均为篮球比赛内容' : '✘ 图文不一致'"
                   :description="`端到端 ${result.total_ms} ms`" />
          <a-row :gutter="16" style="margin-top: 16px">
            <a-col :xs="24" :sm="12">
              <a-card size="small" title="图像侧证据">
                <img v-if="previewUrl" :src="previewUrl" style="max-width: 100%; max-height: 180px" />
                <p style="margin-top: 8px">
                  <a-tag :color="result.image_side.is_court ? 'green' : 'red'">
                    {{ result.image_side.is_court ? '比赛画面' : '非比赛画面' }}
                  </a-tag>
                  检出 {{ result.image_side.player_count }} 名球员 · 平均置信度
                  {{ result.image_side.avg_conf }}
                </p>
              </a-card>
            </a-col>
            <a-col :xs="24" :sm="12">
              <a-card size="small" title="文本侧证据">
                <a-tag :color="result.text_side.is_basketball_text ? 'green' : 'red'">
                  {{ result.text_side.label }}
                </a-tag>
                <p style="margin-top: 8px">置信度 {{ result.text_side.confidence }}</p>
              </a-card>
            </a-col>
          </a-row>
          <a-divider>判定依据</a-divider>
          <ul>
            <li v-for="(e, i) in result.evidence" :key="i">{{ e }}</li>
          </ul>
        </template>
        <a-empty v-else description="上传图像并输入文本后在此显示匹配结论" />
      </a-card>
    </a-col>
  </a-row>
</template>
