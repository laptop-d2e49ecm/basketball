<script setup lang="ts">
import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import { matchImageAndCommentary, type ImageTextMatchResult } from '../api/client'

const selectedFile = shallowRef<File | null>(null)
const previewUrl = ref('')
const commentary = ref('精彩的突破上篮打进！')
const result = shallowRef<ImageTextMatchResult | null>(null)
const loading = ref(false)

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
  const text = commentary.value.trim()
  if (!text) {
    message.warning('请输入待匹配的解说文本')
    return
  }

  loading.value = true
  try {
    result.value = await matchImageAndCommentary(selectedFile.value, text)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '图文匹配失败')
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="feature-intro">
    <div>
      <span class="feature-kicker">IMAGE + COMMENTARY · MATCHING</span>
      <h2>对照图片与解说文字</h2>
      <p>系统分别判断图片中是否检测到球员、文字是否属于篮球解说，再给出匹配结论。</p>
    </div>
    <a-tag color="orange">单张图片演示</a-tag>
  </div>

  <a-row :gutter="[18, 18]">
    <a-col :xs="24" :md="24" :xl="10">
      <a-card title="输入图片和解说">
        <a-upload-dragger
          accept=".png,.jpg,.jpeg"
          :before-upload="beforeUpload"
          :show-upload-list="false"
        >
          <p class="ant-upload-drag-icon"><UploadOutlined /></p>
          <p class="ant-upload-text">点击或拖入 PNG/JPG 图片</p>
          <p class="ant-upload-hint">单张图片最大 10 MB</p>
        </a-upload-dragger>
        <a-textarea
          v-model:value="commentary"
          :rows="4"
          :maxlength="2000"
          show-count
          class="commentary-input"
          placeholder="输入要与图片匹配的解说文本"
        />
        <a-button type="primary" block :loading="loading" class="action-button" @click="submit">
          开始匹配
        </a-button>
      </a-card>
    </a-col>

    <a-col :xs="24" :md="24" :xl="14">
      <a-card title="匹配结果" class="match-result-card">
        <template v-if="result">
          <a-alert
            :type="result.match ? 'success' : 'warning'"
            show-icon
            :message="result.match ? '图片与文本都符合篮球内容' : '图片与文本未能同时确认是篮球内容'"
            :description="`处理耗时 ${result.total_ms} ms`"
          />
          <a-row :gutter="14" class="evidence-grid">
            <a-col :xs="24" :md="12" :xl="12">
              <a-card size="small" title="图片判断">
                <img v-if="previewUrl" :src="previewUrl" alt="用于匹配的图片" class="match-preview" />
                <p class="evidence-text">
                  <a-tag :color="result.image_side.is_court ? 'green' : 'default'">
                    {{ result.image_side.is_court ? '检测到球员' : '未检测到球员' }}
                  </a-tag>
                  <br />人数 {{ result.image_side.player_count }} · 平均置信度 {{ result.image_side.avg_conf }}
                </p>
              </a-card>
            </a-col>
            <a-col :xs="24" :md="12" :xl="12">
              <a-card size="small" title="文本判断">
                <a-tag :color="result.text_side.is_basketball_text ? 'green' : 'default'">
                  {{ result.text_side.label }}
                </a-tag>
                <p class="evidence-text">置信度 {{ result.text_side.confidence }}</p>
              </a-card>
            </a-col>
          </a-row>
          <a-divider>判定依据</a-divider>
          <ul class="evidence-list">
            <li v-for="item in result.evidence" :key="item">{{ item }}</li>
          </ul>
        </template>
        <a-empty v-else description="上传图片并输入解说后，这里会显示匹配结论" />
      </a-card>
      <div class="scope-note">
        这是单张图片与文本的匹配演示，不会对整段视频进行动作与时间点匹配。
      </div>
    </a-col>
  </a-row>
</template>

<style scoped>
.feature-intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 0 20px; }
.feature-kicker { color: #a0aab8; font: 10px 'DM Mono', monospace; letter-spacing: 1.4px; }
.feature-intro h2 { margin: 7px 0 5px; color: #1b293b; font-size: 20px; }
.feature-intro p { margin: 0; color: #8490a0; font-size: 12px; }
.commentary-input { margin-top: 14px; }
.action-button { margin-top: 14px; height: 40px; }
.match-result-card { min-height: 330px; }
.evidence-grid { margin-top: 16px; }
.match-preview { display: block; max-width: 100%; max-height: 180px; margin: 3px auto 10px; object-fit: contain; }
.evidence-text { margin: 10px 0 0; color: #748092; font-size: 11px; line-height: 1.8; }
.evidence-list { margin-bottom: 0; padding-left: 20px; color: #687587; font-size: 12px; line-height: 1.8; }
.scope-note { margin-top: 12px; padding: 12px 14px; border-radius: 9px; color: #7a8797; background: #fff; font-size: 11px; }
@media (max-width: 620px) { .feature-intro { align-items: flex-start; flex-direction: column; } }
</style>
