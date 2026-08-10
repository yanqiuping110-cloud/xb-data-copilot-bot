<template>
  <div class="layout">
    <header class="header">
      <span class="title">智能问数</span>
      <div class="user-area">
        <template v-if="user?.role === 'SCHOOL' && boundSchools.length">
          <el-select
            v-model="selectedSchId"
            placeholder="选择学校"
            style="width: 200px"
            @change="onSwitchSchool"
          >
            <el-option
              v-for="s in boundSchools"
              :key="s.schId"
              :label="s.schName ? `${s.schName} (${s.schId})` : String(s.schId)"
              :value="s.schId"
            />
          </el-select>
        </template>
        <span v-if="user" class="user-label">{{ user.displayName || user.username }}（{{ user.role }}）</span>
        <el-button v-if="user?.role === 'ADMIN'" link type="primary" @click="router.push('/admin/users')">
          用户管理
        </el-button>
        <el-button
          v-if="user?.role === 'ADMIN'"
          link
          type="primary"
          @click="router.push('/admin/meta/tables')"
        >
          元数据管理
        </el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <aside class="session-sidebar">
        <el-button
          type="primary"
          class="new-chat-btn"
          :loading="sessionBusy"
          :disabled="sessionBusy || !pageReady"
          @click="onNewChat"
        >
          + 新对话
        </el-button>
        <ul class="session-list">
          <li
            v-for="s in sessions"
            :key="s.sessionId"
            :class="['session-item', { active: s.sessionId === sessionId }]"
            @click="onSelectSession(s.sessionId)"
          >
            <span class="session-title">{{ s.title || '新对话' }}</span>
            <el-button
              link
              type="danger"
              size="small"
              class="session-del"
              @click.stop="onDeleteSession(s.sessionId)"
            >
              删
            </el-button>
          </li>
        </ul>
        <el-button class="pref-btn" link type="primary" @click="openPrefDrawer">偏好设置</el-button>
      </aside>

      <el-drawer v-model="prefDrawerVisible" title="问数偏好（跨对话生效）" size="360px">
        <p class="pref-hint">以下偏好会注入后续问数 Prompt，不影响当前对话历史。</p>
        <el-form label-width="100px" label-position="top">
          <el-form-item label="默认时间范围">
            <el-select v-model="prefForm.defaultTimeRange" clearable placeholder="不指定" style="width: 100%">
              <el-option label="本月" value="month" />
              <el-option label="本周" value="week" />
              <el-option label="最近7天" value="last_7_days" />
              <el-option label="昨日" value="yesterday" />
            </el-select>
          </el-form-item>
          <el-form-item label="常用统计粒度">
            <el-select v-model="prefForm.preferredGrain" clearable placeholder="不指定" style="width: 100%">
              <el-option label="按日" value="daily" />
              <el-option label="按周" value="weekly" />
              <el-option label="按月" value="monthly" />
            </el-select>
          </el-form-item>
          <el-form-item label="回答风格">
            <el-select v-model="prefForm.answerStyle" clearable placeholder="默认" style="width: 100%">
              <el-option label="简洁" value="concise" />
              <el-option label="详细" value="detailed" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="prefDrawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="prefSaving" @click="savePreferences">保存</el-button>
        </template>
      </el-drawer>

      <div class="chat-area">
        <div class="chat-shell">
          <div ref="messagesEl" class="messages" @scroll="onMessagesScroll">
            <div v-for="(msg, idx) in messages" :key="messageKey(msg, idx)" :class="['msg', msg.role]">
              <!-- 用户消息 -->
              <div v-if="msg.role === 'user'" class="bubble user-bubble">{{ msg.text }}</div>

              <!-- 助手消息 -->
              <div v-else class="response-card" :class="{ error: msg.isError }">
                <AskPipelineHeader
                  v-if="msg.pipelineStep > 0"
                  :active-step="msg.pipelineStep"
                  :status-text="msg.statusText"
                  :show-status="loading && idx === messages.length - 1 && !!msg.statusText"
                />
                <div class="answer-line">{{ msg.text }}</div>

                <details
                  v-if="msg.timeline?.length"
                  class="progress-details"
                  :open="msg.progressOpen"
                >
                  <summary>{{ timelineSummary(msg.timeline) }}</summary>
                  <AskTimeline
                    :steps="msg.timeline"
                    :now-ms="progressClock"
                    :show-thinking="canShowThinking"
                  />
                </details>

                <template v-if="msg.intermediateSteps?.length">
                  <div class="section-label">分步查询</div>
                  <div
                    v-for="(step, sti) in msg.intermediateSteps"
                    :key="sti"
                    class="intermediate-step"
                  >
                    <div class="intermediate-title">
                      步骤 {{ step.stepId }}：{{ step.goal }}
                      <span v-if="step.rowCount != null" class="intermediate-meta">
                        （{{ step.rowCount }} 行）
                      </span>
                    </div>
                    <pre v-if="canShowSqlInChat && step.sql" class="sql-block sql-block-sm">{{ step.sql }}</pre>
                    <div
                      v-if="step.columns?.length && step.rows?.length"
                      class="table-wrap table-wrap-sm"
                    >
                      <el-table
                        :data="intermediateTableRows(step)"
                        border
                        stripe
                        size="small"
                        max-height="200"
                      >
                        <el-table-column
                          v-for="col in step.columns"
                          :key="col"
                          :prop="col"
                          :label="col"
                          min-width="80"
                          show-overflow-tooltip
                        />
                      </el-table>
                    </div>
                  </div>
                </template>

                <template v-if="canShowSqlInChat && msg.result?.sql">
                  <div class="section-label">SQL</div>
                  <pre class="sql-block">{{ msg.result.sql }}</pre>
                </template>

                <ResultPanel
                  v-if="msg.result?.columns?.length && msg.result?.rows?.length"
                  :key="resultPanelKey(msg)"
                  :columns="msg.result.columns"
                  :rows="msg.result.rows"
                  :chart-spec="msg.chartSpec"
                />

                <div v-if="msg.meta" class="meta">{{ msg.meta }}</div>

                <div v-if="msg.traceId" class="feedback-bar">
                  <span class="feedback-hint">这条回答有帮助吗？</span>
                  <div class="feedback-actions">
                    <el-button
                      size="small"
                      round
                      :type="msg.feedback === 'up' ? 'success' : 'default'"
                      :loading="feedbackLoadingId === msg.traceId"
                      @click="onFeedback(msg, 'up')"
                    >
                      有用
                    </el-button>
                    <el-button
                      size="small"
                      round
                      :type="msg.feedback === 'down' ? 'danger' : 'default'"
                      :loading="feedbackLoadingId === msg.traceId"
                      @click="onFeedback(msg, 'down')"
                    >
                      不准
                    </el-button>
                    <el-button
                      size="small"
                      round
                      plain
                      type="warning"
                      :loading="feedbackLoadingId === msg.traceId"
                      @click="onMarkBadcase(msg)"
                    >
                      标记 badcase
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="sessionId" class="chat-toolbar">
            <div class="toolbar-left">
              <el-button
                type="success"
                class="toolbar-report-btn"
                @click="briefReportDrawerVisible = true"
              >
                报告分析
              </el-button>
              <el-button
                type="primary"
                plain
                class="toolbar-excel-btn"
                @click="excelExportDrawerVisible = true"
              >
                导出 Excel
              </el-button>
              <span v-if="briefReportTurnCount" class="toolbar-meta">
                本对话 {{ briefReportTurnCount }} 条可纳入报告
              </span>
            </div>
            <span class="toolbar-hint">勾选问数记录，生成 PDF 报告或导出 Excel 数据表</span>
          </div>

          <div class="input-panel">
            <el-form class="input-row" @submit.prevent="onAsk">
              <el-input
                v-model="question"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="例如：本校本月跳绳参与人数 / 最近7天每日趋势"
                :disabled="loading || needSelectSchool"
                @keydown.enter.exact.prevent="onAsk"
              />
              <el-button
                v-if="!loading"
                type="primary"
                native-type="submit"
                class="ask-btn"
                :disabled="needSelectSchool"
              >
                提问
              </el-button>
              <el-button
                v-else
                type="danger"
                plain
                class="ask-btn"
                :loading="cancelling"
                @click="onCancelAsk"
              >
                中断
              </el-button>
            </el-form>
            <el-alert
              v-if="needSelectSchool"
              title="请先选择学校后再提问"
              type="warning"
              :closable="false"
              show-icon
              class="school-alert"
            />
          </div>
        </div>
      </div>
    </main>

    <BriefReportDrawer
      v-model="briefReportDrawerVisible"
      :session-id="sessionId"
      :messages="messages"
    />
    <ExcelExportDrawer
      v-model="excelExportDrawerVisible"
      :session-id="sessionId"
      :messages="messages"
    />
  </div>
</template>

<script setup>
/** 问数对话页：左侧对话栏 + 学校切换 + SSE 流式 POST /api/v1/ask */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchMe, switchSchool } from '../api/auth'
import { postAskStream, postAskCancel } from '../api/ask'
import { postFeedback } from '../api/feedback'
import {
  createSession,
  deleteSession,
  fetchPreferences,
  fetchSessionMessages,
  fetchSessions,
  updatePreferences,
} from '../api/sessions'
import ResultPanel from '../components/ResultPanel.vue'
import AskPipelineHeader from '../components/ask/AskPipelineHeader.vue'
import AskTimeline from '../components/ask/AskTimeline.vue'
import BriefReportDrawer from '../components/brief-report/BriefReportDrawer.vue'
import ExcelExportDrawer from '../components/brief-report/ExcelExportDrawer.vue'
import { countReportableMessages } from '../utils/briefReportTurn.js'
import {
  applyProgressEvent,
  applyThinkingDelta,
  createAssistantStreamMessage,
  finalizeTimeline,
  formatDurationMs,
  timelineTotalMs,
} from '../utils/askProgress.js'

const router = useRouter()
const user = ref(null)
const boundSchools = ref([])
const selectedSchId = ref(null)
const question = ref('')
const loading = ref(false)
const cancelling = ref(false)
const progressClock = ref(Date.now())
let progressClockTimer = null

watch(loading, (on) => {
  if (on) {
    progressClock.value = Date.now()
    if (!progressClockTimer) {
      progressClockTimer = setInterval(() => {
        progressClock.value = Date.now()
      }, 200)
    }
  } else if (progressClockTimer) {
    clearInterval(progressClockTimer)
    progressClockTimer = null
  }
})

onUnmounted(() => {
  if (progressClockTimer) {
    clearInterval(progressClockTimer)
    progressClockTimer = null
  }
})
const abortController = ref(null)
const currentTraceId = ref(null)
const messages = ref([])
const feedbackLoadingId = ref(null)
const sessionId = ref(null)
const sessions = ref([])
const pageReady = ref(false)
const sessionBusy = ref(false)
const messagesEl = ref(null)
const WELCOME_TEXT =
  '你好，我是问数助手。可尝试：「本校本月跳绳参与人数」「最近7天每日趋势」「昨日全平台活动参与人次」。'
const stickToBottom = ref(true)
const SCROLL_THRESHOLD = 48
const prefDrawerVisible = ref(false)
const prefSaving = ref(false)
const prefForm = ref({
  defaultTimeRange: null,
  preferredGrain: null,
  answerStyle: null,
})
const briefReportDrawerVisible = ref(false)
const excelExportDrawerVisible = ref(false)

const briefReportTurnCount = computed(() => countReportableMessages(messages.value))

const needSelectSchool = computed(
  () => user.value?.role === 'SCHOOL' && boundSchools.value.length > 1 && !selectedSchId.value,
)

/** 仅系统管理员在聊天对话框内可见 SQL */
const canShowSqlInChat = computed(() => user.value?.role === 'ADMIN')
const canShowThinking = computed(() => user.value?.role === 'ADMIN')

function intermediateTableRows(step) {
  if (!step?.columns?.length || !step?.rows?.length) return []
  return step.rows.map((row) =>
    Object.fromEntries(step.columns.map((col, i) => [col, row[i]])),
  )
}

function upsertIntermediateStep(msg, detail) {
  if (!detail?.goal) return
  if (!msg.intermediateSteps) msg.intermediateSteps = []
  const stepId = detail.stepId
  const existing = msg.intermediateSteps.find((s) => s.stepId === stepId)
  const preview = detail.intermediatePreview
  const lastPreview = preview?.length ? preview[preview.length - 1] : null
  const payload = {
    stepId,
    goal: detail.goal,
    rowCount: detail.rowCount ?? lastPreview?.rowCount,
    columns: lastPreview?.columns,
  }
  if (existing) {
    Object.assign(existing, payload)
  } else {
    msg.intermediateSteps.push(payload)
  }
}

function mapIntermediateResults(items) {
  if (!items?.length) return undefined
  return items.map((ir) => ({
    stepId: ir.stepId,
    goal: ir.goal,
    sql: ir.sql,
    columns: ir.columns,
    rows: ir.rows,
    rowCount: ir.rowCount,
  }))
}

function resultTableRows(result) {
  if (!result?.columns?.length || !result?.rows?.length) return []
  return result.rows.map((row) =>
    Object.fromEntries(result.columns.map((col, i) => [col, row[i]])),
  )
}

function buildMeta(m) {
  const parts = []
  if (m.traceId) parts.push(`trace: ${m.traceId}`)
  if (m.latencyMs) parts.push(`${m.latencyMs}ms`)
  return parts.length ? parts.join(' · ') : undefined
}

function messageKey(msg, idx) {
  if (msg.traceId) return `${sessionId.value}-${msg.traceId}`
  return `${sessionId.value}-${idx}-${msg.role}`
}

function resultPanelKey(msg) {
  return `${sessionId.value}-${msg.traceId || 'no-trace'}`
}

function notifyChartsResize() {
  nextTick(() => {
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'))
      setTimeout(() => window.dispatchEvent(new Event('resize')), 120)
      setTimeout(() => window.dispatchEvent(new Event('resize')), 400)
    })
  })
}

function buildAssistantHistoryMessage(m) {
  const isSuccess = m.status === 'success'
  const isCancelled = m.status === 'cancelled'
  const text = isSuccess
    ? m.answer || (m.rowCount != null ? `根据查询结果，共返回 ${m.rowCount} 行数据。` : '查询完成')
    : isCancelled
      ? m.errorMessage || m.answer || '已中断查询（用户主动取消）'
      : m.errorMessage || m.answer || m.status
  return {
    role: 'assistant',
    text,
    isError: !isSuccess,
    meta: buildMeta(m),
    traceId: m.traceId,
    feedback: null,
    result: {
      sql: user.value?.role === 'ADMIN' ? m.finalSql || undefined : undefined,
      columns: m.columns || undefined,
      rows: m.rows || undefined,
    },
    chartSpec: m.chartSpec || undefined,
    intermediateSteps: mapIntermediateResults(m.intermediateResults),
  }
}

function isAtBottom(el) {
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_THRESHOLD
}

function scrollMessagesToBottom() {
  const el = messagesEl.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

function onMessagesScroll() {
  stickToBottom.value = isAtBottom(messagesEl.value)
}

watch(
  messages,
  () => {
    if (!stickToBottom.value) return
    nextTick(scrollMessagesToBottom)
  },
  { deep: true },
)

function resetWelcomeMessages() {
  messages.value = [{ role: 'assistant', text: WELCOME_TEXT }]
}

async function loadSessions() {
  const res = await fetchSessions()
  sessions.value = res.items || []
}

async function activateSession(id) {
  sessionId.value = id
  localStorage.setItem('activeSessionId', id)
  const res = await fetchSessionMessages(id)
  resetWelcomeMessages()
  for (const m of res.messages || []) {
    messages.value.push({ role: 'user', text: m.question })
    messages.value.push(buildAssistantHistoryMessage(m))
  }
  await nextTick()
  scrollMessagesToBottom()
  notifyChartsResize()
}

async function abortOngoingAsk() {
  if (!loading.value) return
  const tid = currentTraceId.value
  try {
    if (tid) {
      try {
        await postAskCancel(tid)
      } catch {
        /* 已结束则忽略，仍断开流 */
      }
    }
    abortController.value?.abort()
  } finally {
    loading.value = false
    cancelling.value = false
    currentTraceId.value = null
    abortController.value = null
  }
}

async function onNewChat() {
  if (sessionBusy.value) return
  sessionBusy.value = true
  try {
    await abortOngoingAsk()
    const res = await createSession()
    await loadSessions()
    await activateSession(res.sessionId)
  } catch (err) {
    if (!pageReady.value) {
      resetWelcomeMessages()
    }
    if (err?.code !== 'ERR_CANCELED') {
      ElMessage.error(err?.message || '创建新对话失败，请稍后重试')
    }
  } finally {
    sessionBusy.value = false
  }
}

async function onSelectSession(id) {
  if (id === sessionId.value) return
  await activateSession(id)
}

async function loadPreferences() {
  try {
    const res = await fetchPreferences()
    const map = Object.fromEntries((res.items || []).map((p) => [p.prefKey, p.prefValue]))
    prefForm.value.defaultTimeRange = map.default_time_range?.unit ?? map.default_time_range ?? null
    prefForm.value.preferredGrain = map.preferred_grain ?? null
    prefForm.value.answerStyle = map.answer_style ?? null
  } catch {
    /* 偏好加载失败不阻断问数 */
  }
}

function openPrefDrawer() {
  prefDrawerVisible.value = true
  loadPreferences()
}

async function savePreferences() {
  const prefs = {}
  if (prefForm.value.defaultTimeRange) {
    prefs.default_time_range = { unit: prefForm.value.defaultTimeRange }
  }
  if (prefForm.value.preferredGrain) {
    prefs.preferred_grain = prefForm.value.preferredGrain
  }
  if (prefForm.value.answerStyle) {
    prefs.answer_style = prefForm.value.answerStyle
  }
  prefSaving.value = true
  try {
    await updatePreferences(prefs)
    ElMessage.success('偏好已保存，后续问数将自动参考')
    prefDrawerVisible.value = false
  } finally {
    prefSaving.value = false
  }
}

async function onDeleteSession(id) {
  await deleteSession(id)
  await loadSessions()
  if (sessionId.value === id) {
    if (sessions.value.length) {
      await activateSession(sessions.value[0].sessionId)
    } else {
      await onNewChat()
    }
  }
}

onMounted(async () => {
  try {
    const res = await fetchMe()
    user.value = res.user
    localStorage.setItem('userRole', res.user.role)
    boundSchools.value = res.user.boundSchools || []
    selectedSchId.value = res.user.activeSchId ?? boundSchools.value[0]?.schId ?? null
    resetWelcomeMessages()
    pageReady.value = true

    try {
      await loadSessions()
      const saved = localStorage.getItem('activeSessionId')
      const owned = saved && sessions.value.some((s) => s.sessionId === saved)
      if (owned) {
        await activateSession(saved)
      } else if (sessions.value.length) {
        await activateSession(sessions.value[0].sessionId)
      } else {
        await onNewChat()
      }
    } catch {
      ElMessage.error('加载对话列表失败，可点击「新对话」重试')
    }
  } catch {
    router.push('/login')
  }
})

function timelineSummary(timeline) {
  if (!timeline?.length) return ''
  const total = timelineTotalMs(timeline, progressClock.value)
  const totalText = total > 0 ? ` · ${formatDurationMs(total)}` : ''
  return `执行详情（${timeline.length} 步${totalText}）`
}

async function onSwitchSchool(schId) {
  try {
    const res = await switchSchool(schId)
    localStorage.setItem('accessToken', res.accessToken)
    user.value = res.user
    selectedSchId.value = schId
    ElMessage.success('已切换学校')
  } catch {
    selectedSchId.value = user.value?.activeSchId ?? null
  }
}

async function onCancelAsk() {
  if (!loading.value) return
  cancelling.value = true
  try {
    await abortOngoingAsk()
  } finally {
    cancelling.value = false
  }
}

function applyCancelledMessage(msg, traceId) {
  msg.text = '已中断查询（用户主动取消）'
  msg.isError = true
  msg.meta = traceId ? `trace: ${traceId}` : undefined
  msg.traceId = traceId
  finalizeTimeline(msg)
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || loading.value) return
  stickToBottom.value = true
  messages.value.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true
  cancelling.value = false

  const traceId = crypto.randomUUID()
  currentTraceId.value = traceId
  abortController.value = new AbortController()

  const assistantIdx = messages.value.length
  messages.value.push(createAssistantStreamMessage())

  const streamHandlers = {
      onProgress: (evt) => {
        const msg = messages.value[assistantIdx]
        if (!msg) return
        applyProgressEvent(msg, evt)
        // 进行中保持执行详情展开，便于看到当前步骤与实时耗时
        if (evt.status === 'running') msg.progressOpen = true
        if (evt.node === 'execute_plan_sql_step' && evt.detail) {
          upsertIntermediateStep(msg, evt.detail)
        }
      },
      onTextDelta: ({ delta }) => {
        const msg = messages.value[assistantIdx]
        if (!msg || !delta) return
        if (msg.text === '正在分析您的问题…') {
          msg.text = delta
        } else {
          msg.text = (msg.text || '') + delta
        }
      },
      onDone: (res) => {
        if (res.sessionId && res.sessionId !== sessionId.value) {
          sessionId.value = res.sessionId
          localStorage.setItem('activeSessionId', res.sessionId)
        }
        const msg = messages.value[assistantIdx]
        const isSuccess = res.status === 'success'
        const isCancelled = res.status === 'cancelled'
        msg.isError = !isSuccess
        if (isCancelled) {
          applyCancelledMessage(msg, res.traceId || traceId)
          return
        }
        msg.text = isSuccess
          ? res.answer || '查询完成'
          : res.errorMessage || '未能回答该问题'
        msg.meta = res.traceId
          ? `trace: ${res.traceId}${res.latencyMs ? ` · ${res.latencyMs}ms` : ''}`
          : undefined
        msg.traceId = res.traceId
        msg.feedback = null
        msg.result = {
          sql: canShowSqlInChat.value ? res.sql || undefined : undefined,
          columns: res.columns || undefined,
          rows: res.rows || undefined,
        }
        msg.chartSpec = res.chartSpec || undefined
        msg.intermediateSteps = mapIntermediateResults(res.intermediateResults) || msg.intermediateSteps
        finalizeTimeline(msg)
        notifyChartsResize()
      },
      onError: (err) => {
        const msg = messages.value[assistantIdx]
        msg.text = err.message || '问数失败，请稍后重试'
        msg.isError = true
        msg.meta = undefined
        finalizeTimeline(msg)
      },
    }

  if (canShowThinking.value) {
    streamHandlers.onThinkingDelta = (evt) => {
      const msg = messages.value[assistantIdx]
      if (!msg) return
      applyThinkingDelta(msg, evt)
      if (evt?.delta) msg.progressOpen = true
    }
  }

  try {
    await postAskStream({
      question: q,
      sessionId: sessionId.value,
      traceId,
      signal: abortController.value.signal,
      ...streamHandlers,
    })
  } catch (err) {
    const msg = messages.value[assistantIdx]
    if (err?.name === 'AbortError') {
      applyCancelledMessage(msg, currentTraceId.value)
    } else if (msg.text === '正在分析您的问题…') {
      msg.text = '请求失败，请稍后重试'
      msg.isError = true
    }
  } finally {
    loading.value = false
    cancelling.value = false
    abortController.value = null
    currentTraceId.value = null
    await loadSessions()
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}

async function onFeedback(msg, kind) {
  if (!msg.traceId) return
  feedbackLoadingId.value = msg.traceId
  try {
    await postFeedback({ traceId: msg.traceId, feedback: kind })
    msg.feedback = kind
    ElMessage.success(kind === 'up' ? '感谢反馈' : '已记录，我们会改进')
  } finally {
    feedbackLoadingId.value = null
  }
}

async function onMarkBadcase(msg) {
  if (!msg.traceId) return
  feedbackLoadingId.value = msg.traceId
  try {
    await postFeedback({
      traceId: msg.traceId,
      feedback: 'down',
      isBadcase: true,
    })
    msg.feedback = 'down'
    ElMessage.success('已标记为 badcase，管理员可在元数据管理中处理')
  } finally {
    feedbackLoadingId.value = null
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(160deg, #eef2f8 0%, #f5f7fa 45%, #fafbfc 100%);
  overflow: hidden;
}

.header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.title {
  font-weight: 700;
  font-size: 18px;
  color: #1a1a2e;
  letter-spacing: 0.02em;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: calc(100% - 120px);
}

.user-label {
  font-size: 13px;
  color: #606266;
}

.main {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px 20px;
  min-height: 0;
  max-width: 1680px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

.session-sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e8ecf2;
  padding: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}

.new-chat-btn {
  width: 100%;
  margin-bottom: 12px;
  border-radius: 8px;
}

.session-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 500;
}

.session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 4px;
}

.session-del {
  flex-shrink: 0;
  padding: 0 4px;
  opacity: 0.6;
}

.session-item:hover .session-del {
  opacity: 1;
}

.pref-btn {
  width: 100%;
  margin-top: 8px;
  justify-content: flex-start;
}

.pref-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

.chat-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-shell {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e8ecf2;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  min-height: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  min-height: 0;
}

.msg {
  margin-bottom: 20px;
}

.msg.user {
  display: flex;
  justify-content: flex-end;
}

.user-bubble {
  display: inline-block;
  max-width: min(680px, 72%);
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
  background: linear-gradient(135deg, #409eff 0%, #337ecc 100%);
  color: #fff;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.25);
}

.response-card {
  max-width: min(920px, 92%);
  padding: 16px 18px;
  border-radius: 4px 16px 16px 16px;
  background: #fafbfc;
  border: 1px solid #e8ecf2;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.response-card.error {
  background: #fef0f0;
  border-color: #fde2e2;
}

.answer-line {
  font-size: 14px;
  line-height: 1.65;
  color: #303133;
  white-space: pre-wrap;
}

.sql-block-sm {
  font-size: 11px;
  padding: 8px 10px;
}

.intermediate-step {
  margin-bottom: 12px;
}

.intermediate-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}

.intermediate-meta {
  font-size: 12px;
  color: #909399;
}

.table-wrap-sm {
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

.sql-block {
  margin: 0;
  padding: 12px 14px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.table-wrap {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.meta {
  margin-top: 10px;
  font-size: 11px;
  color: #b0b8c4;
  font-family: monospace;
}

.progress-details {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.progress-details summary {
  cursor: pointer;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  user-select: none;
  list-style-position: inside;
}

.progress-details :deep(.ask-timeline) {
  padding: 8px 10px 12px;
}

.feedback-bar {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #e4e7ed;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.feedback-hint {
  font-size: 12px;
  color: #909399;
}

.feedback-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.input-panel {
  flex-shrink: 0;
  padding: 12px 20px 20px;
  border-top: 1px solid #eef0f4;
  background: #fafbfc;
}

.chat-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  border-top: 1px solid #eef0f4;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.toolbar-report-btn {
  font-weight: 600;
  font-size: 14px;
  padding: 10px 22px;
  height: auto;
  border-radius: 8px;
}

.toolbar-excel-btn {
  font-weight: 600;
  font-size: 14px;
  padding: 10px 18px;
  height: auto;
  border-radius: 8px;
}

.toolbar-meta {
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}

.toolbar-hint {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-row :deep(.el-textarea__inner) {
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.55;
  min-height: 56px;
  resize: none;
  box-shadow: none;
}

.ask-btn {
  flex-shrink: 0;
  height: 56px;
  padding: 0 28px;
  border-radius: 10px;
}

.school-alert {
  margin-top: 10px;
}

@media (max-width: 900px) {
  .main {
    flex-direction: column;
    padding: 12px;
  }

  .session-sidebar {
    width: 100%;
    max-height: 160px;
  }

  .chat-toolbar {
    flex-wrap: wrap;
    padding: 8px 14px;
  }

  .toolbar-hint {
    display: none;
  }

  .response-card {
    max-width: 100%;
  }

  .user-bubble {
    max-width: 88%;
  }
}
</style>
