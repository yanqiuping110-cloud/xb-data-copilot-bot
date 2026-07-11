<template>
  <div class="stream-md">
    <span>{{ text }}</span><span v-if="active" class="stream-cursor" />
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, default: '' },
  active: { type: Boolean, default: false },
})
</script>

<style scoped>
.stream-md {
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
  white-space: pre-wrap;
}
.stream-cursor::after {
  content: '▌';
  animation: blink 1s step-end infinite;
  color: #6366f1;
}
@keyframes blink { 50% { opacity: 0; } }
</style>
