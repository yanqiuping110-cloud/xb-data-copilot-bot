<template>
  <div class="ask-timeline-wrap">
    <ul class="ask-timeline">
      <li
        v-for="(step, i) in steps"
        :key="step.node || i"
        :class="['timeline-item', step.status || (step.done ? 'done' : ''), { active: step.active, slow: isSlow(step) }]"
      >
        <span class="timeline-icon" :aria-label="step.status">{{ statusGlyph(step) }}</span>
        <div class="timeline-body">
          <div class="timeline-head">
            <span class="timeline-label">{{ step.label }}</span>
            <span v-if="durationLabel(step)" class="timeline-duration" :class="durationClass(step)">
              {{ durationLabel(step) }}
            </span>
          </div>
          <p v-if="stepSubtitle(step)" class="timeline-sub">{{ stepSubtitle(step) }}</p>
        </div>
      </li>
    </ul>
    <div v-if="totalMs > 0" class="timeline-total">
      <span class="total-label">合计耗时</span>
      <span class="total-value">{{ formatDurationMs(totalMs) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDurationMs, timelineTotalMs } from '../../utils/askProgress.js'

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

const totalMs = computed(() => timelineTotalMs(props.steps))

function stepSubtitle(step) {
  return step.summary || step.subtitle || ''
}

function statusGlyph(step) {
  if (step.status === 'fail') return '!'
  if (step.status === 'skipped') return '−'
  if (step.active || step.status === 'running') return '◌'
  return '✓'
}

function durationLabel(step) {
  if (step.active || step.status === 'running') return '进行中'
  if (step.durationMs == null) return ''
  return formatDurationMs(step.durationMs)
}

function isSlow(step) {
  return (step.durationMs || 0) >= 2000
}

function durationClass(step) {
  if (step.active || step.status === 'running') return 'is-running'
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

.timeline-item.active .timeline-icon {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  animation: pulse 1.2s ease-in-out infinite;
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

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.65;
  }
}
</style>
