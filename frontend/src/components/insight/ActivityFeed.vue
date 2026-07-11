<template>
  <div ref="rootEl" class="activity-feed">
    <div v-for="(act, i) in items" :key="i" :class="['feed-item', act.level]">
      {{ act.message }}
    </div>
    <div v-if="!items.length" class="placeholder">{{ placeholder }}</div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
})

const rootEl = ref(null)

watch(
  () => props.items.length,
  async () => {
    await nextTick()
    if (rootEl.value) rootEl.value.scrollTop = rootEl.value.scrollHeight
  },
)
</script>

<style scoped>
.placeholder {
  color: #94a3b8;
  text-align: center;
  padding: 40px 16px;
}
</style>
