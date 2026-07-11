<template>
  <div class="bg-picker">
    <p class="bg-label">{{ label }}</p>
    <div v-if="loadError" class="bg-error">{{ loadError }}</div>
    <div v-else-if="!items.length" class="bg-empty">暂无背景图，将使用渐变兜底</div>
    <div v-else class="bg-grid">
      <button
        v-for="item in items"
        :key="item.path"
        type="button"
        class="bg-card"
        :class="{ active: modelValue === item.path }"
        @click="$emit('update:modelValue', item.path)"
      >
        <img v-if="thumbMap[item.path]" :src="thumbMap[item.path]" :alt="item.name" loading="lazy" />
        <div v-else class="bg-thumb-placeholder">加载中…</div>
        <span class="bg-name">{{ item.name }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { createBriefReportBackgroundObjectUrl } from '../../api/briefReport'

const props = defineProps({
  label: { type: String, default: '背景' },
  items: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
  loadError: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

const thumbMap = ref({})
const objectUrls = ref([])

async function loadThumbnails(items) {
  revokeThumbnails()
  const map = {}
  for (const item of items || []) {
    if (!item?.path) continue
    try {
      const url = await createBriefReportBackgroundObjectUrl(item.path)
      map[item.path] = url
      objectUrls.value.push(url)
    } catch {
      /* 单张失败不影响其余 */
    }
  }
  thumbMap.value = map
}

function revokeThumbnails() {
  for (const url of objectUrls.value) {
    URL.revokeObjectURL(url)
  }
  objectUrls.value = []
  thumbMap.value = {}
}

watch(
  () => props.items,
  (items) => {
    loadThumbnails(items)
  },
  { immediate: true, deep: true },
)

onBeforeUnmount(revokeThumbnails)
</script>

<style scoped>
.bg-picker {
  margin-bottom: 16px;
}
.bg-label {
  margin: 0 0 8px;
  font-size: 13px;
  color: #475569;
}
.bg-empty,
.bg-error {
  font-size: 12px;
  padding: 8px 0;
}
.bg-empty {
  color: #94a3b8;
}
.bg-error {
  color: #ef4444;
}
.bg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px;
}
.bg-card {
  border: 2px solid #e2e8f0;
  border-radius: 8px;
  padding: 4px;
  background: #fff;
  cursor: pointer;
  text-align: center;
}
.bg-card.active {
  border-color: #22c55e;
  box-shadow: 0 0 0 1px #22c55e;
}
.bg-card img {
  width: 100%;
  height: 72px;
  object-fit: cover;
  border-radius: 4px;
  display: block;
}
.bg-thumb-placeholder {
  width: 100%;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #94a3b8;
  background: #f1f5f9;
  border-radius: 4px;
}
.bg-name {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
