<template>
  <div class="layout">
    <header class="header">
      <span class="title">字段元数据 · {{ table?.tableName || '…' }}</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/admin/meta/tables')">返回列表</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <MetaAdminNav />
      <el-card v-loading="loading">
        <template v-if="table">
          <el-descriptions :column="2" border size="small" style="margin-bottom: 16px">
            <el-descriptions-item label="表名">{{ table.tableName }}</el-descriptions-item>
            <el-descriptions-item label="业务域">{{ table.bizDomain || '—' }}</el-descriptions-item>
            <el-descriptions-item label="业务库备注">{{ table.tableCommentAuto || '—' }}</el-descriptions-item>
            <el-descriptions-item label="问数描述">{{ table.descriptionManual || '—' }}</el-descriptions-item>
            <el-descriptions-item label="有效描述" :span="2">
              {{ table.effectiveDescription || '—' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="toolbar">
            <el-button type="primary" @click="openTableEdit">编辑表定义</el-button>
            <el-button :loading="refreshing" @click="onRefresh">刷新结构</el-button>
            <el-button
              type="primary"
              :loading="columnsSaving"
              :disabled="!hasDirtyColumns"
              @click="saveAllColumns"
            >
              保存字段定义{{ dirtyCount ? `（${dirtyCount}）` : '' }}
            </el-button>
            <el-checkbox v-model="hideDeprecated">隐藏废弃字段</el-checkbox>
          </div>
        </template>

        <el-table
          :data="visibleColumns"
          border
          size="small"
          class="columns-table"
          :max-height="tableMaxHeight"
          :row-class-name="rowClassName"
        >
          <el-table-column prop="columnName" label="字段名" width="140" fixed />
          <el-table-column prop="dataType" label="类型(自动)" width="110" />
          <el-table-column label="业务库备注(自动)" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.columnCommentAuto || '—' }}</template>
          </el-table-column>
          <el-table-column label="问数定义(人工)" min-width="160">
            <template #default="{ row }">
              <el-input
                v-model="row._descriptionManual"
                size="small"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
              />
            </template>
          </el-table-column>
          <el-table-column label="有效定义(预览)" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ effectiveDesc(row) }}</template>
          </el-table-column>
          <el-table-column label="角色" width="120">
            <template #default="{ row }">
              <el-select v-model="row._columnRole" size="small" clearable placeholder="角色">
                <el-option v-for="r in columnRoles" :key="r.value" :label="r.label" :value="r.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="别名" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row._aliasesText" size="small" placeholder="逗号分隔" />
            </template>
          </el-table-column>
          <el-table-column label="参与召回" width="132" align="center" fixed="right">
            <template #default="{ row }">
              <div class="recall-cell">
                <el-switch v-model="row._recallEnabled" :disabled="row.status === 0" />
                <span class="recall-label">{{ row._recallEnabled ? '是' : '否' }}</span>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="tableEditVisible" title="编辑表定义" width="560px" destroy-on-close>
      <el-form v-if="table" :model="tableEditForm" label-width="100px">
        <el-form-item label="问数描述">
          <el-input v-model="tableEditForm.descriptionManual" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="表角色">
          <el-select v-model="tableEditForm.tableRole" clearable style="width: 100%">
            <el-option label="事实表 (fact)" value="fact" />
            <el-option label="维度表 (dimension)" value="dimension" />
          </el-select>
        </el-form-item>
        <el-form-item label="业务域">
          <el-input v-model="tableEditForm.bizDomain" />
        </el-form-item>
        <el-form-item label="粒度">
          <el-input v-model="tableEditForm.grain" />
        </el-form-item>
        <el-form-item label="学校字段">
          <el-input v-model="tableEditForm.schIdColumn" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tableEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="tableSaving" @click="submitTableEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 字段元数据页：双列备注、人工定义编辑、有效定义预览 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import {
  getMetaTable,
  listMetaColumns,
  rebuildMetaIndex,
  refreshMetaTable,
  updateMetaColumn,
  updateMetaTable,
} from '../api/meta'

const route = useRoute()
const router = useRouter()
const tableId = Number(route.params.id)
const tableMaxHeight = 'calc(100vh - 260px)'

const loading = ref(false)
const refreshing = ref(false)
const tableSaving = ref(false)
const columnsSaving = ref(false)
const hideDeprecated = ref(false)
const table = ref(null)
const columns = ref([])

const dirtyCount = computed(() => columns.value.filter(isDirty).length)
const hasDirtyColumns = computed(() => dirtyCount.value > 0)
const visibleColumns = computed(() =>
  hideDeprecated.value ? columns.value.filter((row) => row._recallEnabled) : columns.value,
)

const tableEditVisible = ref(false)
const tableEditForm = reactive({
  descriptionManual: '',
  tableRole: '',
  bizDomain: '',
  grain: '',
  schIdColumn: 'sch_id',
})

const columnRoles = [
  { value: 'pk', label: '主键' },
  { value: 'fk', label: '外键' },
  { value: 'measure', label: '度量' },
  { value: 'dimension', label: '维度' },
  { value: 'filter', label: '过滤' },
  { value: 'time', label: '时间' },
]

function aliasesToText(list) {
  return (list || []).join('，')
}

function parseAliases(text) {
  if (!text || !text.trim()) return []
  return text
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function bindColumnRow(row) {
  return {
    ...row,
    _descriptionManual: row.descriptionManual || '',
    _columnRole: row.columnRole || '',
    _aliasesText: aliasesToText(row.aliases),
    _recallEnabled: row.recallEnabled !== false,
  }
}

function rowClassName({ row }) {
  if (!row._recallEnabled) return 'row-deprecated'
  if (row.status === 0) return 'row-removed'
  return ''
}

function effectiveDesc(row) {
  const manual = (row._descriptionManual || '').trim()
  const auto = (row.columnCommentAuto || '').trim()
  return manual || auto || '—'
}

function isDirty(row) {
  const aliases = parseAliases(row._aliasesText)
  const origAliases = row.aliases || []
  const aliasesChanged =
    aliases.length !== origAliases.length || aliases.some((a, i) => a !== origAliases[i])
  const recallChanged = row._recallEnabled !== (row.recallEnabled !== false)
  return (
    (row._descriptionManual || '') !== (row.descriptionManual || '') ||
    (row._columnRole || '') !== (row.columnRole || '') ||
    aliasesChanged ||
    recallChanged
  )
}

onMounted(async () => {
  if (!tableId || Number.isNaN(tableId)) {
    router.replace('/admin/meta/tables')
    return
  }
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
      ElMessage.warning('需要管理员或运营权限')
      router.replace('/')
      return
    }
    localStorage.setItem('userRole', res.user.role)
    await loadAll()
  } catch {
    router.push('/login')
  }
})

async function loadAll() {
  loading.value = true
  try {
    table.value = await getMetaTable(tableId)
    const cols = await listMetaColumns(tableId)
    columns.value = cols.map(bindColumnRow)
  } finally {
    loading.value = false
  }
}

function openTableEdit() {
  Object.assign(tableEditForm, {
    descriptionManual: table.value.descriptionManual || '',
    tableRole: table.value.tableRole || '',
    bizDomain: table.value.bizDomain || '',
    grain: table.value.grain || '',
    schIdColumn: table.value.schIdColumn || 'sch_id',
  })
  tableEditVisible.value = true
}

async function submitTableEdit() {
  tableSaving.value = true
  try {
    table.value = await updateMetaTable(tableId, {
      descriptionManual: tableEditForm.descriptionManual.trim() || null,
      tableRole: tableEditForm.tableRole || null,
      bizDomain: tableEditForm.bizDomain.trim() || null,
      grain: tableEditForm.grain.trim() || null,
      schIdColumn: tableEditForm.schIdColumn.trim() || 'sch_id',
    })
    ElMessage.success('表定义已保存')
    tableEditVisible.value = false
    await promptRebuild('表定义已更新')
  } finally {
    tableSaving.value = false
  }
}

async function onRefresh() {
  refreshing.value = true
  try {
    table.value = await refreshMetaTable(tableId)
    const cols = await listMetaColumns(tableId)
    columns.value = cols.map((c) => {
      const prev = columns.value.find((p) => p.id === c.id)
      const bound = bindColumnRow(c)
      if (prev && isDirty(prev)) {
        bound._descriptionManual = prev._descriptionManual
        bound._columnRole = prev._columnRole
        bound._aliasesText = prev._aliasesText
        bound._recallEnabled = prev._recallEnabled
      }
      return bound
    })
    ElMessage.success('已从业务库刷新（未保存的人工编辑仍保留在输入框）')
    await promptRebuild('表结构已刷新')
  } finally {
    refreshing.value = false
  }
}

async function saveAllColumns() {
  const dirty = columns.value.filter(isDirty)
  if (!dirty.length) return

  columnsSaving.value = true
  try {
    const updatedList = await Promise.all(
      dirty.map((row) =>
        updateMetaColumn(row.id, {
          descriptionManual: row._descriptionManual.trim() || null,
          columnRole: row._columnRole || null,
          aliases: parseAliases(row._aliasesText),
          recallEnabled: row._recallEnabled,
        }),
      ),
    )
    updatedList.forEach((updated, index) => {
      Object.assign(dirty[index], bindColumnRow(updated))
    })
    ElMessage.success(`已保存 ${dirty.length} 个字段`)
    await promptRebuild(`${dirty.length} 个字段已更新`)
  } finally {
    columnsSaving.value = false
  }
}

async function promptRebuild(reason) {
  try {
    await ElMessageBox.confirm(`${reason}，是否立即重建检索索引？`, '重建索引', {
      confirmButtonText: '重建',
      cancelButtonText: '稍后',
      type: 'info',
    })
    const res = await rebuildMetaIndex()
    ElMessage.success(
      `索引完成：字段 ${res.columns}、指标 ${res.metrics}、取值 ${res.fieldValues}`,
    )
  } catch {
    /* 稍后 */
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
.main {
  max-width: min(1680px, calc(100vw - 32px));
  margin: 24px auto;
  padding: 0 16px;
}
.columns-table {
  margin-top: 16px;
  width: 100%;
}
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.recall-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 88px;
}
.recall-label {
  font-size: 12px;
  color: #606266;
  min-width: 14px;
}
:deep(.row-deprecated) {
  --el-table-tr-bg-color: #fafafa;
  color: #909399;
}
:deep(.row-removed) {
  --el-table-tr-bg-color: #fef0f0;
}
</style>
