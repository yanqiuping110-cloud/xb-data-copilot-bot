<template>
  <div v-if="visible" :class="['report-cover', { compact }]">
    <div v-if="!compact" class="shimmer" />
    <div class="cover-content">
      <template v-if="compact">
        <div class="cover-left">
          <span class="brand">Insight Engine</span>
          <span class="title-line">{{ title }}</span>
          <span class="meta">{{ sectionTotal }} 节 · {{ pageCount }} 页 · {{ formatElapsed(latencyMs) }}</span>
        </div>
        <el-button type="primary" size="small" @click="$emit('download')">下载 PDF</el-button>
      </template>
      <template v-else>
        <p class="brand">Insight Engine</p>
        <h2>{{ title }}</h2>
        <p class="meta">{{ sectionTotal }} 节 · {{ pageCount }} 页 · {{ formatElapsed(latencyMs) }}</p>
        <el-button type="primary" @click="$emit('download')">下载 PDF</el-button>
      </template>
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  title: { type: String, default: '' },
  sectionTotal: { type: Number, default: 0 },
  pageCount: { type: Number, default: 0 },
  latencyMs: { type: Number, default: 0 },
})

defineEmits(['download'])

function formatElapsed(ms) {
  if (!ms) return ''
  const s = Math.round(ms / 1000)
  return `耗时 ${s}s`
}
</script>

<style scoped>
.report-cover {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  padding: 24px;
}
.report-cover.compact {
  padding: 10px 14px;
  border-radius: 8px;
  margin-top: 0;
}
.shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.12) 50%, transparent 60%);
  animation: shimmer 0.6s ease-out;
}
@keyframes shimmer {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}
.cover-content {
  position: relative;
  z-index: 1;
}
.report-cover.compact .cover-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.cover-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.brand { font-size: 12px; opacity: 0.85; margin: 0; flex-shrink: 0; }
.title-line {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta { font-size: 12px; opacity: 0.9; flex-shrink: 0; }
h2 { margin: 0 0 8px; font-size: 18px; }
.report-cover:not(.compact) .meta { margin-bottom: 16px; }
</style>
