<template>
  <div class="layout">
    <header class="header">
      <span class="title">小奔问数</span>
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
        <span v-if="user">{{ user.displayName || user.username }}（{{ user.role }}）</span>
        <el-button v-if="user?.role === 'ADMIN'" link type="primary" @click="router.push('/admin/users')">
          用户管理
        </el-button>
        <el-button
          v-if="user?.role === 'ADMIN' || user?.role === 'OPERATOR'"
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
      <el-card class="chat-card">
        <div class="messages">
          <div v-for="(msg, idx) in messages" :key="idx" :class="['msg', msg.role]">
            <div class="bubble">{{ msg.text }}</div>
            <ul v-if="msg.progress?.length" class="progress-list">
              <li
                v-for="(step, si) in msg.progress"
                :key="si"
                :class="{ done: step.done, active: step.active }"
              >
                {{ step.label }}
              </li>
            </ul>
            <div v-if="msg.meta" class="meta">{{ msg.meta }}</div>
          </div>
        </div>

        <el-form class="input-row" @submit.prevent="onAsk">
          <el-input
            v-model="question"
            placeholder="例如：本校本月跳绳参与人数 / 最近7天每日趋势"
            :disabled="loading || needSelectSchool"
          />
          <el-button type="primary" native-type="submit" :loading="loading" :disabled="needSelectSchool">
            提问
          </el-button>
        </el-form>
        <el-alert
          v-if="needSelectSchool"
          title="请先选择学校后再提问"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 12px"
        />
      </el-card>

      <el-card v-if="lastResult" style="margin-top: 16px">
        <template #header>
          <div class="result-header">
            <span>最近一次查询</span>
            <div v-if="lastResult.traceId" class="feedback-row">
              <el-button
                size="small"
                :type="lastFeedback === 'up' ? 'success' : 'default'"
                :loading="feedbackLoading"
                @click="onFeedback('up')"
              >
                👍 有用
              </el-button>
              <el-button
                size="small"
                :type="lastFeedback === 'down' ? 'danger' : 'default'"
                :loading="feedbackLoading"
                @click="onFeedback('down')"
              >
                👎 不准
              </el-button>
              <el-button size="small" :loading="feedbackLoading" @click="onMarkBadcase">
                标记 badcase
              </el-button>
            </div>
          </div>
        </template>
        <p v-if="lastResult.answer"><strong>回答：</strong>{{ lastResult.answer }}</p>
        <p v-if="lastResult.sql"><strong>SQL：</strong><code>{{ lastResult.sql }}</code></p>
        <el-table
          v-if="lastResult.columns?.length"
          :data="tableRows"
          border
          size="small"
          style="margin-top: 12px"
        >
          <el-table-column
            v-for="col in lastResult.columns"
            :key="col"
            :prop="col"
            :label="col"
          />
        </el-table>
      </el-card>
    </main>
  </div>
</template>

<script setup>
/** 问数对话页：学校切换 + SSE 流式 POST /api/v1/ask */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchMe, switchSchool } from '../api/auth'
import { postAskStream } from '../api/ask'
import { postFeedback } from '../api/feedback'

const router = useRouter()
const user = ref(null)
const boundSchools = ref([])
const selectedSchId = ref(null)
const question = ref('')
const loading = ref(false)
const messages = ref([])
const lastResult = ref(null)
const lastFeedback = ref(null)
const feedbackLoading = ref(false)
const sessionId = ref(`sess-${Date.now()}`)

const needSelectSchool = computed(
  () => user.value?.role === 'SCHOOL' && boundSchools.value.length > 1 && !selectedSchId.value,
)

const tableRows = computed(() => {
  if (!lastResult.value?.columns?.length || !lastResult.value?.rows?.length) return []
  return lastResult.value.rows.map((row) =>
    Object.fromEntries(lastResult.value.columns.map((col, i) => [col, row[i]])),
  )
})

onMounted(async () => {
  try {
    const res = await fetchMe()
    user.value = res.user
    localStorage.setItem('userRole', res.user.role)
    boundSchools.value = res.user.boundSchools || []
    selectedSchId.value = res.user.activeSchId ?? boundSchools.value[0]?.schId ?? null
    messages.value.push({
      role: 'assistant',
      text: '你好，我是问数助手。可尝试：「本校本月跳绳参与人数」「最近7天每日趋势」「昨日全平台活动参与人次」。',
    })
  } catch {
    router.push('/login')
  }
})

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

async function onAsk() {
  const q = question.value.trim()
  if (!q) return
  messages.value.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true

  const assistantIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    text: '正在分析您的问题…',
    progress: [],
  })

  try {
    await postAskStream({
      question: q,
      sessionId: sessionId.value,
      onProgress: ({ label }) => {
        const msg = messages.value[assistantIdx]
        if (!msg?.progress) return
        msg.progress.forEach((step) => {
          step.active = false
          step.done = true
        })
        const existing = msg.progress.find((s) => s.label === label)
        if (existing) {
          existing.active = true
          existing.done = false
        } else {
          msg.progress.push({ label, active: true, done: false })
        }
      },
      onDone: (res) => {
        lastResult.value = res
        lastFeedback.value = null
        const msg = messages.value[assistantIdx]
        if (res.status === 'success') {
          msg.text = res.answer || '查询完成'
          msg.meta = res.traceId ? `trace: ${res.traceId} · ${res.latencyMs}ms` : undefined
        } else {
          msg.text = res.errorMessage || '未能回答该问题'
          msg.meta = res.errorCode
        }
        msg.progress?.forEach((step) => {
          step.active = false
          step.done = true
        })
      },
      onError: (err) => {
        const msg = messages.value[assistantIdx]
        msg.text = err.message || '问数失败'
        msg.meta = err.code
      },
    })
  } catch {
    const msg = messages.value[assistantIdx]
    if (msg.text === '正在分析您的问题…') {
      msg.text = '请求失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}

async function onFeedback(kind) {
  if (!lastResult.value?.traceId) return
  feedbackLoading.value = true
  try {
    await postFeedback({ traceId: lastResult.value.traceId, feedback: kind })
    lastFeedback.value = kind
    ElMessage.success(kind === 'up' ? '感谢反馈' : '已记录，我们会改进')
  } finally {
    feedbackLoading.value = false
  }
}

async function onMarkBadcase() {
  if (!lastResult.value?.traceId) return
  feedbackLoading.value = true
  try {
    await postFeedback({
      traceId: lastResult.value.traceId,
      feedback: 'down',
      isBadcase: true,
    })
    lastFeedback.value = 'down'
    ElMessage.success('已标记为 badcase，运营可在元数据管理中处理')
  } finally {
    feedbackLoading.value = false
  }
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: #f5f7fa;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.title {
  font-weight: 600;
  font-size: 18px;
}
.user-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.main {
  max-width: 960px;
  margin: 24px auto;
  padding: 0 16px;
}
.chat-card {
  min-height: 420px;
  display: flex;
  flex-direction: column;
}
.messages {
  flex: 1;
  min-height: 280px;
  max-height: 400px;
  overflow-y: auto;
  margin-bottom: 16px;
}
.msg {
  margin-bottom: 12px;
}
.msg.user {
  text-align: right;
}
.msg.user .bubble {
  background: #409eff;
  color: #fff;
}
.msg.assistant .bubble {
  background: #ecf5ff;
  color: #303133;
}
.bubble {
  display: inline-block;
  padding: 10px 14px;
  border-radius: 8px;
  max-width: 85%;
  text-align: left;
  white-space: pre-wrap;
}
.meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.progress-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  font-size: 12px;
  color: #909399;
  text-align: left;
}
.progress-list li {
  padding: 2px 0;
}
.progress-list li.done {
  color: #67c23a;
}
.progress-list li.active {
  color: #409eff;
  font-weight: 500;
}
.input-row {
  display: flex;
  gap: 8px;
}
code {
  word-break: break-all;
  font-size: 12px;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.feedback-row {
  display: flex;
  gap: 8px;
}
</style>
