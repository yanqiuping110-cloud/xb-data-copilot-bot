<template>
  <div v-if="activeStep > 0" class="pipeline-strip">
    <div
      v-for="(label, i) in steps"
      :key="i"
      :class="['step', { done: i + 1 < activeStep, active: i + 1 === activeStep }]"
    >
      <span class="dot" />
      <span class="label">{{ label }}</span>
    </div>
  </div>
</template>

<script setup>
import { PIPELINE_STEPS } from '../../utils/pipelineMapper'

defineProps({
  activeStep: { type: Number, default: 0 },
})

const steps = PIPELINE_STEPS
</script>

<style scoped>
.pipeline-strip {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 0;
}
.step {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #94a3b8;
}
.step.done { color: #16a34a; }
.step.active { color: #6366f1; font-weight: 600; }
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
</style>
