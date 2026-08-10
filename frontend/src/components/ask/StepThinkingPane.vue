<template>
  <div class="step-thinking-pane">
    <div v-if="title" class="step-thinking-pane__title">{{ title }}</div>
    <pre
      ref="scrollEl"
      class="step-thinking-pane__text"
      @scroll="onScroll"
    >{{ text }}</pre>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  title: { type: String, default: '' },
  /** 外层 details 是否展开；折叠时不强制滚动 */
  active: { type: Boolean, default: true },
})

const scrollEl = ref(null)
/** 流式输出自动滚到底；用户上滑后暂停，回到底部再恢复 */
const autoScroll = ref(true)
const SCROLL_THRESHOLD = 24

function isNearBottom(el) {
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_THRESHOLD
}

function scrollToBottom() {
  const el = scrollEl.value
  if (!el || !autoScroll.value || !props.active) return
  requestAnimationFrame(() => {
    el.scrollTop = el.scrollHeight
  })
}

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  autoScroll.value = isNearBottom(el)
}

watch(
  () => props.text,
  async (val, prev) => {
    if (!prev && val) autoScroll.value = true
    await nextTick()
    scrollToBottom()
  },
)

watch(
  () => props.active,
  async (open) => {
    if (!open) return
    await nextTick()
    scrollToBottom()
  },
)
</script>

<style scoped>
.step-thinking-pane {
  border-top: 1px solid #e2e8f0;
}

.step-thinking-pane + .step-thinking-pane {
  border-top: 1px dashed #cbd5e1;
  margin-top: 0;
}

.step-thinking-pane__title {
  padding: 6px 10px 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #818cf8;
  text-transform: none;
}

.step-thinking-pane__text {
  margin: 0;
  padding: 8px 10px 10px;
  max-height: 180px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.55;
  color: #64748b;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  background: transparent;
}
</style>
