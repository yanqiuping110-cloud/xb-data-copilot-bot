/** LangGraph 节点 → 6 步流水线（Insight Engine UI） */
export const PIPELINE_STEPS = ['理解', '召回', '规划', 'SQL', '执行', '回答']

const NODE_STEP = {
  normalize_question: 1,
  load_session_memory: 1,
  resolve_references: 1,
  process_memory_context: 1,
  do_recall_tables: 2,
  do_recall_columns: 2,
  do_recall_metrics: 2,
  do_recall_sql_examples: 2,
  select_l1_examples: 3,
  plan_question: 3,
  build_llm_context: 3,
  agent_loop: 3,
  generate_sql: 4,
  validate_sql: 4,
  execute_sql: 5,
  verify_answer: 5,
  format_answer: 6,
  build_chart: 6,
}

export function nodeToPipelineStep(node) {
  return NODE_STEP[node] || 3
}

export function pipelineLabel(step) {
  return PIPELINE_STEPS[Math.max(0, Math.min(step - 1, PIPELINE_STEPS.length - 1))]
}
