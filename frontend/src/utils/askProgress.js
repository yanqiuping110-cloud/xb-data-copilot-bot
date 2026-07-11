/** LangGraph 节点 → 6 步流水线（Ask / Insight 共用） */
export const PIPELINE_STEPS = ['理解', '召回', '规划', 'SQL', '执行', '回答']

export const PIPELINE_PHASES = [
  { key: 'understand', label: '理解', step: 1 },
  { key: 'recall', label: '召回', step: 2 },
  { key: 'plan', label: '规划', step: 3 },
  { key: 'sql', label: 'SQL', step: 4 },
  { key: 'execute', label: '执行', step: 5 },
  { key: 'answer', label: '回答', step: 6 },
]

const NODE_STEP = {
  normalize_question: 1,
  load_session_memory: 1,
  load_user_preference: 1,
  resolve_references: 1,
  process_memory_context: 1,
  extract_keywords: 1,
  do_recall_tables: 2,
  do_recall_columns: 2,
  do_recall_metrics: 2,
  do_recall_field_values: 2,
  merge_retrieved_info: 2,
  filter_tables: 2,
  filter_columns: 2,
  filter_metrics: 2,
  do_recall_sql_examples: 2,
  select_l1_examples: 3,
  plan_question: 3,
  build_llm_context: 3,
  agent_loop: 3,
  build_agent_context: 3,
  generate_sql: 4,
  validate_sql: 4,
  correct_sql: 4,
  apply_policy: 4,
  generate_sql_step: 4,
  execute_plan_sql_step: 4,
  execute_sql: 5,
  verify_answer: 5,
  assemble_result: 5,
  format_answer: 6,
  build_chart: 6,
}

const NODE_PHASE = {
  normalize_question: 'understand',
  load_session_memory: 'understand',
  load_user_preference: 'understand',
  resolve_references: 'understand',
  process_memory_context: 'understand',
  extract_keywords: 'understand',
  do_recall_tables: 'recall',
  do_recall_columns: 'recall',
  do_recall_metrics: 'recall',
  do_recall_field_values: 'recall',
  merge_retrieved_info: 'recall',
  filter_tables: 'recall',
  filter_columns: 'recall',
  filter_metrics: 'recall',
  do_recall_sql_examples: 'recall',
  select_l1_examples: 'plan',
  plan_question: 'plan',
  build_llm_context: 'plan',
  agent_loop: 'plan',
  build_agent_context: 'plan',
  generate_sql: 'sql',
  validate_sql: 'sql',
  correct_sql: 'sql',
  apply_policy: 'sql',
  generate_sql_step: 'sql',
  execute_plan_sql_step: 'sql',
  execute_sql: 'execute',
  verify_answer: 'execute',
  assemble_result: 'execute',
  format_answer: 'answer',
  build_chart: 'answer',
}

export function nodeToPipelineStep(node) {
  return NODE_STEP[node] || 3
}

export function nodeToPhase(node) {
  return NODE_PHASE[node] || 'plan'
}

export function pipelineLabel(step) {
  return PIPELINE_STEPS[Math.max(0, Math.min(step - 1, PIPELINE_STEPS.length - 1))]
}

export function formatDurationMs(ms) {
  if (ms == null || Number.isNaN(ms) || ms < 0) return ''
  const n = Math.round(ms)
  if (n < 1000) return `${n} ms`
  if (n < 60_000) {
    const sec = n / 1000
    return sec >= 10 ? `${sec.toFixed(1)} s` : `${sec.toFixed(2)} s`
  }
  const min = Math.floor(n / 60_000)
  const sec = Math.round((n % 60_000) / 1000)
  return `${min} min ${sec} s`
}

export function timelineTotalMs(steps) {
  if (!steps?.length) return 0
  return steps.reduce((sum, step) => sum + (Number(step.durationMs) || 0), 0)
}

export function formatStepSubtitle(evt) {
  if (evt?.summary) return evt.summary
  const d = evt?.detail || {}
  if (d.keywords?.length) return `关键词：${d.keywords.join('、')}`
  if (d.count != null) return `命中 ${d.count} 项`
  if (d.rowCount != null) return `${d.rowCount} 行`
  if (d.complexity) {
    const steps = d.stepCount != null ? ` · ${d.stepCount} 步` : ''
    return `复杂度 ${d.complexity}${steps}`
  }
  if (d.hasSql) return 'SQL 已生成'
  return ''
}

export function applyProgressEvent(msg, evt) {
  if (!evt?.node) return
  if (!msg.timeline) msg.timeline = []

  for (const step of msg.timeline) {
    if (step.active && step.node !== evt.node) {
      step.active = false
      step.done = true
      step.status = 'done'
    }
  }

  let step = msg.timeline.find((s) => s.node === evt.node)
  if (!step) {
    step = { node: evt.node }
    msg.timeline.push(step)
  }

  Object.assign(step, {
    label: evt.label,
    phase: evt.phase || nodeToPhase(evt.node),
    status: evt.status === 'running' ? 'running' : 'done',
    summary: evt.summary,
    subtitle: formatStepSubtitle(evt),
    durationMs: evt.durationMs,
    icon: evt.icon,
    active: evt.status === 'running',
    done: evt.status !== 'running',
  })

  if (evt.status !== 'running') {
    step.active = false
    step.done = true
    step.status = 'done'
  }

  msg.pipelineStep = nodeToPipelineStep(evt.node)
  msg.statusText = evt.status === 'running' ? `正在${evt.label}…` : `已完成 ${evt.label}`
}

export function finalizeTimeline(msg) {
  if (!msg?.timeline) return
  for (const step of msg.timeline) {
    step.active = false
    step.done = true
    step.status = 'done'
  }
  msg.statusText = ''
  msg.pipelineStep = 6
  msg.progressOpen = false
}

export function createAssistantStreamMessage(text = '正在分析您的问题…') {
  return {
    role: 'assistant',
    text,
    thinking: '',
    pipelineStep: 0,
    statusText: '',
    timeline: [],
    progressOpen: true,
    intermediateSteps: [],
  }
}
