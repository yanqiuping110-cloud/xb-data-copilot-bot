<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · 字段取值</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-select v-model="filterTableId" clearable placeholder="筛选表" style="width: 200px" @change="onTableChange">
            <el-option v-for="t in tables" :key="t.id" :label="t.tableName" :value="t.id" />
          </el-select>
          <el-select
            v-model="filterColumnId"
            clearable
            placeholder="筛选字段"
            style="width: 200px"
            @change="loadList"
          >
            <el-option
              v-for="c in columnOptions"
              :key="c.id"
              :label="c.columnName"
              :value="c.id"
            />
          </el-select>
          <el-button type="primary" @click="openCreate">新增取值</el-button>
        </div>
        <el-table v-loading="loading" :data="values" border style="margin-top: 16px">
          <el-table-column prop="tableName" label="表" min-width="160" />
          <el-table-column prop="columnName" label="字段" width="120" />
          <el-table-column prop="valueText" label="库中值" width="100" />
          <el-table-column prop="displayLabel" label="展示名" width="120" />
          <el-table-column label="别名" min-width="140">
            <template #default="{ row }">{{ (row.aliases || []).join('，') || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑取值' : '新增取值'" width="480px" destroy-on-close>
      <el-form :model="form" label-width="88px">
        <el-form-item label="表" required>
          <el-select v-model="form.tableId" style="width: 100%" @change="onFormTableChange">
            <el-option v-for="t in tables" :key="t.id" :label="t.tableName" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="字段" required>
          <el-select v-model="form.columnId" style="width: 100%">
            <el-option v-for="c in formColumns" :key="c.id" :label="c.columnName" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="库中值" required>
          <el-input v-model="form.valueText" />
        </el-form-item>
        <el-form-item label="展示名">
          <el-input v-model="form.displayLabel" />
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="form.aliasesText" placeholder="逗号分隔，如 跳绳,跳绳项目" />
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
  createFieldValue,
  deleteFieldValue,
  listFieldValues,
  listMetaColumns,
  listMetaTables,
  updateFieldValue,
} from '../api/meta'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const values = ref([])
const tables = ref([])
const columnOptions = ref([])
const formColumns = ref([])
const filterTableId = ref(null)
const filterColumnId = ref(null)
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  tableId: null,
  columnId: null,
  valueText: '',
  displayLabel: '',
  aliasesText: '',
})

function parseAliases(text) {
  if (!text?.trim()) return []
  return text.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
}

onMounted(async () => {
  if (!(await guardMetaManager())) return
  await loadTables()
  await loadList()
})

async function guardMetaManager() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
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

async function loadColumnsForTable(tableId, target) {
  if (!tableId) {
    target.value = []
    return
  }
  target.value = await listMetaColumns(tableId)
}

async function onTableChange() {
  filterColumnId.value = null
  await loadColumnsForTable(filterTableId.value, columnOptions)
  await loadList()
}

async function onFormTableChange() {
  form.columnId = null
  await loadColumnsForTable(form.tableId, formColumns)
}

async function loadList() {
  loading.value = true
  try {
    const params = {}
    if (filterColumnId.value) params.columnId = filterColumnId.value
    else if (filterTableId.value) params.tableId = filterTableId.value
    values.value = await listFieldValues(params)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  Object.assign(form, {
    tableId: filterTableId.value || tables.value[0]?.id || null,
    columnId: filterColumnId.value || null,
    valueText: '',
    displayLabel: '',
    aliasesText: '',
  })
  loadColumnsForTable(form.tableId, formColumns).then(() => {
    dialogVisible.value = true
  })
}

function openEdit(row) {
  editId.value = row.id
  const table = tables.value.find((t) => t.tableName === row.tableName)
  Object.assign(form, {
    tableId: table?.id || null,
    columnId: row.columnId,
    valueText: row.valueText,
    displayLabel: row.displayLabel || '',
    aliasesText: (row.aliases || []).join('，'),
  })
  loadColumnsForTable(form.tableId, formColumns).then(() => {
    dialogVisible.value = true
  })
}

async function submit() {
  if (!form.columnId || !form.valueText.trim()) {
    ElMessage.warning('请选择字段并填写库中值')
    return
  }
  const body = {
    columnId: form.columnId,
    valueText: form.valueText.trim(),
    displayLabel: form.displayLabel.trim() || null,
    aliases: parseAliases(form.aliasesText),
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateFieldValue(editId.value, body)
    } else {
      await createFieldValue(body)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm('确定删除该取值？', '确认', { type: 'warning' })
  await deleteFieldValue(row.id)
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
.toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
</style>
