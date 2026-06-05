<template>
  <el-menu mode="horizontal" :default-active="active" router class="meta-nav">
    <el-menu-item index="/admin/meta/tables">表管理</el-menu-item>
    <el-menu-item index="/admin/meta/relations">表关系</el-menu-item>
    <el-menu-item index="/admin/meta/field-values">字段取值</el-menu-item>
    <el-menu-item index="/admin/meta/metrics">指标</el-menu-item>
    <el-menu-item index="/admin/meta/sql-examples">L1 样例</el-menu-item>
    <el-menu-item index="/admin/meta/badcases">Badcase</el-menu-item>
  </el-menu>
</template>

<script setup>
/** 元数据管理子导航 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = computed(() => {
  const p = route.path
  if (p.startsWith('/admin/meta/tables/') && p.endsWith('/columns')) {
    return '/admin/meta/tables'
  }
  if (p === '/admin/meta/tables/new') return '/admin/meta/tables'
  return p
})
</script>

<style scoped>
.meta-nav {
  margin-bottom: 16px;
  border-bottom: none;
}
</style>
