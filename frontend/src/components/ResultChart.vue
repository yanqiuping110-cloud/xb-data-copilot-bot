<template>
  <div class="result-chart">
    <p v-if="chartSpec?.status === 'rejected'" class="chart-hint rejected">
      {{ rejectReason }}
    </p>
    <p v-else-if="note" class="chart-hint">{{ note }}</p>
    <div v-show="hasChart" ref="chartEl" class="chart-canvas" />
  </div>
</template>

<script setup>
/** 根据 chartSpec + 表格数据渲染 ECharts */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildEchartsOption } from '../utils/chartAdapter'

const props = defineProps({
  chartSpec: { type: Object, default: null },
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
})

const chartEl = ref(null)
let chartInstance = null
let resizeObserver = null
let intersectionObserver = null

const note = computed(() => props.chartSpec?.options?.note || null)

const rejectReason = computed(
  () => props.chartSpec?.rejectReason || props.chartSpec?.reject_reason || '当前结果无法生成图表',
)

const hasChart = computed(
  () => props.chartSpec?.status === 'ready' && buildEchartsOption({
    chartSpec: props.chartSpec,
    columns: props.columns,
    rows: props.rows,
  }),
)

function isInstanceValid() {
  return (
    chartInstance
    && !chartInstance.isDisposed()
    && chartEl.value
    && chartInstance.getDom() === chartEl.value
  )
}

function disposeChart() {
  chartInstance?.dispose()
  chartInstance = null
}

function ensureChartInstance() {
  if (!chartEl.value) return null
  if (isInstanceValid()) return chartInstance
  disposeChart()
  chartInstance = echarts.init(chartEl.value)
  return chartInstance
}

function renderChart() {
  if (!chartEl.value || !hasChart.value) {
    disposeChart()
    return
  }
  const option = buildEchartsOption({
    chartSpec: props.chartSpec,
    columns: props.columns,
    rows: props.rows,
  })
  if (!option) {
    disposeChart()
    return
  }
  const instance = ensureChartInstance()
  if (!instance) return
  instance.setOption(option, true)
  instance.resize()
}

function scheduleRender() {
  nextTick(() => {
    requestAnimationFrame(() => {
      renderChart()
      requestAnimationFrame(() => chartInstance?.resize())
    })
  })
}

function onResize() {
  if (!hasChart.value) return
  if (!isInstanceValid()) {
    scheduleRender()
    return
  }
  chartInstance.resize()
}

function setupResizeObserver() {
  if (!chartEl.value || typeof ResizeObserver === 'undefined') return
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(() => onResize())
  resizeObserver.observe(chartEl.value)
}

function setupIntersectionObserver() {
  if (!chartEl.value || typeof IntersectionObserver === 'undefined') return
  intersectionObserver?.disconnect()
  intersectionObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) scheduleRender()
    },
    { threshold: 0.05 },
  )
  intersectionObserver.observe(chartEl.value)
}

onMounted(() => {
  scheduleRender()
  setupResizeObserver()
  setupIntersectionObserver()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  intersectionObserver?.disconnect()
  intersectionObserver = null
  disposeChart()
})

watch(
  () => [props.chartSpec, props.columns, props.rows],
  () => scheduleRender(),
  { deep: true },
)

watch(hasChart, (ready) => {
  if (ready) scheduleRender()
  else disposeChart()
})

watch(chartEl, (el) => {
  if (el) {
    setupResizeObserver()
    setupIntersectionObserver()
    scheduleRender()
  }
})
</script>

<style scoped>
.result-chart {
  width: 100%;
}

.chart-canvas {
  width: 100%;
  height: 320px;
  min-height: 240px;
}

.chart-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #909399;
}

.chart-hint.rejected {
  color: #e6a23c;
}
</style>
