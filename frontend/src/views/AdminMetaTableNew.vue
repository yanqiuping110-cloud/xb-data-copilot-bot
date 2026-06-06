<template>
  <div class="layout">
    <header class="header">
      <span class="title">注册新表</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/admin/meta/tables')">返回列表</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <el-card>
        <el-steps :active="step" finish-status="success" align-center style="margin-bottom: 24px">
          <el-step title="输入表名" />
          <el-step title="预览结构" />
          <el-step title="补充定义" />
        </el-steps>

        <!-- Step 1: 表名 -->
        <div v-if="step === 0" class="step-panel">
          <el-form label-width="88px" style="max-width: 480px">
            <el-form-item label="业务表名" required>
              <el-input
                v-model="tableName"
                placeholder="如 sport_activity_qzs_record"
                @keyup.enter="onIntrospect"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="introspecting" @click="onIntrospect">
                从业务库读取
              </el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- Step 2+3: 预览与编辑 -->
        <div v-else class="step-panel">
          <el-alert
            v-if="preview.existsInCopilot"
            title="该表已在问数库注册，请前往字段页维护"
            type="warning"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          />

          <el-form label-width="100px" class="table-form">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="表名">
                  <el-input :model-value="preview.tableName" disabled />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="表角色">
                  <el-select v-model="tableForm.tableRole" clearable style="width: 100%">
                    <el-option label="事实表 (fact)" value="fact" />
                    <el-option label="维度表 (dimension)" value="dimension" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="业务库备注">
              <el-input :model-value="preview.tableCommentAuto" type="textarea" :rows="2" disabled />
            </el-form-item>
            <el-form-item label="问数描述">
              <el-input
                v-model="tableForm.descriptionManual"
                type="textarea"
                :rows="2"
                placeholder="人工定义，优先于业务库 COMMENT"
              />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="业务域">
                  <el-input v-model="tableForm.bizDomain" placeholder="如 活动打卡" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="学校字段">
                  <el-input v-model="tableForm.schIdColumn" placeholder="sch_id" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="粒度">
              <el-input v-model="tableForm.grain" placeholder="如 一人一项目一次打卡一条记录" />
            </el-form-item>
          </el-form>

          <p class="section-title">字段列表（业务库只读 + 问数定义可编辑）</p>
          <el-table :data="columnRows" border size="small" max-height="420">
            <el-table-column prop="columnName" label="字段名" width="140" fixed />
            <el-table-column prop="dataType" label="类型(自动)" width="120" />
            <el-table-column label="业务库备注(自动)" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.columnCommentAuto || '—' }}</template>
            </el-table-column>
            <el-table-column label="问数定义(人工)" min-width="180">
              <template #default="{ row }">
                <el-input v-model="row.descriptionManual" size="small" placeholder="问数用字段说明" />
              </template>
            </el-table-column>
            <el-table-column label="有效定义(预览)" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ effectiveDesc(row) }}</template>
            </el-table-column>
            <el-table-column label="角色" width="120">
              <template #default="{ row }">
                <el-select v-model="row.columnRole" size="small" clearable placeholder="角色">
                  <el-option v-for="r in columnRoles" :key="r.value" :label="r.label" :value="r.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="别名" min-width="140">
              <template #default="{ row }">
                <el-input v-model="row.aliasesText" size="small" placeholder="逗号分隔" />
              </template>
            </el-table-column>
            <el-table-column label="参与召回" width="100" fixed="right">
              <template #default="{ row }">
                <el-switch v-model="row.recallEnabled" active-text="是" inactive-text="否" />
              </template>
            </el-table-column>
          </el-table>

          <div class="footer-actions">
            <el-button @click="step = 0">上一步</el-button>
            <el-button
              v-if="!preview.existsInCopilot"
              type="primary"
              :loading="saving"
              @click="onSave"
            >
              保存入库
            </el-button>
            <el-button v-else type="primary" @click="goExisting">前往字段页</el-button>
          </div>
        </div>
      </el-card>
    </main>
  </div>
</template>

<script setup>
/** 注册新表向导：introspect 预览 → 双列备注 → 保存 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import { createMetaTable, introspectTable, listMetaTables, rebuildMetaIndex } from '../api/meta'

const router = useRouter()
const step = ref(0)
const tableName = ref('')
const introspecting = ref(false)
const saving = ref(false)

const preview = reactive({
  tableName: '',
  tableCommentAuto: '',
  existsInCopilot: false,
  columns: [],
})

const tableForm = reactive({
  tableRole: 'fact',
  bizDomain: '',
  descriptionManual: '',
  grain: '',
  schIdColumn: 'sch_id',
})

const columnRows = ref([])

const columnRoles = [
  { value: 'pk', label: '主键' },
  { value: 'fk', label: '外键' },
  { value: 'measure', label: '度量' },
  { value: 'dimension', label: '维度' },
  { value: 'filter', label: '过滤' },
  { value: 'time', label: '时间' },
]

function effectiveDesc(row) {
  const manual = (row.descriptionManual || '').trim()
  const auto = (row.columnCommentAuto || '').trim()
  return manual || auto || '—'
}

function parseAliases(text) {
  if (!text || !text.trim()) return undefined
  return text
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

onMounted(async () => {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
      ElMessage.warning('需要管理员或运营权限')
      router.replace('/')
      return
    }
    localStorage.setItem('userRole', res.user.role)
  } catch {
    router.push('/login')
  }
})

async function onIntrospect() {
  const name = tableName.value.trim()
  if (!name) {
    ElMessage.warning('请输入表名')
    return
  }
  introspecting.value = true
  try {
    const res = await introspectTable(name)
    preview.tableName = res.tableName
    preview.tableCommentAuto = res.tableCommentAuto || ''
    preview.existsInCopilot = res.existsInCopilot
    preview.columns = res.columns || []

    tableForm.descriptionManual = ''
    tableForm.bizDomain = ''
    tableForm.grain = ''
    tableForm.tableRole = 'fact'
    tableForm.schIdColumn = 'sch_id'

    columnRows.value = (res.columns || []).map((c) => ({
      columnName: c.columnName,
      dataType: c.dataType,
      columnCommentAuto: c.columnCommentAuto || '',
      descriptionManual: '',
      columnRole: '',
      aliasesText: '',
      recallEnabled: true,
    }))

    step.value = 1
    if (!res.columns?.length) {
      ElMessage.warning('业务库未找到该表或字段为空')
    }
  } finally {
    introspecting.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const columns = columnRows.value.map((c) => ({
      columnName: c.columnName,
      descriptionManual: c.descriptionManual?.trim() || null,
      columnRole: c.columnRole || null,
      aliases: parseAliases(c.aliasesText),
      recallEnabled: c.recallEnabled !== false,
    }))

    const row = await createMetaTable({
      tableName: preview.tableName,
      tableRole: tableForm.tableRole || null,
      bizDomain: tableForm.bizDomain.trim() || null,
      descriptionManual: tableForm.descriptionManual.trim() || null,
      grain: tableForm.grain.trim() || null,
      schIdColumn: tableForm.schIdColumn.trim() || 'sch_id',
      status: 1,
      columns,
    })

    ElMessage.success('表已注册')
    try {
      await ElMessageBox.confirm('是否立即重建检索索引？', '重建索引', {
        confirmButtonText: '重建',
        cancelButtonText: '稍后',
        type: 'info',
      })
      const idx = await rebuildMetaIndex()
      ElMessage.success(
        `索引完成：字段 ${idx.columns}、指标 ${idx.metrics}、取值 ${idx.fieldValues}`,
      )
    } catch {
      /* 稍后 */
    }
    router.push(`/admin/meta/tables/${row.id}/columns`)
  } finally {
    saving.value = false
  }
}

async function goExisting() {
  const res = await listMetaTables({ offset: 0, limit: 200 })
  const found = res.items.find((t) => t.tableName === preview.tableName)
  if (found) {
    router.push(`/admin/meta/tables/${found.id}/columns`)
  } else {
    router.push('/admin/meta/tables')
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
  max-width: 1200px;
  margin: 24px auto;
  padding: 0 16px;
}
.step-panel {
  min-height: 200px;
}
.section-title {
  margin: 20px 0 12px;
  font-weight: 600;
  color: #303133;
}
.footer-actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
</style>
