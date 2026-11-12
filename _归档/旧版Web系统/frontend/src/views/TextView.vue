<script setup>
// 解说文本分类页：输入文本 → POST /api/v1/text/classify → 动作类别 + 置信度 top3
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import client from '../api/client'

const text = ref('')
const loading = ref(false)
const result = ref(null)

const samples = [
  '詹姆斯外线三分出手命中！',
  '这球防守犯规了，裁判回看录像',
  '教练请求暂停调整战术',
  '今天天气晴朗适合出游', // 域外对照
]

async function submit(t) {
  const val = (t ?? text.value).trim()
  if (!val) return message.warning('请输入解说文本')
  text.value = val
  loading.value = true
  try {
    result.value = await client.post('/text/classify', { text: val })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-row :gutter="[16, 16]">
    <a-col :xs="24" :md="12">
      <a-card title="输入解说文本（实验 1 语料训练的弱监督动作分类器）">
        <a-textarea v-model:value="text" :rows="5" :maxlength="2000" show-count
                    placeholder="例如：底角三分出手，球进了！！" />
        <div style="margin-top: 12px">
          <span style="color: #999; margin-right: 8px">示例：</span>
          <a-tag v-for="s in samples" :key="s" style="cursor: pointer" @click="submit(s)">{{ s }}</a-tag>
        </div>
        <a-button type="primary" block style="margin-top: 16px" :loading="loading" @click="submit()">
          开始分类
        </a-button>
      </a-card>
    </a-col>
    <a-col :xs="24" :md="12">
      <a-card title="分类结果">
        <template v-if="result">
          <a-result :status="result.is_basketball_text ? 'success' : 'warning'"
                    :title="result.label"
                    :sub-title="result.is_basketball_text
                      ? `判定为篮球赛事文本（置信度 ${result.confidence}）`
                      : `置信度 ${result.confidence}，判定为非篮球赛事文本`" />
          <a-divider>类别 Top3</a-divider>
          <div v-for="item in result.top3" :key="item.label" class="top3-row">
            <span class="top3-label">{{ item.label }}</span>
            <a-progress :percent="Math.round(item.prob * 100)" :show-info="true"
                        :stroke-color="{ from: '#108ee9', to: '#87d068' }" />
          </div>
          <a-descriptions :column="1" size="small" style="margin-top: 12px">
            <a-descriptions-item label="耗时">{{ result.infer_ms }} ms</a-descriptions-item>
            <a-descriptions-item label="字数">{{ result.chars }}</a-descriptions-item>
          </a-descriptions>
        </template>
        <a-empty v-else description="输入文本后在此显示分类结果" />
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
.top3-row { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.top3-label { width: 90px; flex: none; }
</style>
