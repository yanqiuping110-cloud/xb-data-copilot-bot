<template>
  <div v-if="sections.length" ref="rootEl" class="section-chat">
    <div
      v-for="sec in sections"
      :key="sec.index"
      :class="['section-block', sec.status]"
    >
      <div class="section-head">
        <span class="section-idx">第 {{ sec.index }} 节</span>
        <span class="section-title">{{ sec.title }}</span>
        <el-tag v-if="sec.status === 'running'" size="small" type="primary">分析中</el-tag>
        <el-tag v-else-if="sec.status === 'done'" size="small" type="success">完成</el-tag>
        <el-tag v-else-if="sec.status === 'fail'" size="small" type="danger">失败</el-tag>
      </div>
      <div class="q-row">
        <span class="role-label">问</span>
        <p class="question-text">{{ sec.question }}</p>
      </div>
      <div v-if="sec.answer || sec.streaming" class="a-row">
        <span class="role-label answer-label">答</span>
        <div class="answer-body">
          <StreamMarkdown :text="sec.answer" :active="sec.streaming" />
        </div>
      </div>
      <div v-else-if="sec.status === 'running'" class="a-row waiting">
        <span class="role-label answer-label">答</span>
        <StreamMarkdown text="" :active="true" />
      </div>
      <SectionPreviewTable
        v-if="sec.preview && sec.preview.columns?.length"
        :columns="sec.preview.columns"
        :rows="sec.preview.rows"
      />
      <SectionInlineChart
        v-if="sec.chartSpec"
        :spec="sec.chartSpec"
        :section-index="sec.index"
      />
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import StreamMarkdown from './StreamMarkdown.vue'
import SectionPreviewTable from './SectionPreviewTable.vue'
import SectionInlineChart from './SectionInlineChart.vue'

const props = defineProps({
  sections: { type: Array, default: () => [] },
})

const rootEl = ref(null)

watch(
  () => props.sections.length,
  async () => {
    await nextTick()
    if (rootEl.value) rootEl.value.scrollTop = rootEl.value.scrollHeight
  },
)

watch(
  () => props.sections.map((s) => s.answer?.length || 0).join(','),
  async () => {
    await nextTick()
    if (rootEl.value) rootEl.value.scrollTop = rootEl.value.scrollHeight
  },
)
</script>

<style scoped>
.section-chat {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 10px 12px;
}
.section-block {
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}
.section-block:last-child {
  border-bottom: none;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.section-idx {
  font-size: 11px;
  font-weight: 600;
  color: #6366f1;
  background: #eef2ff;
  padding: 2px 8px;
  border-radius: 4px;
}
.section-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}
.q-row,
.a-row {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}
.role-label {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.answer-label {
  background: #eef2ff;
  color: #6366f1;
}
.question-text {
  margin: 0;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
}
.answer-body {
  flex: 1;
  min-width: 0;
}
.a-row.waiting {
  opacity: 0.85;
}
</style>
