<template>
  <el-dialog
    v-model="visible"
    title="报告分析"
    width="860px"
    align-center
    :close-on-click-modal="!generating"
    :close-on-press-escape="!generating"
    destroy-on-close
    class="brief-report-dialog"
    @open="onOpen"
  >
    <el-steps :active="step" finish-status="success" simple class="steps">
      <el-step title="勾选内容" />
      <el-step title="报告设置" />
      <el-step title="生成预览" />
    </el-steps>

    <div v-show="step === 0" class="step-body">
      <p class="step-desc">勾选要纳入报告的成功问数记录（顺序即章节顺序）。</p>
      <TurnPicker v-model="selectedTraceIds" :messages="messages" />
    </div>

    <div v-show="step === 1" class="step-body">
      <el-form label-position="top">
        <el-form-item label="报告提示词" required>
          <el-input
            v-model="userPrompt"
            type="textarea"
            :rows="4"
            placeholder="例如：面向区教育局领导，汇报我区智慧体育建设成效与2026年活动数据"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="汇报单位">
          <el-input v-model="org" placeholder="可选，如 XX区教育局" />
        </el-form-item>
        <el-form-item label="报告日期">
          <el-input v-model="reportDate" placeholder="可选，如 2026年7月" />
        </el-form-item>
        <BackgroundPicker
          v-model="coverBackground"
          label="封面背景"
          :items="backgrounds.cover"
          :load-error="backgroundsLoadError"
        />
        <BackgroundPicker
          v-model="endingBackground"
          label="结尾背景"
          :items="backgrounds.ending"
          :load-error="backgroundsLoadError"
        />
      </el-form>
    </div>

    <div v-show="step === 2" class="step-body step-preview">
      <div v-if="generating" class="gen-progress">
        <p>{{ progressLabel || '正在生成报告…' }}</p>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
      <PdfViewer
        v-if="pdfPreviewUrl"
        :url="pdfPreviewUrl"
        :page-count="pageCount"
        :file-size="fileSize"
        placeholder="报告完成后将在此预览"
        @open="openPdfNewTab"
      />
      <div v-else-if="!generating" class="pdf-empty">
        <PdfViewer placeholder="点击「生成 PDF」开始" />
      </div>
    </div>

    <template #footer>
      <div class="footer-actions">
        <el-button v-if="step > 0" :disabled="generating" @click="step -= 1">上一步</el-button>
        <el-button v-if="step < 2" type="primary" :disabled="!canNext" @click="step += 1">
          下一步
        </el-button>
        <el-button
          v-if="step === 2"
          type="primary"
          :loading="generating"
          :disabled="!canGenerate"
          @click="onGenerate"
        >
          生成 PDF
        </el-button>
        <el-button v-if="pdfPreviewUrl" :disabled="generating" @click="downloadPdf">下载</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createBriefReportPdfObjectUrl,
  downloadBriefReportPdf,
  fetchBriefReportBackgrounds,
  postBriefReportStream,
} from '../../api/briefReport'
import PdfViewer from '../insight/PdfViewer.vue'
import BackgroundPicker from './BackgroundPicker.vue'
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

const step = ref(0)
const selectedTraceIds = ref([])
const userPrompt = ref('')
const org = ref('')
const reportDate = ref('')
const coverBackground = ref('')
const endingBackground = ref('')
const backgrounds = ref({ cover: [], ending: [] })
const backgroundsLoadError = ref('')

const generating = ref(false)
const progressLabel = ref('')
const progressPct = ref(0)
const reportId = ref('')
const pageCount = ref(0)
const fileSize = ref(0)
const pdfObjectUrl = ref('')
const abortController = ref(null)

const pdfPreviewUrl = computed(() => pdfObjectUrl.value)

const canNext = computed(() => {
  if (step.value === 0) return selectedTraceIds.value.length > 0
  if (step.value === 1) return (userPrompt.value || '').trim().length >= 10
  return true
})

const canGenerate = computed(
  () =>
    props.sessionId &&
    selectedTraceIds.value.length > 0 &&
    (userPrompt.value || '').trim().length >= 10,
)

watch(visible, (v) => {
  if (!v) {
    abortController.value?.abort()
    generating.value = false
    revokePdfUrl()
  }
})

function revokePdfUrl() {
  if (pdfObjectUrl.value) {
    URL.revokeObjectURL(pdfObjectUrl.value)
    pdfObjectUrl.value = ''
  }
}

async function loadPdfPreview(id) {
  if (!id) return
  revokePdfUrl()
  try {
    pdfObjectUrl.value = await createBriefReportPdfObjectUrl(id)
  } catch (e) {
    ElMessage.error(e?.message || 'PDF 加载失败')
  }
}

async function loadBackgrounds() {
  backgroundsLoadError.value = ''
  try {
    const data = await fetchBriefReportBackgrounds()
    backgrounds.value = data || { cover: [], ending: [] }
    if (!coverBackground.value && backgrounds.value.cover?.length) {
      coverBackground.value = backgrounds.value.cover[0].path
    }
    if (!endingBackground.value && backgrounds.value.ending?.length) {
      endingBackground.value = backgrounds.value.ending[0].path
    }
    if (!backgrounds.value.cover?.length && !backgrounds.value.ending?.length) {
      backgroundsLoadError.value = '未扫描到背景图，请确认文件在 cover/ 与 ending/ 目录下'
    }
  } catch (err) {
    backgrounds.value = { cover: [], ending: [] }
    const data = err?.response?.data
    const msg =
      data?.error?.message ||
      data?.detail?.error?.message ||
      err?.message ||
      '背景图列表加载失败'
    backgroundsLoadError.value = `${msg}（请确认后端 BRIEF_REPORT_ENABLED=true 并已重启）`
    ElMessage.error(backgroundsLoadError.value)
  }
}

async function onOpen() {
  step.value = 0
  reportId.value = ''
  progressPct.value = 0
  progressLabel.value = ''
  await loadBackgrounds()
}

watch(step, (n) => {
  if (n === 1 && visible.value) {
    loadBackgrounds()
  }
})

async function onGenerate() {
  if (!canGenerate.value) return
  generating.value = true
  progressPct.value = 5
  progressLabel.value = '准备生成…'
  reportId.value = ''
  abortController.value = new AbortController()

  try {
    const result = await postBriefReportStream({
      sessionId: props.sessionId,
      traceIds: selectedTraceIds.value,
      userPrompt: userPrompt.value.trim(),
      options: {
        org: org.value || undefined,
        reportDate: reportDate.value || undefined,
        coverBackground: coverBackground.value || undefined,
        endingBackground: endingBackground.value || undefined,
      },
      signal: abortController.value.signal,
      onEvent: ({ type, payload }) => {
        if (type === 'progress') {
          progressLabel.value = payload.label || ''
          progressPct.value = Math.min(90, (payload.step || 1) * 18)
        }
        if (type === 'status') {
          progressLabel.value = payload.text || progressLabel.value
        }
      },
      onError: (err) => {
        ElMessage.error(err.message || '报告生成失败')
      },
    })
    if (result?.reportId) {
      reportId.value = result.reportId
      pageCount.value = result.pageCount || 0
      fileSize.value = result.fileSize || 0
      progressPct.value = 100
      progressLabel.value = '生成完成'
      await loadPdfPreview(result.reportId)
      ElMessage.success('报告已生成')
    }
  } catch (err) {
    if (err?.name !== 'AbortError') {
      ElMessage.error(err?.message || '报告生成失败')
    }
  } finally {
    generating.value = false
  }
}

function openPdfNewTab() {
  if (pdfObjectUrl.value) {
    window.open(pdfObjectUrl.value, '_blank')
    return
  }
  if (reportId.value) loadPdfPreview(reportId.value).then(() => {
    if (pdfObjectUrl.value) window.open(pdfObjectUrl.value, '_blank')
  })
}

function downloadPdf() {
  if (!reportId.value) return
  downloadBriefReportPdf(reportId.value)
}
</script>

<style scoped>
.brief-report-dialog :deep(.el-dialog) {
  max-width: 92vw;
  border-radius: 12px;
}
.brief-report-dialog :deep(.el-dialog__header) {
  padding-bottom: 8px;
}
.brief-report-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
  max-height: min(72vh, 720px);
  overflow-y: auto;
}
.steps {
  margin-bottom: 20px;
}
.step-body {
  min-height: 300px;
}
.step-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #64748b;
}
.step-preview {
  display: flex;
  flex-direction: column;
  min-height: 420px;
}
.gen-progress {
  margin-bottom: 16px;
}
.gen-progress p {
  margin: 0 0 8px;
  font-size: 13px;
  color: #475569;
}
.footer-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}
.pdf-empty {
  min-height: 360px;
}
</style>
