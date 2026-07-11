<template>
  <div class="pdf-viewer">
    <div v-if="url" class="pdf-toolbar">
      <div class="pdf-toolbar-left">
        <span class="pdf-badge" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
            <path
              d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <path d="M14 3v5h5" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
            <path d="M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
        </span>
        <div class="pdf-toolbar-text">
          <span class="pdf-title">PDF 预览</span>
          <span class="pdf-meta-line">
            <span v-if="pageCount">{{ pageCount }} 页</span>
            <span v-if="pageCount && fileSize">·</span>
            <span v-if="fileSize">{{ formatBytes(fileSize) }}</span>
          </span>
        </div>
      </div>
      <el-button size="small" plain @click="$emit('open')">新窗口打开</el-button>
    </div>
    <div v-if="url" class="pdf-frame-wrap">
      <iframe :src="viewerSrc" class="pdf-frame" title="PDF 报告预览" />
    </div>
    <div v-else class="pdf-placeholder">
      <div class="pdf-placeholder-icon" aria-hidden="true">
        <svg viewBox="0 0 64 64" width="48" height="48" fill="none">
          <rect x="12" y="8" width="40" height="48" rx="4" stroke="#cbd5e1" stroke-width="2" />
          <path d="M28 8v10h14" stroke="#cbd5e1" stroke-width="2" stroke-linejoin="round" />
          <path d="M22 30h20M22 38h14M22 46h18" stroke="#e2e8f0" stroke-width="2" stroke-linecap="round" />
        </svg>
      </div>
      <p class="pdf-placeholder-text">{{ placeholder }}</p>
      <el-progress v-if="loading" :percentage="progress" :stroke-width="8" style="width: 220px" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  url: { type: String, default: '' },
  pageCount: { type: Number, default: 0 },
  fileSize: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  progress: { type: Number, default: 0 },
  placeholder: { type: String, default: '报告完成后将在此预览 PDF' },
})

defineEmits(['open'])

const viewerSrc = computed(() => {
  if (!props.url) return ''
  const hash = 'toolbar=0&navpanes=0&scrollbar=1&view=FitH'
  return props.url.includes('#') ? props.url : `${props.url}#${hash}`
})

function formatBytes(n) {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.pdf-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.pdf-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.pdf-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: #fff;
  color: #6366f1;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.pdf-toolbar-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.pdf-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.pdf-meta-line {
  font-size: 12px;
  color: #64748b;
}

.pdf-frame-wrap {
  flex: 1;
  min-height: 0;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  background: #f1f5f9;
}

.pdf-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 420px;
  border: 0;
  background: #fff;
}

.pdf-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 320px;
  border: 1px dashed #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.pdf-placeholder-icon {
  opacity: 0.9;
}

.pdf-placeholder-text {
  margin: 0;
  font-size: 14px;
  color: #94a3b8;
}
</style>
