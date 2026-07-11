<template>
  <div v-if="activeStep > 0 || statusText" class="ask-pipeline-header">
    <PipelineStrip :active-step="activeStep" />
    <StatusLine v-if="showStatus && statusText" :text="statusText" />
  </div>
</template>

<script setup>
import PipelineStrip from '../insight/PipelineStrip.vue'
import StatusLine from '../insight/StatusLine.vue'

defineProps({
  activeStep: { type: Number, default: 0 },
  statusText: { type: String, default: '' },
  showStatus: { type: Boolean, default: false },
})
</script>

<style scoped>
.ask-pipeline-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eef0f4;
}
</style>
