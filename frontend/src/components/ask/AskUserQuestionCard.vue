<template>
  <div class="ask-user-card">
    <div v-if="title" class="ask-title">{{ title }}</div>
    <div v-if="reason" class="ask-reason">{{ reason }}</div>

    <div
      v-for="q in displayQuestions"
      :key="q.id"
      class="ask-question"
    >
      <div class="ask-prompt">{{ q.prompt }}</div>
      <div v-if="q.options?.length" class="ask-options">
        <button
          v-for="opt in q.options"
          :key="opt.id"
          type="button"
          class="ask-chip"
          :class="{
            selected: selections[q.id]?.optionId === opt.id,
            recommended: opt.recommended,
          }"
          :disabled="readonly || submitting"
          @click="selectOption(q.id, opt)"
        >
          {{ opt.label }}
          <span v-if="opt.recommended" class="rec-badge">建议</span>
        </button>
      </div>
      <el-input
        v-if="q.allowFreeText !== false && !readonly"
        v-model="freeTexts[q.id]"
        size="small"
        class="ask-freetext"
        placeholder="或自己补充说明…"
        :disabled="submitting"
        @keyup.enter="onSubmit"
      />
    </div>

    <div v-if="!readonly" class="ask-actions">
      <el-button
        v-if="hasRecommended"
        size="small"
        @click="applyRecommended"
      >
        按建议继续
      </el-button>
      <el-button
        type="primary"
        size="small"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        提交补充
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  clarification: { type: Object, default: null },
  readonly: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
})

const emit = defineEmits(['submit'])

const selections = reactive({})
const freeTexts = reactive({})

const displayQuestions = computed(() => {
  const c = props.clarification || {}
  if (Array.isArray(c.questions) && c.questions.length) {
    return c.questions.slice(0, 4).map((q) => ({
      id: q.id,
      prompt: q.prompt,
      allowFreeText: q.allowFreeText !== false,
      options: (q.options || []).slice(0, 4),
    }))
  }
  // 扁平兼容
  const opts = (c.options || []).map((label, i) => ({
    id: `opt_${i}`,
    label: String(label),
    recommended: i === 0,
  }))
  return [
    {
      id: 'general',
      prompt: c.question || '请补充查询条件',
      allowFreeText: true,
      options: opts.slice(0, 4),
    },
  ]
})

const title = computed(() => props.clarification?.title || '')
const reason = computed(() => props.clarification?.reason || '')

const hasRecommended = computed(() =>
  displayQuestions.value.some((q) => q.options?.some((o) => o.recommended)),
)

const canSubmit = computed(() => {
  return displayQuestions.value.some((q) => {
    if (selections[q.id]?.optionId) return true
    if ((freeTexts[q.id] || '').trim()) return true
    return false
  })
})

watch(
  () => props.clarification,
  () => {
    Object.keys(selections).forEach((k) => delete selections[k])
    Object.keys(freeTexts).forEach((k) => delete freeTexts[k])
  },
)

function selectOption(qid, opt) {
  selections[qid] = { optionId: opt.id, label: opt.label }
}

function applyRecommended() {
  for (const q of displayQuestions.value) {
    const rec = (q.options || []).find((o) => o.recommended)
    if (rec) selections[q.id] = { optionId: rec.id, label: rec.label }
  }
}

function onSubmit() {
  const answers = []
  const textParts = []
  for (const q of displayQuestions.value) {
    const free = (freeTexts[q.id] || '').trim()
    const sel = selections[q.id]
    if (free) {
      answers.push({ questionId: q.id, freeText: free })
      textParts.push(free)
    } else if (sel?.optionId) {
      answers.push({ questionId: q.id, optionId: sel.optionId })
      textParts.push(sel.label)
    }
  }
  if (!textParts.length) return
  emit('submit', {
    question: textParts.join('，'),
    clarificationAnswers: answers,
    clarificationThreadId: props.clarification?.threadId || null,
  })
}
</script>

<style scoped>
.ask-user-card {
  margin-top: 10px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}
.ask-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: #0f172a;
}
.ask-reason {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 10px;
}
.ask-question + .ask-question {
  margin-top: 12px;
}
.ask-prompt {
  font-size: 14px;
  margin-bottom: 8px;
  color: #1e293b;
}
.ask-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.ask-chip {
  border: 1px solid #cbd5e1;
  background: #fff;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
  color: #334155;
}
.ask-chip:hover:not(:disabled) {
  border-color: #64748b;
}
.ask-chip.selected {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}
.ask-chip.recommended {
  box-shadow: inset 0 0 0 1px #93c5fd;
}
.rec-badge {
  margin-left: 4px;
  font-size: 11px;
  color: #2563eb;
}
.ask-freetext {
  max-width: 360px;
}
.ask-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
