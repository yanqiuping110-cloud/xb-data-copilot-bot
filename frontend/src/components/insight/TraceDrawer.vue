<template>
  <el-drawer :model-value="visible" title="Trace 飞行记录仪" size="420px" @close="$emit('update:visible', false)">
    <ul class="trace-list">
      <li v-for="tr in traces" :key="tr.sectionIndex" class="trace-item">
        <div class="trace-head">
          <span class="idx">第 {{ tr.sectionIndex }} 节</span>
          <el-tag size="small" :type="tr.status === 'success' ? 'success' : 'warning'">{{ tr.status }}</el-tag>
        </div>
        <div class="trace-title">{{ tr.title }}</div>
        <div class="trace-meta">
          <code>{{ tr.subTraceId || '-' }}</code>
          <span v-if="tr.latencyMs">{{ tr.latencyMs }} ms</span>
        </div>
      </li>
    </ul>
    <p v-if="!traces.length" class="empty">暂无 Trace 数据</p>
  </el-drawer>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  traces: { type: Array, default: () => [] },
})

defineEmits(['update:visible'])
</script>

<style scoped>
.trace-list { list-style: none; margin: 0; padding: 0; }
.trace-item {
  border-bottom: 1px solid #f1f5f9;
  padding: 12px 0;
}
.trace-head { display: flex; justify-content: space-between; align-items: center; }
.trace-title { font-size: 13px; margin: 6px 0; }
.trace-meta { font-size: 11px; color: #64748b; display: flex; gap: 12px; }
code { font-size: 10px; background: #f8fafc; padding: 2px 4px; border-radius: 4px; }
.empty { color: #94a3b8; text-align: center; padding: 24px; }
</style>
