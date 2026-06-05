<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · 指标</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-button type="primary" @click="openCreate">新增指标</el-button>
        </div>
        <el-table v-loading="loading" :data="metrics" border style="margin-top: 16px">
          <el-table-column prop="metricCode" label="编码" width="160" />
          <el-table-column prop="metricName" label="名称" min-width="140" />
          <el-table-column prop="relevantTables" label="相关表" min-width="140" show-overflow-tooltip />
          <el-table-column prop="formulaText" label="公式" min-width="120" show-overflow-tooltip />
          <el-table-column label="仅超管" width="80">
            <template #default="{ row }">{{ row.adminOnly ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column label="关联字段" min-width="160">
            <template #default="{ row }">
              {{ (row.columnLinks || []).map((l) => `${l.tableName}.${l.columnName}`).join('；') || '—' }}
            </template>
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

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑指标' : '新增指标'" width="640px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="编码" required>
          <el-input v-model="form.metricCode" :disabled="!!editId" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.metricName" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="相关表">
          <el-input v-model="form.relevantTables" placeholder="逗号分隔表名" />
        </el-form-item>
        <el-form-item label="公式">
          <el-input v-model="form.formulaText" placeholder="如 COUNT(DISTINCT people_id)" />
        </el-form-item>
        <el-form-item label="过滤提示">
          <el-input v-model="form.filterHint" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="时间字段">
              <el-input v-model="form.timeColumn" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="聚合类型">
              <el-input v-model="form.aggType" placeholder="count_distinct" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="单位">
          <el-input v-model="form.unit" style="width: 120px" />
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="form.aliasesText" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="关联字段">
          <div v-for="(link, idx) in form.columnLinks" :key="idx" class="link-row">
            <el-select v-model="link.columnId" filterable placeholder="选择字段" style="flex: 1">
              <el-option
                v-for="c in allColumns"
                :key="c.id"
                :label="`${c.tableName}.${c.columnName}`"
                :value="c.id"
              />
            </el-select>
            <el-select v-model="link.usageType" style="width: 130px">
              <el-option label="度量" value="measure" />
              <el-option label="过滤" value="filter" />
              <el-option label="分组" value="group_by" />
              <el-option label="JOIN键" value="join_key" />
            </el-select>
            <el-button link type="danger" @click="form.columnLinks.splice(idx, 1)">删</el-button>
          </div>
          <el-button link type="primary" @click="form.columnLinks.push({ columnId: null, usageType: 'measure' })">
            + 添加字段
          </el-button>
        </el-form-item>
        <el-form-item label="仅超管/运营">
          <el-switch v-model="form.adminOnly" />
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
  createMetric,
  deleteMetric,
  listMetaColumns,
  listMetaTables,
  listMetrics,
  updateMetric,
} from '../api/meta'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const metrics = ref([])
const allColumns = ref([])
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  metricCode: '',
  metricName: '',
  description: '',
  relevantTables: '',
  formulaText: '',
  filterHint: '',
  timeColumn: '',
  aggType: '',
  unit: '',
  aliasesText: '',
  adminOnly: false,
  columnLinks: [],
})

function parseAliases(text) {
  if (!text?.trim()) return []
  return text.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
}

onMounted(async () => {
  if (!(await guardMetaManager())) return
  await loadAllColumns()
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

async function loadAllColumns() {
  const tables = await listMetaTables({ offset: 0, limit: 200 })
  const cols = []
  for (const t of tables.items) {
    const list = await listMetaColumns(t.id)
    for (const c of list) {
      cols.push({ id: c.id, tableName: t.tableName, columnName: c.columnName })
    }
  }
  allColumns.value = cols
}

async function loadList() {
  loading.value = true
  try {
    metrics.value = await listMetrics()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  Object.assign(form, {
    metricCode: '',
    metricName: '',
    description: '',
    relevantTables: '',
    formulaText: '',
    filterHint: '',
    timeColumn: '',
    aggType: '',
    unit: '',
    aliasesText: '',
    adminOnly: false,
    columnLinks: [],
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  Object.assign(form, {
    metricCode: row.metricCode,
    metricName: row.metricName,
    description: row.description || '',
    relevantTables: row.relevantTables || '',
    formulaText: row.formulaText || '',
    filterHint: row.filterHint || '',
    timeColumn: row.timeColumn || '',
    aggType: row.aggType || '',
    unit: row.unit || '',
    aliasesText: (row.aliases || []).join('，'),
    adminOnly: !!row.adminOnly,
    columnLinks: (row.columnLinks || []).map((l) => ({
      columnId: l.columnId,
      usageType: l.usageType,
    })),
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.metricCode.trim() || !form.metricName.trim()) {
    ElMessage.warning('请填写编码与名称')
    return
  }
  const columnLinks = form.columnLinks
    .filter((l) => l.columnId)
    .map((l) => ({ columnId: l.columnId, usageType: l.usageType || 'measure' }))
  const body = {
    metricName: form.metricName.trim(),
    description: form.description.trim() || null,
    relevantTables: form.relevantTables.trim() || null,
    formulaText: form.formulaText.trim() || null,
    filterHint: form.filterHint.trim() || null,
    timeColumn: form.timeColumn.trim() || null,
    aggType: form.aggType.trim() || null,
    unit: form.unit.trim() || null,
    aliases: parseAliases(form.aliasesText),
    adminOnly: form.adminOnly,
    columnLinks,
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateMetric(editId.value, body)
    } else {
      await createMetric({ ...body, metricCode: form.metricCode.trim() })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确定删除指标「${row.metricName}」？`, '确认', { type: 'warning' })
  await deleteMetric(row.id)
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
.link-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
</style>
