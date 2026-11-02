<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { classifyCommentary, type TextClassificationResult } from '../api/client'

const text = ref('')
const result = shallowRef<TextClassificationResult | null>(null)
const loading = ref(false)

const examples = [
  '詹姆斯外线三分出手命中！',
  '这球防守犯规了，裁判回看录像。',
  '教练请求暂停调整战术。',
  '今天天气晴朗，适合出游。',
]

async function submit(example?: string): Promise<void> {
  const value = (example ?? text.value).trim()
  if (!value) {
    message.warning('请输入一段解说文本')
    return
  }
  text.value = value
  loading.value = true
  try {
    result.value = await classifyCommentary(value)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '文本分类失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="feature-intro">
    <div>
      <span class="feature-kicker">COMMENTARY · TEXT CLASSIFICATION</span>
      <h2>识别解说文字里的篮球事件</h2>
      <p>输入一段文字，查看分类结果、置信度和候选类别。</p>
    </div>
    <a-tag color="green">CPU 可运行</a-tag>
  </div>

  <a-row :gutter="[18, 18]">
    <a-col :xs="24" :md="12" :xl="12">
      <a-card title="输入解说文本">
        <a-textarea
          v-model:value="text"
          :rows="6"
          :maxlength="2000"
          show-count
          placeholder="例如：底角三分出手，球进了！"
        />
        <div class="examples">
          <span>试试示例</span>
          <a-tag v-for="example in examples" :key="example" @click="submit(example)">
            {{ example }}
          </a-tag>
        </div>
        <a-button type="primary" block :loading="loading" class="action-button" @click="submit()">
          开始分类
        </a-button>
      </a-card>
    </a-col>

    <a-col :xs="24" :md="12" :xl="12">
      <a-card title="分类结果" class="result-panel">
        <template v-if="result">
          <a-result
            :status="result.is_basketball_text ? 'success' : 'warning'"
            :title="result.label"
            :sub-title="result.is_basketball_text
              ? `判定为篮球赛事文本 · 置信度 ${result.confidence}`
              : `判定为非篮球赛事文本 · 最高类别置信度 ${result.confidence}`"
          />
          <a-divider>候选类别</a-divider>
          <div v-for="item in result.top3" :key="item.label" class="top-result">
            <span>{{ item.label }}</span>
            <a-progress :percent="Math.round(item.prob * 100)" />
          </div>
          <a-descriptions :column="2" size="small" class="result-details">
            <a-descriptions-item label="分类耗时">{{ result.infer_ms }} ms</a-descriptions-item>
            <a-descriptions-item label="输入字数">{{ result.chars }}</a-descriptions-item>
          </a-descriptions>
        </template>
        <a-empty v-else description="提交文本后，这里会显示分类结果" />
      </a-card>
      <div class="scope-note">
        此页对文本内容分类，不会从视频中识别投篮、传球等动作。
      </div>
    </a-col>
  </a-row>
</template>

<style scoped>
.feature-intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 0 20px; }
.feature-kicker { color: #a0aab8; font: 10px 'DM Mono', monospace; letter-spacing: 1.4px; }
.feature-intro h2 { margin: 7px 0 5px; color: #1b293b; font-size: 20px; }
.feature-intro p { margin: 0; color: #8490a0; font-size: 12px; }
.examples { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 14px; color: #97a1af; font-size: 11px; }
.examples :deep(.ant-tag) { margin-inline-end: 0; cursor: pointer; }
.action-button { margin-top: 18px; height: 40px; }
.result-panel { min-height: 320px; }
.top-result { display: grid; grid-template-columns: 86px 1fr; align-items: center; gap: 10px; margin: 7px 0; color: #5e6b7b; font-size: 12px; }
.top-result :deep(.ant-progress) { margin-bottom: 0; }
.result-details { margin-top: 18px; }
.scope-note { margin-top: 12px; padding: 12px 14px; border-radius: 9px; color: #7a8797; background: #fff; font-size: 11px; }
@media (max-width: 620px) { .feature-intro { align-items: flex-start; flex-direction: column; } }
</style>
