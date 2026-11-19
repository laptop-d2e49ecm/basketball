export const agentTools = [
  { name: 'query_video_events', label: '查询视频事件', description: '读取当前视频的动作、人数变化和时间点，支持分页查看整场事件。' },
  { name: 'player_detect', label: '检测图像中的球员', description: '根据图像路径检测球员，返回人数、置信度和检测耗时。' },
  { name: 'commentary_classify', label: '分类解说文本', description: '判断一句解说属于投篮、传球、抢断等哪类篮球动作。' },
  { name: 'retrieve_commentary', label: '检索真人解说', description: '按比赛局面或关键词检索本地真人解说语料，提供表达参考。' },
  { name: 'image_text_match', label: '检查图文匹配', description: '检查图像与文字是否均为篮球比赛内容，并返回判断依据。' },
]

export function toolLabel(name: string): string {
  return agentTools.find(tool => tool.name === name)?.label || name || '未知工具'
}

export const argumentLabels: Record<string, string> = {
  task_id: '视频任务', image_path: '图像路径', text: '文本', query: '检索关键词',
  limit: '读取条数', offset: '跳过条数', top_k: '参考条数',
}

export function argumentValue(value: unknown): string {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2) ?? String(value)
}
