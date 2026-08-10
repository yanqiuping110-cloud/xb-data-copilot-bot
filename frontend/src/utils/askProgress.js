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

export function timelineTotalMs(steps, nowMs = Date.now()) {
  if (!steps?.length) return 0
  return steps.reduce((sum, step) => {
    if ((step.active || step.status === 'running') && step.startedAt) {
      return sum + Math.max(0, nowMs - step.startedAt)
    }
    return sum + (Number(step.durationMs) || 0)
  }, 0)
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
  const now = Date.now()

  for (const step of msg.timeline) {
    if (step.active && step.node !== evt.node) {
      step.active = false
      step.done = true
      step.status = 'done'
      if (step.durationMs == null && step.startedAt) {
        step.durationMs = Math.max(0, now - step.startedAt)
      }
    }
  }

  let step = msg.timeline.find((s) => s.node === evt.node)
  if (!step) {
    step = { node: evt.node }
    msg.timeline.push(step)
  }

  const isRunning = evt.status === 'running'
  Object.assign(step, {
    label: evt.label,
    phase: evt.phase || nodeToPhase(evt.node),
    status: isRunning ? 'running' : evt.status === 'fail' ? 'fail' : 'done',
    summary: evt.summary ?? step.summary,
    subtitle: formatStepSubtitle(evt) || step.subtitle,
    icon: evt.icon,
    active: isRunning,
    done: !isRunning,
  })

  if (isRunning) {
    if (!step.startedAt) step.startedAt = now
    // 进行中不覆盖服务端最终耗时字段
    if (evt.durationMs == null) step.durationMs = undefined
    beginStepThinkingBlock(step)
    _flushPendingThinking(msg, step, evt.node)
  } else {
    if (evt.durationMs != null) {
      step.durationMs = evt.durationMs
    } else if (step.durationMs == null && step.startedAt) {
      step.durationMs = Math.max(0, now - step.startedAt)
    }
    step.active = false
    step.done = true
    step._thinkingClosed = true
  }

  msg.pipelineStep = nodeToPipelineStep(evt.node)
  msg.statusText = isRunning ? `正在${evt.label}…` : `已完成 ${evt.label}`
}

function _flushPendingThinking(msg, step, node) {
  const pending = msg._pendingThinking
  if (!pending) return
  const pendingNode = msg._pendingThinkingNode
  if (pendingNode && pendingNode !== node) return
  appendStepThinking(step, pending)
  msg._pendingThinking = ''
  msg._pendingThinkingNode = null
}

/** 开始新一轮推理块（同一步多次调模型时分隔）。 */
export function beginStepThinkingBlock(step) {
  if (!step) return
  if (!Array.isArray(step.thinkingBlocks)) step.thinkingBlocks = []
  const last = step.thinkingBlocks[step.thinkingBlocks.length - 1]
  if (last && last.length > 0) {
    step._thinkingClosed = true
  }
}

export function appendStepThinking(step, delta) {
  if (!step || !delta) return
  if (!Array.isArray(step.thinkingBlocks)) step.thinkingBlocks = []
  if (!step.thinkingBlocks.length || step._thinkingClosed) {
    step.thinkingBlocks.push(delta)
    step._thinkingClosed = false
  } else {
    const idx = step.thinkingBlocks.length - 1
    step.thinkingBlocks[idx] = (step.thinkingBlocks[idx] || '') + delta
  }
  step.thinking = step.thinkingBlocks.join('\n\n')
}

/** 将思考增量挂到对应执行步骤（ADMIN 流式）。 */
export function applyThinkingDelta(msg, evt) {
  if (!msg) return
  const delta = typeof evt === 'string' ? evt : evt?.delta
  if (!delta) return
  const node = typeof evt === 'object' ? evt?.node : null

  msg.thinking = (msg.thinking || '') + delta

  if (!msg.timeline) msg.timeline = []
  let step = node ? msg.timeline.find((s) => s.node === node) : null
  if (!step) {
    step = msg.timeline.find((s) => s.active || s.status === 'running')
  }
  if (!step) {
    msg._pendingThinking = (msg._pendingThinking || '') + delta
    if (node) msg._pendingThinkingNode = node
    return
  }
  appendStepThinking(step, delta)
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
  msg._pendingThinking = ''
  msg._pendingThinkingNode = null
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
