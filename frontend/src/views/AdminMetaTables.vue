<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · 表管理</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-button type="primary" @click="router.push('/admin/meta/tables/new')">注册新表</el-button>
          <el-button :loading="rebuilding" @click="onRebuildIndex">重建检索索引</el-button>
        </div>

        <el-table v-loading="loading" :data="tables" border style="margin-top: 16px">
          <el-table-column prop="tableName" label="表名" min-width="200" />
          <el-table-column prop="bizDomain" label="业务域" min-width="100" />
          <el-table-column label="角色" width="90">
            <template #default="{ row }">{{ row.tableRole || '—' }}</template>
          </el-table-column>
          <el-table-column label="有效描述" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.effectiveDescription || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
                {{ row.status === 1 ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近 introspect" width="160">
            <template #default="{ row }">{{ formatTime(row.lastIntrospectedAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="router.push(`/admin/meta/tables/${row.id}/columns`)">
                字段
              </el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="primary" :loading="refreshingId === row.id" @click="onRefresh(row)">
                刷新结构
              </el-button>
              <el-button
                link
                :type="row.status === 1 ? 'danger' : 'success'"
                @click="toggleStatus(row)"
              >
                {{ row.status === 1 ? '停用' : '启用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="editVisible" title="编辑表定义" width="560px" destroy-on-close>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="表名">
          <el-input :model-value="editForm.tableName" disabled />
        </el-form-item>
        <el-form-item label="业务库备注">
          <el-input :model-value="editForm.tableCommentAuto" type="textarea" :rows="2" disabled />
        </el-form-item>
        <el-form-item label="问数描述">
          <el-input v-model="editForm.descriptionManual" type="textarea" :rows="2" placeholder="人工定义，优先于业务库备注" />
        </el-form-item>
        <el-form-item label="表角色">
          <el-select v-model="editForm.tableRole" clearable placeholder="如 fact / dimension" style="width: 100%">
            <el-option label="事实表 (fact)" value="fact" />
            <el-option label="维度表 (dimension)" value="dimension" />
          </el-select>
        </el-form-item>
        <el-form-item label="业务域">
          <el-input v-model="editForm.bizDomain" placeholder="如 活动打卡" />
        </el-form-item>
        <el-form-item label="粒度">
          <el-input v-model="editForm.grain" placeholder="如 一人一项目一次打卡一条记录" />
        </el-form-item>
        <el-form-item label="维度绑定">
          <div class="bindings">
            <div v-for="(b, idx) in editForm.scopeBindings" :key="idx" class="binding-row">
              <el-select
                v-model="b.dimensionCode"
                placeholder="维度"
                style="width: 140px"
                filterable
              >
                <el-option
                  v-for="d in scopeDimensions"
                  :key="d.code"
                  :label="`${d.display_name} (${d.code})`"
                  :value="d.code"
                />
              </el-select>
              <el-select
                v-model="b.columnName"
                placeholder="物理列"
                style="flex: 1"
                filterable
                allow-create
                default-first-option
              >
                <el-option
                  v-for="c in tableColumns"
                  :key="c.columnName"
                  :label="c.columnName"
                  :value="c.columnName"
                />
              </el-select>
              <el-button link type="danger" @click="editForm.scopeBindings.splice(idx, 1)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addBindingRow">添加绑定</el-button>
          </div>
          <p class="field-hint">
            仅对「确实有该物理列」的表绑定维度；无学校隔离的维表请留空。删掉绑定后点保存才会生效。
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 元数据表列表：CRUD、刷新结构、重建索引 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import {
  listMetaColumns,
  listMetaTables,
  rebuildMetaIndex,
  refreshMetaTable,
  updateMetaTable,
} from '../api/meta'
import { getTableScopeBindings, listScopeDimensions, putTableScopeBindings } from '../api/scope'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const refreshingId = ref(null)
const tables = ref([])
const scopeDimensions = ref([])
const tableColumns = ref([])

const editVisible = ref(false)
const editForm = reactive({
  id: null,
  tableName: '',
  tableCommentAuto: '',
  descriptionManual: '',
  tableRole: '',
  bizDomain: '',
  grain: '',
  status: 1,
  scopeBindings: [],
})

function formatTime(iso) {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 19)
}

async function ensureMetaManager() {
  const res = await fetchMe()
  if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
    ElMessage.warning('需要管理员或运营权限')
    router.replace('/')
    return false
  }
  localStorage.setItem('userRole', res.user.role)
  return true
}

onMounted(async () => {
  try {
    if (!(await ensureMetaManager())) return
    await Promise.all([loadList(), loadScopeDimensions()])
  } catch {
    router.push('/login')
  }
})

async function loadScopeDimensions() {
  try {
    const res = await listScopeDimensions()
    scopeDimensions.value = res.items || []
  } catch {
    scopeDimensions.value = []
  }
}

function addBindingRow() {
  editForm.scopeBindings.push({ dimensionCode: '', columnName: '' })
}

async function loadList() {
  loading.value = true
  try {
    const res = await listMetaTables({ offset: 0, limit: 200 })
    tables.value = res.items
  } finally {
    loading.value = false
  }
}

async function openEdit(row) {
  Object.assign(editForm, {
    id: row.id,
    tableName: row.tableName,
    tableCommentAuto: row.tableCommentAuto || '',
    descriptionManual: row.descriptionManual || '',
    tableRole: row.tableRole || '',
    bizDomain: row.bizDomain || '',
    grain: row.grain || '',
    status: row.status,
    scopeBindings: [],
  })
  try {
    const [colsRes, bindRes] = await Promise.all([
      listMetaColumns(row.id),
      getTableScopeBindings(row.id),
    ])
    tableColumns.value = colsRes.items || []
    const bindings = bindRes.items || []
    // 只展示库里真实绑定；不要用 schIdColumn 默认塞回 school（否则删了再打开又出现）
    editForm.scopeBindings = bindings.map((b) => ({
      dimensionCode: b.dimensionCode,
      columnName: b.columnName,
    }))
  } catch {
    tableColumns.value = []
    editForm.scopeBindings = []
  }
  editVisible.value = true
}

async function submitEdit() {
  const bindings = editForm.scopeBindings
    .filter((b) => b.dimensionCode && b.columnName)
    .map((b) => ({ dimensionCode: b.dimensionCode, columnName: b.columnName.trim() }))
  saving.value = true
  try {
    const schoolBinding = bindings.find((b) => b.dimensionCode === 'school')
    await updateMetaTable(editForm.id, {
      tableRole: editForm.tableRole || null,
      bizDomain: editForm.bizDomain.trim() || null,
      descriptionManual: editForm.descriptionManual.trim() || null,
      grain: editForm.grain.trim() || null,
      schIdColumn: schoolBinding?.columnName || null,
    })
    await putTableScopeBindings(editForm.id, bindings)
    ElMessage.success('已保存')
    editVisible.value = false
    await loadList()
    await promptRebuild('表定义已更新')
  } finally {
    saving.value = false
  }
}

async function onRefresh(row) {
  refreshingId.value = row.id
  try {
    await refreshMetaTable(row.id)
    ElMessage.success('已从业务库刷新结构（人工定义已保留）')
    await loadList()
    await promptRebuild('表结构已刷新')
  } finally {
    refreshingId.value = null
  }
}

async function toggleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  const action = next === 0 ? '停用' : '启用'
  await ElMessageBox.confirm(`确定${action}表「${row.tableName}」？`, '确认', { type: 'warning' })
  await updateMetaTable(row.id, { status: next })
  ElMessage.success(`已${action}`)
  await loadList()
}

async function doRebuild() {
  rebuilding.value = true
  try {
    const res = await rebuildMetaIndex()
    ElMessage.success(
      `索引重建完成：字段 ${res.columns}、指标 ${res.metrics}、取值 ${res.fieldValues}、维度 ${res.embeddingDims}`,
    )
  } finally {
    rebuilding.value = false
  }
}

async function onRebuildIndex() {
  await ElMessageBox.confirm(
    '将全量重建字段、指标与取值检索索引，需 Embedding 服务可用。继续？',
    '重建检索索引',
    { type: 'warning' },
  )
  await doRebuild()
}

async function promptRebuild(reason) {
  try {
    await ElMessageBox.confirm(`${reason}，是否立即重建检索索引？`, '重建索引', {
      confirmButtonText: '重建',
      cancelButtonText: '稍后',
      type: 'info',
    })
    await doRebuild()
  } catch {
    /* 用户选择稍后 */
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: #f5f7fa;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.title {
  font-weight: 600;
  font-size: 18px;
}
.toolbar {
  display: flex;
  gap: 12px;
}
.main {
  max-width: 1200px;
  margin: 24px auto;
  padding: 0 16px;
}
.bindings {
  width: 100%;
}
.binding-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.field-hint {
  margin: 8px 0 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
</style>
