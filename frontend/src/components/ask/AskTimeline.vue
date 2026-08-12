<template>
  <div class="ask-timeline-wrap">
    <ul class="ask-timeline">
      <li
        v-for="(step, i) in steps"
        :key="step.node || i"
        :class="[
          'timeline-item',
          step.status || (step.done ? 'done' : ''),
          { active: isRunning(step), slow: isSlow(step) },
        ]"
      >
        <span class="timeline-icon" :aria-label="step.status">
          <i v-if="isRunning(step)" class="timeline-spinner" />
          <template v-else>{{ statusGlyph(step) }}</template>
        </span>
        <div class="timeline-body">
          <div class="timeline-head">
            <span class="timeline-label">{{ step.label }}</span>
            <span v-if="showThinking && hasThinking(step)" class="timeline-llm-badge">大模型</span>
            <span v-if="durationLabel(step)" class="timeline-duration" :class="durationClass(step)">
              {{ durationLabel(step) }}
            </span>
          </div>
          <p v-if="stepSubtitle(step)" class="timeline-sub">{{ stepSubtitle(step) }}</p>
          <details
            v-if="showThinking && hasThinking(step)"
            class="step-thinking"
            :open="isThinkingDetailsOpen(step)"
            @toggle="onThinkingToggle(step, $event)"
          >
            <summary>
              推理过程
              <span v-if="thinkingBlocks(step).length > 1" class="step-thinking__count">
                {{ thinkingBlocks(step).length }} 段
              </span>
            </summary>
            <div class="step-thinking__list">
              <StepThinkingPane
                v-for="(block, bi) in thinkingBlocks(step)"
                :key="`${step.node}-${bi}`"
                :text="block.text"
                :title="block.title"
                :active="isThinkingDetailsOpen(step)"
              />
            </div>
          </details>
        </div>
      </li>
    </ul>
    <div v-if="displayTotalMs > 0" class="timeline-total">
      <span class="total-label">合计耗时</span>
      <span class="total-value">{{ formatDurationMs(displayTotalMs) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  formatDurationMs,
  getThinkingBlocksWithTitles,
  timelineTotalMs,
} from '../../utils/askProgress.js'
import StepThinkingPane from './StepThinkingPane.vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  /** 父级可选传入时钟；不传则组件内自 tick */
  nowMs: { type: Number, default: null },
  /** ADMIN 可见：在步骤内展示大模型推理 */
  showThinking: { type: Boolean, default: false },
})

const localNow = ref(Date.now())
/** 用户手动折叠/展开：完成后尊重用户选择；进行中默认展开 */
const thinkingOpen = ref({})
let timer = null

const hasRunning = computed(() =>
  (props.steps || []).some((s) => s.active || s.status === 'running'),
)

const effectiveNow = computed(() => (props.nowMs != null ? props.nowMs : localNow.value))

watch(
  hasRunning,
  (running) => {
    if (props.nowMs != null) return
    if (running && !timer) {
      localNow.value = Date.now()
      timer = setInterval(() => {
        localNow.value = Date.now()
      }, 200)
    } else if (!running && timer) {
      clearInterval(timer)
      timer = null
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const displayTotalMs = computed(() => timelineTotalMs(props.steps, effectiveNow.value))

function thinkingBlocks(step) {
  return getThinkingBlocksWithTitles(step)
}

function hasThinking(step) {
  return thinkingBlocks(step).length > 0
}

function isThinkingDetailsOpen(step) {
  const key = step.node
  if (Object.prototype.hasOwnProperty.call(thinkingOpen.value, key)) {
    return !!thinkingOpen.value[key]
  }
  // 默认展开有推理的步骤；用户手动折叠后记住状态
  return hasThinking(step)
}

function onThinkingToggle(step, event) {
  const open = !!event?.target?.open
  thinkingOpen.value = { ...thinkingOpen.value, [step.node]: open }
}

function isRunning(step) {
  return !!(step.active || step.status === 'running')
}

function stepSubtitle(step) {
  return step.summary || step.subtitle || ''
}

function statusGlyph(step) {
  if (step.status === 'fail') return '!'
  if (step.status === 'skipped') return '−'
  return '✓'
}

function elapsedMs(step) {
  if (isRunning(step) && step.startedAt) {
    return Math.max(0, effectiveNow.value - step.startedAt)
  }
  return step.durationMs
}

function durationLabel(step) {
  const ms = elapsedMs(step)
  if (ms == null) return isRunning(step) ? '0 ms' : ''
  return formatDurationMs(ms)
}

function isSlow(step) {
  return (elapsedMs(step) || 0) >= 2000
}

function durationClass(step) {
  if (isRunning(step)) return 'is-running'
  const ms = step.durationMs || 0
  if (ms >= 5000) return 'is-slow'
  if (ms >= 2000) return 'is-medium'
  return 'is-fast'
}
</script>

<style scoped>
.ask-timeline-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ask-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(180deg, #fafbfc 0%, #f8fafc 100%);
  border: 1px solid #e8ecf1;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.timeline-item.active {
  border-color: #c7d2fe;
  background: linear-gradient(180deg, #f8faff 0%, #f1f5ff 100%);
  box-shadow: inset 3px 0 0 #6366f1;
}

.timeline-item.slow:not(.active) {
  border-color: #fde68a;
  background: linear-gradient(180deg, #fffbeb 0%, #fefce8 100%);
}

.timeline-icon {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: #94a3b8;
}

.timeline-item.done .timeline-icon {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
}

.timeline-item.fail .timeline-icon {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

.timeline-item.active .timeline-icon {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
}

.timeline-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

.timeline-body {
  flex: 1;
  min-width: 0;
}

.timeline-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-label {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.35;
}

.timeline-llm-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #4338ca;
  background: #e0e7ff;
  border: 1px solid #c7d2fe;
}

.timeline-duration {
  margin-left: auto;
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

.timeline-duration.is-fast {
  color: #047857;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.timeline-duration.is-medium {
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.timeline-duration.is-slow {
  color: #c2410c;
  background: #fff7ed;
  border: 1px solid #fdba74;
}

.timeline-duration.is-running {
  color: #4338ca;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
}

.timeline-sub {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: #64748b;
}

.step-thinking {
  margin-top: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  overflow: hidden;
}

.step-thinking summary {
  cursor: pointer;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  user-select: none;
  list-style-position: inside;
}

.step-thinking__count {
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  color: #6366f1;
  background: #eef2ff;
}

.step-thinking__list {
  display: flex;
  flex-direction: column;
}

.timeline-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(90deg, #f1f5f9 0%, #eef2ff 100%);
  border: 1px solid #e2e8f0;
}

.total-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.total-value {
  font-size: 13px;
  font-weight: 700;
  color: #312e81;
  font-variant-numeric: tabular-nums;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
