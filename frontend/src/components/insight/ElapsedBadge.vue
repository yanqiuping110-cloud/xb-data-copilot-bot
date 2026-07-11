<template>
  <span v-if="elapsedMs != null" class="elapsed-badge">已用时 {{ formatElapsed(elapsedMs) }}</span>
</template>

<script setup>
defineProps({
  elapsedMs: { type: Number, default: null },
})

function formatElapsed(ms) {
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}
</script>
