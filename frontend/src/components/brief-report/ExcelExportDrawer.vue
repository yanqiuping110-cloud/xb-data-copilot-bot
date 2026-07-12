<template>
  <el-dialog
    v-model="visible"
    title="导出 Excel"
    width="760px"
    align-center
    :close-on-click-modal="!exporting"
    :close-on-press-escape="!exporting"
    destroy-on-close
    class="excel-export-dialog"
    @open="onOpen"
  >
    <p class="step-desc">勾选要导出的问数记录，每条记录将写入一个工作表（Sheet）。</p>
    <TurnPicker v-model="selectedTraceIds" :messages="messages" />

    <template #footer>
      <div class="footer-actions">
        <el-button :disabled="exporting" @click="visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="exporting"
          :disabled="!canExport"
          @click="onExport"
        >
          导出 Excel
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadBriefReportExcel } from '../../api/briefReport'
import TurnPicker from './TurnPicker.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  sessionId: { type: String, default: null },
  messages: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const selectedTraceIds = ref([])
const exporting = ref(false)

const canExport = computed(
  () => props.sessionId && selectedTraceIds.value.length > 0 && !exporting.value,
)

function onOpen() {
  selectedTraceIds.value = []
  exporting.value = false
}

async function onExport() {
  if (!canExport.value) return
  exporting.value = true
  try {
    await downloadBriefReportExcel({
      sessionId: props.sessionId,
      traceIds: selectedTraceIds.value,
    })
    ElMessage.success('Excel 已下载')
    visible.value = false
  } catch (err) {
    ElMessage.error(err?.message || 'Excel 导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.excel-export-dialog :deep(.el-dialog) {
  max-width: 92vw;
  border-radius: 12px;
}
.step-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #64748b;
}
.footer-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
