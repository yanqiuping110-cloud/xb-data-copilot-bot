<template>
  <div class="embed-layout">
    <header class="embed-header">
      <span class="title">智能问数</span>
    </header>
    <main class="embed-main">
      <div ref="chatRef" class="chat-area">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['msg', msg.role]">
          <div class="bubble">{{ msg.text }}</div>
          <AskUserQuestionCard
            v-if="msg.clarification"
            :clarification="msg.clarification"
            :readonly="msg.clarificationReadonly"
            :submitting="loading"
            @submit="onClarificationSubmit"
          />
          <ResultPanel
            v-if="msg.result?.columns?.length && msg.result?.rows?.length"
            :columns="msg.result.columns"
            :rows="msg.result.rows"
            :chart-spec="msg.chartSpec"
          />
        </div>
      </div>
      <div class="input-bar">
        <el-input
          v-model="question"
          placeholder="输入业务问题…"
          :disabled="loading"
          @keyup.enter="onAsk"
        />
        <el-button type="primary" :loading="loading" @click="onAsk">提问</el-button>
      </div>
    </main>
  </div>
</template>

<script setup>
/** iframe 嵌入问数页：/embed/ask?token=... */
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import ResultPanel from '../components/ResultPanel.vue'
import AskUserQuestionCard from '../components/ask/AskUserQuestionCard.vue'
import { postAskStream } from '../api/ask'

const route = useRoute()
const question = ref('')
const loading = ref(false)
const messages = ref([])
const chatRef = ref(null)

onMounted(() => {
  const token = route.query.token
  if (token) {
    localStorage.setItem('accessToken', String(token))
  }
  if (!localStorage.getItem('accessToken')) {
    ElMessage.error('缺少 embed token')
  }
  window.addEventListener('message', onParentMessage)
})

function onParentMessage(event) {
  const allowed = (import.meta.env.VITE_EMBED_ORIGINS || '').split(',').map((s) => s.trim()).filter(Boolean)
  if (allowed.length && !allowed.includes(event.origin)) return
  const data = event.data || {}
  if (data.type === 'copilot:ask' && data.question) {
    question.value = data.question
    onAsk()
  }
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || loading.value) return
  await runAsk(q)
}

async function onClarificationSubmit(payload) {
  if (loading.value) return
  await runAsk(payload.question, {
    clarificationAnswers: payload.clarificationAnswers,
    clarificationThreadId: payload.clarificationThreadId,
  })
}

async function runAsk(q, extras = {}) {
  messages.value.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true
  const assistantIdx = messages.value.length
  messages.value.push({ role: 'assistant', text: '正在分析…' })
  const traceId = crypto.randomUUID()
  try {
    await postAskStream({
      question: q,
      traceId,
      clarificationAnswers: extras.clarificationAnswers,
      clarificationThreadId: extras.clarificationThreadId,
      onDone: (res) => {
        const msg = messages.value[assistantIdx]
        const ok =
          res.status === 'success' ||
          res.status === 'chitchat' ||
          res.status === 'out_of_scope' ||
          res.status === 'need_clarification'
        msg.text = ok ? (res.answer || '查询完成') : (res.errorMessage || '未能回答')
        msg.result = { columns: res.columns, rows: res.rows }
        msg.chartSpec = res.chartSpec
        msg.clarification = res.clarification || null
        msg.clarificationReadonly = false
        msg.status = res.status
      },
      onError: (err) => {
        messages.value[assistantIdx].text = err.message || '问数失败'
      },
    })
  } finally {
    loading.value = false
    await nextTick()
    chatRef.value?.scrollTo({ top: chatRef.value.scrollHeight, behavior: 'smooth' })
  }
}
</script>

<style scoped>
.embed-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8fafc;
}
.embed-header {
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
}
.title { font-weight: 600; }
.embed-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  min-height: 0;
}
.chat-area {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 12px;
}
.msg { margin-bottom: 12px; }
.msg.user .bubble {
  background: #6366f1;
  color: #fff;
  display: inline-block;
  padding: 8px 12px;
  border-radius: 12px 12px 4px 12px;
}
.msg.assistant .bubble {
  background: #fff;
  border: 1px solid #e2e8f0;
  padding: 10px 12px;
  border-radius: 12px;
}
.input-bar {
  display: flex;
  gap: 8px;
}
</style>
