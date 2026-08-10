<template>
  <div>
    <el-input
      v-model="q"
      clearable
      placeholder="搜索供应商"
      style="margin-bottom: 12px"
    />
    <div class="sys-provider-wall">
      <button
        v-for="p in filtered"
        :key="p.code"
        type="button"
        class="sys-provider-tile"
        :class="{ 'is-active': modelValue === p.code }"
        @click="$emit('update:modelValue', p.code)"
      >
        <div class="sys-provider-tile__logo" :style="{ background: p.color || '#0ca678' }">
          {{ initial(p.name) }}
        </div>
        <div class="sys-provider-tile__name">{{ p.name }}</div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { providerInitial } from '../../constants/llmProviders.fallback'

const props = defineProps({
  modelValue: { type: String, default: '' },
  providers: { type: Array, default: () => [] },
  role: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

const q = ref('')

const filtered = computed(() => {
  let list = props.providers
  if (props.role) {
    list = list.filter((p) => !p.roles?.length || p.roles.includes(props.role))
  }
  const key = q.value.trim().toLowerCase()
  if (!key) return list
  return list.filter(
    (p) => p.name.toLowerCase().includes(key) || p.code.toLowerCase().includes(key),
  )
})

function initial(name) {
  return providerInitial(name)
}
</script>
