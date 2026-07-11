<template>
  <div v-if="text" class="status-line">{{ text }}</div>
</template>

<script setup>
defineProps({
  text: { type: String, default: '' },
})
</script>

<style scoped>
.status-line {
  flex: 1;
  min-width: 0;
  padding: 6px 10px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-size: 12px;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
