<template>
  <div class="turn-picker">
    <div class="picker-toolbar">
      <el-button size="small" @click="selectAll">全选有效</el-button>
      <el-button size="small" @click="selectWithChart">仅选有图表</el-button>
      <el-button size="small" @click="clearAll">清空</el-button>
      <span class="picker-hint">
        已选 {{ modelValue.length }} / {{ selectableTurns.length }} 条可纳入
      </span>
    </div>
    <el-empty v-if="!allTurns.length" description="当前会话暂无成功的问数记录" />
    <el-checkbox-group
      v-else
      :model-value="modelValue"
      class="turn-list"
      @change="onChange"
    >
      <label
        v-for="t in allTurns"
        :key="t.traceId"
        class="turn-item"
        :class="{ disabled: !t.selectable }"
      >
        <el-checkbox :value="t.traceId" :disabled="!t.selectable" />
        <div class="turn-body">
          <div class="turn-question">{{ t.question }}</div>
          <div class="turn-meta">
            <el-tag size="small" :type="t.selectable ? 'success' : 'info'">
              {{ t.selectable ? '可纳入' : t.skipReason }}
            </el-tag>
            <span v-if="t.rowCount != null">{{ t.rowCount }} 行</span>
            <span v-if="t.hasChart" class="has-chart">有图</span>
          </div>
        </div>
      </label>
    </el-checkbox-group>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import {
  hasReportableContentFromMessage,
  turnRowCountFromMessage,
} from '../../utils/briefReportTurn.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const allTurns = computed(() => {
  const out = []
  const msgs = props.messages || []
  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i]
    if (msg.role !== 'assistant' || !msg.traceId || msg.isError) continue
    let question = ''
    for (let j = i - 1; j >= 0; j--) {
      if (msgs[j].role === 'user') {
        question = msgs[j].text || ''
        break
      }
    }
    const rowCount = turnRowCountFromMessage(msg)
    const hasChart = Boolean(msg.chartSpec)
    const selectable = hasReportableContentFromMessage(msg)
    out.push({
      traceId: msg.traceId,
      question: question || msg.text?.slice(0, 40) || '问数记录',
      rowCount,
      hasChart,
      selectable,
      skipReason: selectable ? '' : '无有效数据',
    })
  }
  return out
})

const selectableTurns = computed(() => allTurns.value.filter((t) => t.selectable))

watch(
  () => [props.modelValue, selectableTurns.value],
  () => {
    const allowed = new Set(selectableTurns.value.map((t) => t.traceId))
    const filtered = (props.modelValue || []).filter((id) => allowed.has(id))
    if (filtered.length !== (props.modelValue || []).length) {
      emit('update:modelValue', filtered)
    }
  },
  { deep: true },
)

function onChange(val) {
  const allowed = new Set(selectableTurns.value.map((t) => t.traceId))
  emit('update:modelValue', (val || []).filter((id) => allowed.has(id)))
}

function selectAll() {
  emit(
    'update:modelValue',
    selectableTurns.value.map((t) => t.traceId),
  )
}

function selectWithChart() {
  emit(
    'update:modelValue',
    selectableTurns.value.filter((t) => t.hasChart).map((t) => t.traceId),
  )
}

function clearAll() {
  emit('update:modelValue', [])
}
</script>

<style scoped>
.turn-picker {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.picker-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.picker-hint {
  margin-left: auto;
  font-size: 12px;
  color: #64748b;
}
.turn-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}
.turn-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.turn-item:hover:not(.disabled) {
  border-color: #22c55e;
}
.turn-item.disabled {
  opacity: 0.55;
  cursor: not-allowed;
  background: #f8fafc;
}
.turn-body {
  flex: 1;
  min-width: 0;
}
.turn-question {
  font-size: 13px;
  color: #0f172a;
  line-height: 1.45;
  margin-bottom: 6px;
}
.turn-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #64748b;
}
.has-chart {
  color: #16a34a;
}
</style>
