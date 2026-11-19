<script setup lang="ts">
import type { AgentToolCall } from '../api/client'
import { argumentLabels, argumentValue, toolLabel } from '../agentTools'
defineProps<{ calls: AgentToolCall[] }>()
</script>

<template>
  <details class="cv-tool-trace">
    <summary>{{ calls.length }} 次工具调用 · {{ calls.map(call => toolLabel(call.tool)).join('、') }}</summary>
    <article v-for="(call, index) in calls" :key="index" class="cv-tool-call">
      <header><b>{{ index + 1 }}. {{ toolLabel(call.tool) }}</b><span :class="call.status">{{ call.status === 'ok' ? '成功' : call.status === 'error' ? '失败' : '未返回结果' }}</span></header>
      <code>{{ call.tool }}</code>
      <dl v-if="Object.keys(call.args || {}).length">
        <template v-for="(value, key) in call.args" :key="key">
          <dt>{{ argumentLabels[key] || key }}</dt><dd>{{ argumentValue(value) }}</dd>
        </template>
      </dl>
      <p v-else>未提供调用参数</p>
      <b class="cv-tool-result-label">结果摘要</b>
      <p class="cv-tool-result">{{ call.result_summary || '未返回结果摘要' }}</p>
      <small v-if="call.elapsed_ms != null">工具报告耗时 {{ call.elapsed_ms }} ms</small>
    </article>
  </details>
</template>
