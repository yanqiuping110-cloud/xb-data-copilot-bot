<template>
  <div class="sys-wizard__side-list">
    <div
      v-for="t in filtered"
      :key="t.code"
      class="sys-type-item"
      :class="{
        'is-active': modelValue === t.code,
        'is-disabled': !t.selectable,
      }"
      @click="onPick(t)"
    >
      <span class="sys-type-item__logo" :style="{ background: t.color || '#0ca678' }">
        {{ initial(t.name) }}
      </span>
      <span>{{ t.name }}</span>
      <span v-if="!t.selectable" class="sys-type-item__soon">
        {{ t.status === 'coming_soon' ? '即将推出/需扩展' : '不可用' }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { providerInitial } from '../../constants/llmProviders.fallback'

const props = defineProps({
  modelValue: { type: String, default: '' },
  types: { type: Array, default: () => [] },
  query: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const filtered = computed(() => {
  const key = props.query.trim().toLowerCase()
  if (!key) return props.types
  return props.types.filter(
    (t) => t.name.toLowerCase().includes(key) || t.code.toLowerCase().includes(key),
  )
})

function initial(name) {
  return providerInitial(name)
}

function onPick(t) {
  if (!t.selectable) {
    ElMessage.info(`「${t.name}」即将支持，当前请选择已开放类型`)
    return
  }
  emit('update:modelValue', t.code)
}
</script>
