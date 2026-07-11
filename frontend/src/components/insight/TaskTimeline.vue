<template>
  <ul class="task-timeline">
    <li
      v-for="item in items"
      :key="item.index"
      :class="['task-item', statusClass(item.index)]"
    >
      <span class="idx">{{ item.index }}</span>
      <span class="title">{{ item.title }}</span>
      <el-tag size="small" type="info">{{ item.intent }}</el-tag>
    </li>
  </ul>
</template>

<script setup>
const props = defineProps({
  items: { type: Array, default: () => [] },
  sectionStatus: { type: Object, default: () => ({}) },
})

function statusClass(index) {
  const st = props.sectionStatus[index]
  if (st === 'running') return 'running'
  if (st === 'done') return 'done'
  if (st === 'fail') return 'fail'
  return ''
}
</script>

<style scoped>
.task-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}
.task-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 12px;
}
.idx {
  width: 20px;
  font-weight: 600;
  color: #94a3b8;
}
.title {
  flex: 1;
}
</style>
