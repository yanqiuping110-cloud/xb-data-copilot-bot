<template>
  <el-menu mode="horizontal" :default-active="active" router class="meta-nav">
    <el-menu-item index="/admin/meta/tables">表管理</el-menu-item>
    <el-menu-item index="/admin/meta/relations">表关系</el-menu-item>
    <el-menu-item index="/admin/meta/field-values">字段取值</el-menu-item>
    <el-menu-item index="/admin/meta/metrics">指标</el-menu-item>
    <el-menu-item index="/admin/meta/sql-examples">L1 样例</el-menu-item>
    <el-menu-item index="/admin/meta/badcases">Badcase</el-menu-item>
    <el-menu-item v-if="showGitRepos" index="/admin/code/repos">Git 仓库</el-menu-item>
  </el-menu>
</template>

<script setup>
/** 元数据管理子导航（Git 仓库 tab 仅超管可见） */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { fetchMe } from '../api/auth'

const route = useRoute()
const userRole = ref(localStorage.getItem('userRole') || '')
const showGitRepos = computed(() => userRole.value === 'ADMIN')

const active = computed(() => {
  const p = route.path
  if (p.startsWith('/admin/meta/tables/') && p.endsWith('/columns')) {
    return '/admin/meta/tables'
  }
  if (p === '/admin/meta/tables/new') return '/admin/meta/tables'
  return p
})

onMounted(async () => {
  try {
    const res = await fetchMe()
    userRole.value = res.user.role
    localStorage.setItem('userRole', res.user.role)
  } catch {
    /* 路由守卫会处理未登录 */
  }
})
</script>

<style scoped>
.meta-nav {
  margin-bottom: 16px;
  border-bottom: none;
}
</style>
