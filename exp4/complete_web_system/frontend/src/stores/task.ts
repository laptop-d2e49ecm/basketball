import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CommentaryEvent, TaskStatus } from '../api/client'

const STORAGE_KEY = 'courtvision.current-video-task'

function loadSavedTask(): TaskStatus | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? JSON.parse(saved) as TaskStatus : null
  } catch {
    return null
  }
}

export const useTaskStore = defineStore('video-task', () => {
  const task = ref<TaskStatus | null>(loadSavedTask())
  const commentary = ref<CommentaryEvent[]>([])

  function setTask(value: TaskStatus | null) {
    task.value = value
    try {
      if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
      else localStorage.removeItem(STORAGE_KEY)
    } catch {
      // The current page still works if browser storage is unavailable.
    }
  }

  function appendCommentary(event: CommentaryEvent) {
    commentary.value = [...commentary.value, event].sort((a, b) => a.t_ms - b.t_ms)
  }

  function setCommentary(events: CommentaryEvent[]) {
    commentary.value = [...events].sort((a, b) => a.t_ms - b.t_ms)
  }

  function reset() {
    setTask(null)
    commentary.value = []
  }

  return { task, commentary, setTask, appendCommentary, setCommentary, reset }
})
