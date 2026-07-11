<template>
  <details v-if="text" ref="detailsEl" class="ask-thinking-panel" open @toggle="onToggle">
    <summary>思考过程 <span class="badge">ADMIN</span></summary>
    <pre ref="scrollEl" class="thinking-text" @scroll="onScroll">{{ text }}</pre>
  </details>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
})

const scrollEl = ref(null)
const detailsEl = ref(null)
/** 流式输出时自动滚到底；用户手动上滑后暂停，回到底部再恢复 */
const autoScroll = ref(true)

const SCROLL_THRESHOLD = 20

function isNearBottom(el) {
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_THRESHOLD
}

function scrollToBottom() {
  const el = scrollEl.value
  if (!el || !autoScroll.value || !detailsEl.value?.open) return
  requestAnimationFrame(() => {
    el.scrollTop = el.scrollHeight
  })
}

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  autoScroll.value = isNearBottom(el)
}

function onToggle() {
  if (detailsEl.value?.open) {
    nextTick(scrollToBottom)
  }
}

watch(
  () => props.text,
  async (val, prev) => {
    if (!prev && val) {
      autoScroll.value = true
    }
    await nextTick()
    scrollToBottom()
  },
)
</script>

<style scoped>
.ask-thinking-panel {
  margin-bottom: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  overflow: hidden;
}

.ask-thinking-panel summary {
  cursor: pointer;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  user-select: none;
  list-style-position: inside;
}

.badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #e0e7ff;
  color: #4338ca;
  font-size: 10px;
  font-weight: 700;
}

.thinking-text {
  margin: 0;
  padding: 10px 12px 12px;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.55;
  color: #64748b;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  background: transparent;
  border-top: 1px solid #e2e8f0;
}
</style>
