<template>
  <div class="template-gallery">
    <div
      v-for="tpl in templates"
      :key="tpl.code"
      :class="['tpl-card', { active: modelValue === tpl.code }]"
      @click="$emit('update:modelValue', tpl.code)"
    >
      <div class="tpl-icon">{{ tpl.icon }}</div>
      <div class="tpl-name">{{ tpl.name }}</div>
      <div class="tpl-desc">{{ tpl.desc }}</div>
      <el-tag size="small" type="info">{{ tpl.sections }} 节</el-tag>
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'monthly_ops' },
})

defineEmits(['update:modelValue'])

const templates = [
  { code: 'monthly_ops', name: '月度运营', desc: '标准 4 节 KPI 报告', sections: 4, icon: '📊' },
  { code: 'monthly_ops_long', name: '月度长报告', desc: '8 节深度分析', sections: 8, icon: '📈' },
  { code: 'period_compare', name: '周期对比', desc: '本期 vs 上期', sections: 3, icon: '⚖️' },
  { code: 'custom', name: '自定义', desc: 'LLM 拆解意图', sections: '≤12', icon: '✨' },
]
</script>

<style scoped>
.template-gallery {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.tpl-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
}
.tpl-card:hover,
.tpl-card.active {
  border-color: #6366f1;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}
.tpl-icon { font-size: 20px; margin-bottom: 4px; }
.tpl-name { font-weight: 600; font-size: 13px; }
.tpl-desc { font-size: 11px; color: #64748b; margin: 4px 0 6px; min-height: 28px; }
</style>
