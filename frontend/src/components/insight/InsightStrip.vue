<template>
  <TransitionGroup name="insight-pop" tag="div" class="insight-strip">
    <div v-for="(item, i) in items" :key="i" :class="['pill', item.type || 'info']">
      {{ item.text }}
    </div>
  </TransitionGroup>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
})
</script>

<style scoped>
.insight-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 2px 0;
}
.pill {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  max-width: 100%;
}
.pill.up { background: #ecfdf5; color: #047857; }
.pill.warn { background: #fffbeb; color: #b45309; }
.insight-pop-enter-active { transition: all 0.3s ease; }
.insight-pop-enter-from { opacity: 0; transform: translateY(8px); }
</style>
