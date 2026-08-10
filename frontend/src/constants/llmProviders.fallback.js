/**
 * LLM 供应商离线兜底（仅 API 不可用时）。主数据源为 GET /llm-providers。
 * temporary — 与 backend/app/system/catalogs/llm_providers.yaml 保持同步。
 */
export const LLM_PROVIDERS_FALLBACK = [
  {
    code: 'deepseek',
    name: 'DeepSeek',
    logoKey: 'deepseek',
    color: '#4D6BFE',
    defaultApiBase: 'https://api.deepseek.com',
    suggestedModels: ['deepseek-chat', 'deepseek-reasoner'],
    supportsThinking: true,
    adapterKey: 'openai_compatible',
    extraDefaults: { thinking_enabled: true },
    roles: ['chat'],
  },
  {
    code: 'dashscope',
    name: '阿里云百炼',
    logoKey: 'dashscope',
    color: '#FF6A00',
    defaultApiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    suggestedModels: ['qwen-plus', 'qwen-turbo'],
    supportsThinking: false,
    adapterKey: 'openai_compatible',
    extraDefaults: {},
    roles: ['chat', 'embedding'],
  },
  {
    code: 'openai_compatible',
    name: '通用 OpenAI 兼容',
    logoKey: 'generic',
    color: '#0CA678',
    defaultApiBase: '',
    suggestedModels: [],
    supportsThinking: false,
    adapterKey: 'openai_compatible',
    extraDefaults: {},
    roles: ['chat', 'embedding'],
  },
  {
    code: 'ollama',
    name: 'Ollama',
    logoKey: 'ollama',
    color: '#111111',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    suggestedModels: ['qwen2.5', 'nomic-embed-text'],
    supportsThinking: false,
    adapterKey: 'openai_compatible',
    extraDefaults: {},
    roles: ['chat', 'embedding'],
  },
]

export function providerLabel(code, providers = LLM_PROVIDERS_FALLBACK) {
  const hit = providers.find((p) => p.code === code)
  return hit?.name || code || '未知'
}

export function providerColor(code, providers = LLM_PROVIDERS_FALLBACK) {
  const hit = providers.find((p) => p.code === code)
  return hit?.color || '#0CA678'
}

export function providerInitial(nameOrCode) {
  const s = String(nameOrCode || '?').trim()
  return s.slice(0, 1).toUpperCase()
}
