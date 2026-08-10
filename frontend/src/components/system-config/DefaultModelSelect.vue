<template>
  <el-popover :visible="visible" placement="bottom-end" :width="280" trigger="click" @update:visible="onVisible">
    <template #reference>
      <el-button>
        <span>{{ label }}</span>
        <el-icon class="el-icon--right"><Switch /></el-icon>
      </el-button>
    </template>
    <div class="default-picker">
      <el-input
        v-model="q"
        size="small"
        clearable
        placeholder="通过名称搜索"
        class="default-picker__search"
      />
      <div class="default-picker__list">
        <button
          v-for="m in filtered"
          :key="m.id"
          type="button"
          class="default-picker__item"
          :class="{ 'is-active': m.isDefault }"
          @click="pick(m)"
        >
          <span class="default-picker__dot" :style="{ background: colorOf(m.provider) }" />
          <span class="default-picker__name">{{ m.name }}</span>
          <el-icon v-if="m.isDefault" color="#0ca678"><Select /></el-icon>
        </button>
        <div v-if="!filtered.length" class="sys-muted" style="padding: 12px; text-align: center">
          暂无可用模型
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Select, Switch } from '@element-plus/icons-vue'
import { providerColor } from '../../constants/llmProviders.fallback'

const props = defineProps({
  role: { type: String, required: true },
  models: { type: Array, default: () => [] },
  providers: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

const visible = ref(false)
const q = ref('')

const roleModels = computed(() =>
  props.models.filter((m) => m.role === props.role && m.status === 1),
)

const current = computed(() => roleModels.value.find((m) => m.isDefault))

const label = computed(() => {
  const prefix = props.role === 'embedding' ? '默认 Embedding' : '系统默认模型'
  return current.value ? `${prefix}：${current.value.name}` : prefix
})

const filtered = computed(() => {
  const key = q.value.trim().toLowerCase()
  if (!key) return roleModels.value
  return roleModels.value.filter((m) => m.name.toLowerCase().includes(key))
})

function colorOf(code) {
  return providerColor(code, props.providers)
}

function onVisible(v) {
  visible.value = v
  if (!v) q.value = ''
}

function pick(m) {
  if (!m.isDefault) emit('select', m)
  visible.value = false
}
</script>

<style scoped>
.default-picker__search {
  margin-bottom: 8px;
}
.default-picker__list {
  max-height: 260px;
  overflow: auto;
}
.default-picker__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
  padding: 8px 6px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}
.default-picker__item:hover,
.default-picker__item.is-active {
  background: #e6f9f1;
}
.default-picker__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.default-picker__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
</style>
