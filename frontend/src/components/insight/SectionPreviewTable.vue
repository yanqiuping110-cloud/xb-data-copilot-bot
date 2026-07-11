<template>
  <div class="preview-table-wrap">
    <p class="preview-label">数据预览</p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in rows" :key="ri">
            <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
})
</script>

<style scoped>
.preview-table-wrap {
  margin: 8px 0 8px 32px;
}
.preview-label {
  margin: 0 0 6px;
  font-size: 11px;
  color: #64748b;
}
.table-scroll {
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  border: 1px solid #e2e8f0;
  padding: 6px 8px;
  text-align: left;
  white-space: nowrap;
}
th {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
</style>
