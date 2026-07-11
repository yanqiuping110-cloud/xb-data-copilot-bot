<template>
  <div v-if="hasData" class="result-panel">
    <div class="section-label">查询结果</div>
    <el-tabs v-model="activeTab" class="result-tabs" @tab-change="onTabChange">
      <el-tab-pane label="图表与表格" name="both">
        <ResultChart
          :chart-spec="chartSpec"
          :columns="columns"
          :rows="rows"
        />
        <div class="table-wrap table-below">
          <el-table
            :data="tableRows"
            border
            stripe
            size="small"
            :max-height="maxHeight"
          >
            <el-table-column
              v-for="col in columns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="100"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane label="仅表格" name="table">
        <div class="table-wrap">
          <el-table
            :data="tableRows"
            border
            stripe
            size="small"
            :max-height="maxHeight"
          >
            <el-table-column
              v-for="col in columns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="100"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane v-if="showChartOnlyTab" label="仅图表" name="chart" lazy>
        <ResultChart
          v-if="activeTab === 'chart'"
          :chart-spec="chartSpec"
          :columns="columns"
          :rows="rows"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
/** 查询结果：图表 + 表格同屏展示 */
import { computed, nextTick, ref } from 'vue'
import ResultChart from './ResultChart.vue'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  chartSpec: { type: Object, default: null },
  maxHeight: { type: [Number, String], default: 320 },
})

const activeTab = ref('both')

const hasData = computed(() => props.columns?.length && props.rows?.length)

const showChartOnlyTab = computed(() => props.chartSpec?.status === 'ready')

const tableRows = computed(() => {
  if (!props.columns?.length || !props.rows?.length) return []
  return props.rows.map((row) =>
    Object.fromEntries(props.columns.map((col, i) => [col, row[i]])),
  )
})

function onTabChange() {
  nextTick(() => {
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'))
    })
  })
}
</script>

<style scoped>
.result-panel {
  margin-top: 4px;
}

.section-label {
  margin: 14px 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.result-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.table-wrap {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.table-below {
  margin-top: 12px;
}
</style>
