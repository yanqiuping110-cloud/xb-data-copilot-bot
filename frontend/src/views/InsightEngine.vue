<template>
  <div class="layout">
    <header class="header">
      <div class="header-left">
        <el-button link type="primary" @click="router.push('/ask')">← 智能问数</el-button>
        <span class="title">Insight Engine · 深度洞察</span>
      </div>
      <div class="user-area">
        <el-button link type="primary" @click="traceDrawerVisible = true">Trace</el-button>
        <span v-if="user" class="user-label">{{ user.displayName || user.username }}</span>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <section class="left-panel">
        <el-card shadow="never" class="input-card">
          <template #header>分析意图</template>
          <el-input
            v-model="requestText"
            type="textarea"
            :rows="2"
            placeholder="例如：生成本月运营深度分析报告，关注 KPI 趋势与异常"
            :disabled="running"
          />
          <div class="template-row">
            <span class="label">报告模板</span>
            <TemplateGallery v-model="templateCode" />
          </div>
          <el-button
            v-if="running && reportId"
            class="cancel-btn"
            @click="cancelReport"
          >
            取消报告
          </el-button>
          <el-button
            type="primary"
            class="start-btn"
            :loading="running"
            :disabled="!requestText.trim()"
            @click="startReport"
          >
            {{ running ? '生成中…' : '开始深度分析' }}
          </el-button>
        </el-card>

        <el-card v-if="planItems.length" shadow="never" class="plan-card insight-theme">
          <template #header>分析计划 · {{ planItems.length }} 节</template>
          <TaskTimeline :items="planItems" :section-status="sectionStatus" />
        </el-card>

        <el-card shadow="never" class="history-card">
          <template #header>历史报告</template>
          <ul v-if="history.length" class="history-list">
            <li
              v-for="h in history"
              :key="h.reportId"
              :class="{ active: h.reportId === reportId }"
              @click="loadHistory(h.reportId)"
            >
              <span class="h-title">{{ h.title }}</span>
              <el-tag size="small" :type="statusTag(h.status)">{{ h.status }}</el-tag>
            </li>
          </ul>
          <p v-else class="empty-hint">暂无历史报告</p>
        </el-card>
      </section>

      <section class="center-panel insight-theme">
        <div class="center-toolbar">
          <div class="toolbar-row">
            <StatusLine v-if="statusText" :text="statusText" />
            <ElapsedBadge v-if="elapsedMs" :elapsed-ms="elapsedMs" />
          </div>
          <PipelineStrip :active-step="pipelineStep" />
          <InsightStrip v-if="insightItems.length" :items="insightItems" />
        </div>

        <div class="center-body">
          <ActivityFeed
            v-if="activities.length && !sectionBlocks.length"
            class="activity-compact"
            :items="activities"
            placeholder=""
          />
          <SectionChat :sections="sectionBlocks" />
          <p v-if="!sectionBlocks.length && !running" class="empty-hint center-hint">
            输入分析意图并点击「开始深度分析」，章节问答与实时进度将在此展示。
          </p>
        </div>

        <div v-if="executiveSummary || reportDone" class="center-footer">
          <div v-if="executiveSummary" class="summary-block">
            <h3>执行摘要</h3>
            <StreamMarkdown :text="executiveSummary" :active="running && !reportDone" />
          </div>
          <ReportCover
            :visible="reportDone"
            compact
            :title="statusText"
            :section-total="sectionTotal"
            :page-count="pdfPageCount"
            :latency-ms="elapsedMs"
            @download="downloadPdf"
          />
        </div>
      </section>

      <section class="right-panel insight-theme">
        <el-card shadow="never" class="pdf-card">
          <template #header><span>PDF 报告</span></template>
          <PdfViewer
            :url="pdfObjectUrl"
            :page-count="pdfPageCount"
            :file-size="pdfFileSize"
            :loading="pdfLoading"
            :progress="progressPct"
            @open="downloadPdf"
          />
        </el-card>
      </section>
    </main>
    <TraceDrawer v-model:visible="traceDrawerVisible" :traces="traceList" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchMe } from '../api/auth'
import {
  branchResearchReport,
  cancelResearchReport,
  getResearchTraces,
  listResearchReports,
  postResearchStream,
  createResearchPdfObjectUrl,
  downloadResearchPdf,
  getResearchReport,
} from '../api/research'
import ActivityFeed from '../components/insight/ActivityFeed.vue'
import SectionChat from '../components/insight/SectionChat.vue'
import ElapsedBadge from '../components/insight/ElapsedBadge.vue'
import InsightStrip from '../components/insight/InsightStrip.vue'
import PdfViewer from '../components/insight/PdfViewer.vue'
import PipelineStrip from '../components/insight/PipelineStrip.vue'
import ReportCover from '../components/insight/ReportCover.vue'
import StatusLine from '../components/insight/StatusLine.vue'
import StreamMarkdown from '../components/insight/StreamMarkdown.vue'
import TaskTimeline from '../components/insight/TaskTimeline.vue'
import TemplateGallery from '../components/insight/TemplateGallery.vue'
import TraceDrawer from '../components/insight/TraceDrawer.vue'
import '../styles/insight-theme.css'

const router = useRouter()
const user = ref(null)
const requestText = ref('生成本月运营深度分析报告')
const templateCode = ref('monthly_ops')
const running = ref(false)
const reportId = ref('')
const statusText = ref('')
const activities = ref([])
const planItems = ref([])
const sectionStatus = ref({})
const executiveSummary = ref('')
const pdfObjectUrl = ref('')
const pdfLoading = ref(false)
const pdfPageCount = ref(0)
const pdfFileSize = ref(0)
const history = ref([])
const elapsedMs = ref(null)
const pipelineStep = ref(0)
const insightItems = ref([])
const reportDone = ref(false)
const traceDrawerVisible = ref(false)
const traceList = ref([])
const sectionBlocks = ref([])
let abortCtrl = null
let userCancelled = false

const ACTIVITY_MAX = 80

function findSectionBlock(index) {
  return sectionBlocks.value.find((s) => s.index === index)
}

function upsertSectionBlock(index, patch) {
  const existing = findSectionBlock(index)
  if (existing) {
    Object.assign(existing, patch)
  } else {
    sectionBlocks.value.push({ index, title: '', question: '', answer: '', streaming: false, status: 'pending', preview: null, chartSpec: null, ...patch })
  }
}

function rebuildSectionBlocksFromDetail(sections) {
  sectionBlocks.value = (sections || []).map((s) => ({
    index: s.sectionIndex,
    title: s.title,
    question: s.question || s.title,
    answer: s.answer || (s.status === 'success' ? '' : '本节数据暂不可用'),
    streaming: false,
    status: s.status === 'success' ? 'done' : s.status === 'fail' ? 'fail' : 'done',
    preview: null,
    chartSpec: null,
  }))
  activities.value = []
  for (const s of sections || []) {
    const ok = s.status === 'success'
    pushActivity(ok ? 'success' : 'warn', `${ok ? '✓' : '✗'} 第${s.sectionIndex}节 · ${s.title}`)
    if (s.answer) {
      pushActivity('info', `  解读：${String(s.answer).slice(0, 80)}${s.answer.length > 80 ? '…' : ''}`)
    }
  }
}

function revokePdfUrl() {
  if (pdfObjectUrl.value) {
    URL.revokeObjectURL(pdfObjectUrl.value)
    pdfObjectUrl.value = ''
  }
}

async function loadPdfPreview(id) {
  if (!id) return
  revokePdfUrl()
  pdfLoading.value = true
  try {
    pdfObjectUrl.value = await createResearchPdfObjectUrl(id)
  } catch (e) {
    ElMessage.error(e?.message || 'PDF 加载失败')
  } finally {
    pdfLoading.value = false
  }
}

const sectionTotal = computed(() => planItems.value.length || 0)
const sectionDone = computed(() => Object.values(sectionStatus.value).filter((s) => s === 'done').length)
const progressPct = computed(() => {
  if (!sectionTotal.value) return running.value ? 5 : 0
  return Math.min(99, Math.round((sectionDone.value / sectionTotal.value) * 90) + 5)
})

function statusTag(status) {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'fail') return 'danger'
  return 'info'
}

function pushActivity(level, message) {
  activities.value.push({ level, message })
  if (activities.value.length > ACTIVITY_MAX) {
    activities.value.splice(0, activities.value.length - ACTIVITY_MAX)
  }
}

async function refreshHistory() {
  try {
    history.value = await listResearchReports()
  } catch {
    /* ignore */
  }
}

async function loadHistory(id) {
  try {
    const detail = await getResearchReport(id)
    reportId.value = detail.reportId
    executiveSummary.value = detail.executiveSummary || ''
    if (detail.pdfUrl || detail.pdfPageCount) {
      pdfPageCount.value = detail.pdfPageCount || 0
      pdfFileSize.value = detail.pdfFileSize || 0
      reportDone.value = true
      await loadPdfPreview(id)
    }
    planItems.value = (detail.sections || []).map((s) => ({
      index: s.sectionIndex,
      title: s.title,
      intent: s.intent || 'open_query',
    }))
    sectionStatus.value = {}
    for (const s of detail.sections || []) {
      sectionStatus.value[s.sectionIndex] = s.status === 'success' ? 'done' : s.status
    }
    rebuildSectionBlocksFromDetail(detail.sections || [])
    if (detail.insights?.length) {
      insightItems.value = detail.insights.map((x) => ({
        type: x.type || 'info',
        text: x.text,
      }))
    }
    statusText.value = `已加载历史报告 · ${detail.status}`
  } catch {
    ElMessage.error('加载报告失败')
  }
}

function handleEvent({ type, payload }) {
  switch (type) {
    case 'report_started':
      reportId.value = payload.reportId
      statusText.value = payload.title
      pushActivity('info', `报告已创建 · ${payload.reportId}`)
      break
    case 'status':
      statusText.value = payload.text
      break
    case 'activity':
      pushActivity(payload.level || 'info', payload.message)
      break
    case 'plan_item':
      planItems.value.push({
        index: payload.index,
        title: payload.title,
        intent: payload.intent,
      })
      break
    case 'section_start':
      sectionStatus.value[payload.sectionIndex] = 'running'
      upsertSectionBlock(payload.sectionIndex, {
        title: payload.title,
        question: payload.question || payload.title,
        answer: '',
        streaming: true,
        status: 'running',
        preview: null,
        chartSpec: null,
      })
      pushActivity('info', `▸ 第${payload.sectionIndex}节 · ${payload.title}`)
      break
    case 'section_progress':
      statusText.value = `第${payload.sectionIndex}节 · ${payload.label}`
      if (payload.pipelineStep) pipelineStep.value = payload.pipelineStep
      break
    case 'text_delta':
      if (payload.scope === 'summary') {
        executiveSummary.value = (executiveSummary.value || '') + (payload.delta || '')
      } else if (payload.scope === 'section' && payload.sectionIndex != null) {
        const block = findSectionBlock(payload.sectionIndex)
        if (block) {
          block.answer = (block.answer || '') + (payload.delta || '')
          block.streaming = true
        } else {
          upsertSectionBlock(payload.sectionIndex, {
            answer: payload.delta || '',
            streaming: true,
            status: 'running',
          })
        }
      } else if (payload.scope === 'recommendation') {
        executiveSummary.value = (executiveSummary.value || '') + (payload.delta || '')
      }
      break
    case 'section_done':
      sectionStatus.value[payload.sectionIndex] =
        payload.status === 'success' ? 'done' : 'fail'
      {
        const block = findSectionBlock(payload.sectionIndex)
        if (block) {
          block.streaming = false
          block.status = payload.status === 'success' ? 'done' : 'fail'
          if (payload.answer && (!block.answer || payload.answer.length > block.answer.length)) {
            block.answer = payload.answer
          }
        }
      }
      break
    case 'insights_ready':
      executiveSummary.value = payload.executiveSummary || executiveSummary.value
      insightItems.value = (payload.insights || []).map((x) => ({
        type: x.type || 'info',
        text: x.text,
      }))
      pushActivity('success', '洞察汇总完成')
      break
    case 'pdf_ready':
      pdfPageCount.value = payload.pageCount
      pdfFileSize.value = payload.fileSizeBytes
      reportDone.value = true
      pushActivity('success', `PDF 已生成 · ${payload.pageCount} 页`)
      if (reportId.value) loadPdfPreview(reportId.value)
      break
    case 'report_done':
      reportDone.value = true
      if (reportId.value) loadTraces(reportId.value)
      break
    case 'heartbeat':
      elapsedMs.value = payload.elapsedMs
      break
    case 'section_preview': {
      const block = findSectionBlock(payload.sectionIndex)
      if (block) {
        block.preview = {
          columns: payload.columns || [],
          rows: payload.rowsSample || payload.rows || [],
        }
      }
      pushActivity('info', `第${payload.sectionIndex}节 · 数据预览就绪`)
      break
    }
    case 'chart_ready': {
      const block = findSectionBlock(payload.sectionIndex)
      if (block) block.chartSpec = payload.chartSpec || null
      pushActivity('info', `第${payload.sectionIndex}节 · 图表就绪`)
      break
    }
    case 'plan_revealed':
      break
    default:
      break
  }
}

async function loadTraces(id) {
  try {
    const data = await getResearchTraces(id)
    traceList.value = data.traces || []
  } catch {
    traceList.value = []
  }
}

async function branchFromSection(sectionIndex) {
  if (!reportId.value) return
  try {
    await branchResearchReport(reportId.value, {
      branchFromSection: sectionIndex,
      requestText: requestText.value,
      templateCode: templateCode.value,
      options: { stream: true },
    })
    ElMessage.success(`已从第 ${sectionIndex} 节创建分支（请刷新后查看新报告）`)
  } catch {
    ElMessage.error('分支创建失败')
  }
}

async function downloadPdf() {
  if (!reportId.value) return
  try {
    await downloadResearchPdf(reportId.value)
  } catch (e) {
    ElMessage.error(e?.message || 'PDF 下载失败')
  }
}

async function cancelReport() {
  if (!reportId.value || !running.value) return
  userCancelled = true
  try {
    abortCtrl?.abort()
    await cancelResearchReport(reportId.value)
    running.value = false
    statusText.value = '报告已取消'
    pushActivity('warn', '已取消报告')
  } catch {
    ElMessage.error('取消失败')
  }
}

async function startReport() {
  if (running.value) return
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  userCancelled = false
  running.value = true
  reportId.value = ''
  activities.value = []
  planItems.value = []
  sectionStatus.value = {}
  sectionBlocks.value = []
  executiveSummary.value = ''
  revokePdfUrl()
  pdfPageCount.value = 0
  pdfFileSize.value = 0
  insightItems.value = []
  reportDone.value = false
  pipelineStep.value = 0
  traceList.value = []

  try {
    await postResearchStream({
      requestText: requestText.value.trim(),
      templateCode: templateCode.value,
      onEvent: handleEvent,
      onError: (e) => {
        if (userCancelled || e.code === 'CANCELLED') return
        ElMessage.error(e.message || '报告生成失败')
        pushActivity('warn', e.message || '错误')
      },
      signal: abortCtrl.signal,
    })
    if (!userCancelled) statusText.value = '报告生成完成'
    await refreshHistory()
  } catch (err) {
    if (err?.name !== 'AbortError' && !userCancelled) {
      ElMessage.error(err?.message || '报告生成失败')
    }
  } finally {
    running.value = false
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  router.push('/login')
}

onMounted(async () => {
  try {
    user.value = await fetchMe()
  } catch {
    router.push('/login')
  }
  await refreshHistory()
})

onUnmounted(() => {
  revokePdfUrl()
})
</script>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f8fafc;
}
.header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}
.main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr) 300px;
  gap: 8px;
  padding: 8px;
  overflow: hidden;
}
.left-panel,
.center-panel,
.right-panel {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}
.left-panel :deep(.el-card) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 8px;
}
.left-panel :deep(.el-card__header) {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
}
.left-panel :deep(.el-card__body) {
  padding: 10px 12px;
}
.input-card {
  flex-shrink: 0;
}
.input-card .template-row {
  margin: 8px 0;
}
.input-card .label {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.start-btn,
.cancel-btn {
  width: 100%;
}
.cancel-btn {
  margin-bottom: 6px;
}
.plan-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.plan-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
}
.history-card {
  flex-shrink: 0;
  max-height: 32%;
  overflow: hidden;
}
.history-card :deep(.el-card__body) {
  max-height: 120px;
  overflow-y: auto;
  padding-top: 6px;
  padding-bottom: 6px;
}
.center-panel {
  background: transparent;
}
.center-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.center-toolbar :deep(.pipeline-strip) {
  padding: 2px 0;
}
.center-toolbar :deep(.elapsed-badge) {
  flex-shrink: 0;
}
.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.center-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  gap: 6px;
}
.center-body :deep(.section-chat) {
  flex: 1;
  min-height: 0;
}
.activity-compact {
  flex-shrink: 0;
  max-height: 88px;
  overflow-y: auto;
}
.center-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 38%;
}
.summary-block {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 8px 10px;
  max-height: 72px;
  overflow-y: auto;
}
.summary-block h3 {
  margin: 0 0 4px;
  font-size: 12px;
  color: #64748b;
}
.summary-block :deep(.stream-md) {
  font-size: 12px;
  line-height: 1.45;
}
.right-panel :deep(.el-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 8px;
}
.right-panel :deep(.el-card__header) {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
}
.right-panel :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 10px 10px;
}
.pdf-card {
  flex: 1;
  min-height: 0;
}
.plan-list,
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.plan-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 13px;
}
.plan-list li.running {
  color: #2563eb;
}
.plan-list li.done {
  color: #16a34a;
}
.plan-list li.fail {
  color: #dc2626;
}
.plan-list .idx {
  width: 20px;
  font-weight: 600;
  color: #94a3b8;
}
.plan-title {
  flex: 1;
}
.history-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.history-list li:hover,
.history-list li.active {
  background: #eff6ff;
}
.h-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.status-bar {
  padding: 10px 14px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  font-size: 14px;
  color: #334155;
}
.activity-feed {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
}
.feed-item {
  padding: 4px 0;
  color: #475569;
}
.feed-item.success {
  color: #16a34a;
}
.feed-item.warn {
  color: #d97706;
}
.feed-placeholder {
  color: #94a3b8;
  text-align: center;
  padding: 40px 16px;
}
.empty-hint {
  font-size: 12px;
  color: #94a3b8;
  margin: 0;
}
.center-hint {
  text-align: center;
  padding: 16px 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px dashed #e2e8f0;
  font-size: 12px;
}
@media (max-width: 1100px) {
  .layout {
    height: auto;
    min-height: 100vh;
    overflow: auto;
  }
  .main {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }
  .left-panel,
  .center-panel,
  .right-panel {
    height: auto;
    max-height: none;
  }
  .history-card {
    max-height: none;
  }
  .center-footer {
    max-height: none;
  }
  .pdf-card {
    min-height: 420px;
  }
}
</style>
