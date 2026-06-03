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
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <el-card class="chat-card">
        <div class="messages">
          <div v-for="(msg, idx) in messages" :key="idx" :class="['msg', msg.role]">
            <div class="bubble">{{ msg.text }}</div>
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
        <template #header>最近一次查询</template>
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
/** 问数对话页：学校切换 + POST /api/v1/ask */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchMe, switchSchool } from '../api/auth'
import { postAsk } from '../api/ask'

const router = useRouter()
const user = ref(null)
const boundSchools = ref([])
const selectedSchId = ref(null)
const question = ref('')
const loading = ref(false)
const messages = ref([])
const lastResult = ref(null)
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
  try {
    const res = await postAsk({ question: q, sessionId: sessionId.value })
    lastResult.value = res
    if (res.status === 'success') {
      messages.value.push({
        role: 'assistant',
        text: res.answer || '查询完成',
        meta: res.traceId ? `trace: ${res.traceId} · ${res.latencyMs}ms` : undefined,
      })
    } else {
      messages.value.push({
        role: 'assistant',
        text: res.errorMessage || '未能回答该问题',
        meta: res.errorCode,
      })
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
.input-row {
  display: flex;
  gap: 8px;
}
code {
  word-break: break-all;
  font-size: 12px;
}
</style>
