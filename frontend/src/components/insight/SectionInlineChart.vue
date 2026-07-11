<template>
  <div class="inline-chart">
    <p class="chart-label">{{ title }}</p>
    <div v-if="bars.length" class="bar-chart">
      <div v-for="(bar, i) in bars" :key="i" class="bar-row">
        <span class="bar-label">{{ bar.label }}</span>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: bar.pct + '%' }" />
        </div>
        <span class="bar-value">{{ bar.value }}</span>
      </div>
    </div>
    <p v-else class="chart-hint">图表已生成（见 PDF 预览）</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  spec: { type: Object, default: () => ({}) },
  sectionIndex: { type: Number, default: 0 },
})

const title = computed(() => props.spec?.title || `第 ${props.sectionIndex} 节图表`)

const bars = computed(() => {
  const spec = props.spec || {}
  const data = spec.data || spec.series?.[0]?.data
  const labels = spec.labels || spec.xAxis?.data || spec.categories
  if (!Array.isArray(data) || !data.length) return []
  const nums = data.map((v) => (typeof v === 'number' ? v : parseFloat(v) || 0))
  const max = Math.max(...nums, 1)
  const lbls = Array.isArray(labels) ? labels : nums.map((_, i) => `项${i + 1}`)
  return nums.slice(0, 8).map((v, i) => ({
    label: String(lbls[i] ?? i + 1).slice(0, 12),
    value: v,
    pct: Math.round((v / max) * 100),
  }))
})
</script>

<style scoped>
.inline-chart {
  margin: 8px 0 8px 32px;
  padding: 10px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.chart-label {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}
.bar-row {
  display: grid;
  grid-template-columns: 72px 1fr 48px;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 11px;
}
.bar-label {
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track {
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 4px;
  min-width: 2px;
}
.bar-value {
  text-align: right;
  color: #475569;
  font-variant-numeric: tabular-nums;
}
.chart-hint {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
}
</style>
