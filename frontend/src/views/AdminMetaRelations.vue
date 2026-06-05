<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · 表关系</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-select v-model="filterTableId" clearable placeholder="按源表筛选" style="width: 220px" @change="loadList">
            <el-option v-for="t in tables" :key="t.id" :label="t.tableName" :value="t.id" />
          </el-select>
          <el-button type="primary" @click="openCreate">新增关系</el-button>
        </div>
        <el-table v-loading="loading" :data="relations" border style="margin-top: 16px">
          <el-table-column label="源表" min-width="160">
            <template #default="{ row }">{{ row.fromTableName }}.{{ row.fromColumn }}</template>
          </el-table-column>
          <el-table-column label="目标表" min-width="160">
            <template #default="{ row }">{{ row.toTableName }}.{{ row.toColumn }}</template>
          </el-table-column>
          <el-table-column prop="relationType" label="类型" width="110" />
          <el-table-column prop="cardinality" label="基数" width="80" />
          <el-table-column prop="joinHint" label="JOIN 说明" min-width="140" show-overflow-tooltip />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑关系' : '新增关系'" width="560px" destroy-on-close>
      <el-form :model="form" label-width="96px">
        <el-form-item label="源表" required>
          <el-select v-model="form.fromTableId" style="width: 100%" @change="form.fromColumn = ''">
            <el-option v-for="t in tables" :key="t.id" :label="t.tableName" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="源字段" required>
          <el-input v-model="form.fromColumn" placeholder="如 people_id" />
        </el-form-item>
        <el-form-item label="目标表" required>
          <el-select v-model="form.toTableId" style="width: 100%" @change="form.toColumn = ''">
            <el-option v-for="t in tables" :key="t.id" :label="t.tableName" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标字段" required>
          <el-input v-model="form.toColumn" placeholder="如 id" />
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="form.relationType" style="width: 100%">
            <el-option label="逻辑 JOIN" value="logical_join" />
            <el-option label="外键 FK" value="fk" />
            <el-option label="查找 lookup" value="lookup" />
          </el-select>
        </el-form-item>
        <el-form-item label="基数">
          <el-select v-model="form.cardinality" clearable style="width: 100%">
            <el-option label="n:1" value="n:1" />
            <el-option label="1:n" value="1:n" />
            <el-option label="n:n" value="n:n" />
          </el-select>
        </el-form-item>
        <el-form-item label="JOIN 说明">
          <el-input v-model="form.joinHint" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import { fetchMe } from '../api/auth'
import {
  createRelation,
  deleteRelation,
  listMetaTables,
  listRelations,
  updateRelation,
} from '../api/meta'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const relations = ref([])
const tables = ref([])
const filterTableId = ref(null)
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  fromTableId: null,
  fromColumn: '',
  toTableId: null,
  toColumn: '',
  relationType: 'logical_join',
  cardinality: '',
  joinHint: '',
})

onMounted(async () => {
  if (!(await guardMetaManager())) return
  await loadTables()
  await loadList()
})

async function guardMetaManager() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
      ElMessage.warning('需要管理员或运营权限')
      router.replace('/')
      return false
    }
    localStorage.setItem('userRole', res.user.role)
    return true
  } catch {
    router.push('/login')
    return false
  }
}

async function loadTables() {
  const res = await listMetaTables({ offset: 0, limit: 200 })
  tables.value = res.items
}

async function loadList() {
  loading.value = true
  try {
    const params = {}
    if (filterTableId.value) params.fromTableId = filterTableId.value
    relations.value = await listRelations(params)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  Object.assign(form, {
    fromTableId: filterTableId.value || tables.value[0]?.id || null,
    fromColumn: '',
    toTableId: null,
    toColumn: '',
    relationType: 'logical_join',
    cardinality: '',
    joinHint: '',
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  Object.assign(form, {
    fromTableId: row.fromTableId,
    fromColumn: row.fromColumn,
    toTableId: row.toTableId,
    toColumn: row.toColumn,
    relationType: row.relationType,
    cardinality: row.cardinality || '',
    joinHint: row.joinHint || '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.fromTableId || !form.toTableId || !form.fromColumn.trim() || !form.toColumn.trim()) {
    ElMessage.warning('请填写完整表与字段')
    return
  }
  const body = {
    fromTableId: form.fromTableId,
    fromColumn: form.fromColumn.trim(),
    toTableId: form.toTableId,
    toColumn: form.toColumn.trim(),
    relationType: form.relationType,
    cardinality: form.cardinality || null,
    joinHint: form.joinHint.trim() || null,
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateRelation(editId.value, body)
    } else {
      await createRelation(body)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm('确定删除该关系？', '确认', { type: 'warning' })
  await deleteRelation(row.id)
  ElMessage.success('已删除')
  await loadList()
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}
</script>

<style scoped>
.layout { min-height: 100vh; background: #f5f7fa; }
.header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; background: #fff; border-bottom: 1px solid #e4e7ed;
}
.title { font-weight: 600; font-size: 18px; }
.main { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
.toolbar { display: flex; gap: 12px; align-items: center; }
</style>
