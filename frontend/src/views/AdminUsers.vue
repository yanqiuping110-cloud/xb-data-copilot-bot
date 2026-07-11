<template>
  <div class="layout">
    <header class="header">
      <span class="title">用户管理</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <el-card>
        <div class="toolbar">
          <el-select v-model="roleFilter" placeholder="全部角色" clearable style="width: 140px" @change="loadList">
            <el-option label="运营" value="OPERATOR" />
            <el-option label="渠道" value="SCHOOL" />
          </el-select>
          <el-button type="primary" @click="openCreate">新建用户</el-button>
        </div>

        <el-table v-loading="loading" :data="users" border style="margin-top: 16px">
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="displayName" label="显示名" min-width="120" />
          <el-table-column label="角色" width="90">
            <template #default="{ row }">{{ roleLabel(row.role) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
                {{ row.status === 1 ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="数据授权" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.role === 'ADMIN'">—</span>
              <span v-else>{{ grantSummaryMap[row.id] || '未配置' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <template v-if="row.role !== 'ADMIN'">
                <el-button link type="primary" @click="openPatch(row)">编辑</el-button>
                <el-button link type="primary" @click="openGrants(row)">数据授权</el-button>
                <el-button
                  link
                  :type="row.status === 1 ? 'danger' : 'success'"
                  @click="toggleStatus(row)"
                >
                  {{ row.status === 1 ? '禁用' : '启用' }}
                </el-button>
              </template>
              <span v-else class="muted">超管</span>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          style="margin-top: 16px; justify-content: flex-end"
          @current-change="loadList"
          @size-change="loadList"
        />
      </el-card>
    </main>

    <!-- 新建用户 -->
    <el-dialog v-model="createVisible" title="新建用户" width="560px" destroy-on-close>
      <el-form :model="createForm" label-width="88px">
        <el-form-item label="用户名" required>
          <el-input v-model="createForm.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="createForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="createForm.role" style="width: 100%" @change="onCreateRoleChange">
            <el-option label="运营" value="OPERATOR" />
            <el-option label="渠道" value="SCHOOL" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="createForm.displayName" />
        </el-form-item>
        <template v-if="createForm.role !== 'ADMIN'">
          <el-divider content-position="left">数据授权</el-divider>
          <p class="hint">启用 DataScope 后须配置可见表；行级维度可选（不配则不按学校等维度过滤）。渠道账户须配置 school。</p>
          <div v-for="(row, idx) in createForm.grantRows" :key="idx" class="grant-row">
            <el-select v-model="row.dimensionCode" placeholder="维度" style="width: 150px" filterable>
              <el-option
                v-for="d in scopeDimensions"
                :key="d.code"
                :label="`${d.display_name} (${d.code})`"
                :value="d.code"
              />
            </el-select>
            <el-input
              v-model="row.valuesText"
              placeholder="允许多值，逗号分隔"
              style="flex: 1"
            />
            <el-button link type="danger" @click="createForm.grantRows.splice(idx, 1)">删除</el-button>
          </div>
          <el-button link type="primary" @click="addGrantRow(createForm.grantRows)">添加维度授权</el-button>
          <el-form-item label="可见表" style="margin-top: 12px">
            <el-select
              v-model="createForm.tableNames"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择可查询的表"
              style="width: 100%"
            >
              <el-option v-for="t in metaTables" :key="t.id" :label="t.tableName" :value="t.tableName" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑：显示名 / 重置密码 -->
    <el-dialog v-model="patchVisible" title="编辑用户" width="420px" destroy-on-close>
      <el-form :model="patchForm" label-width="88px">
        <el-form-item label="用户名">
          <el-input :model-value="patchForm.username" disabled />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="patchForm.displayName" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="patchForm.password"
            type="password"
            show-password
            placeholder="留空则不修改"
            autocomplete="new-password"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="patchVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitPatch">保存</el-button>
      </template>
    </el-dialog>

    <!-- 数据授权 -->
    <el-dialog v-model="grantsVisible" title="数据授权" width="600px" destroy-on-close>
      <p class="hint">
        行级授权可选：每个维度配置多值 IN；不配则不注入行级过滤。表级授权：限制可查询的表白名单（必填）。
      </p>
      <el-form label-width="88px">
        <el-form-item label="行级维度">
          <div class="grant-block">
            <div v-for="(row, idx) in grantsForm.grantRows" :key="idx" class="grant-row">
              <el-select v-model="row.dimensionCode" placeholder="维度" style="width: 150px" filterable>
                <el-option
                  v-for="d in scopeDimensions"
                  :key="d.code"
                  :label="`${d.display_name} (${d.code})`"
                  :value="d.code"
                />
              </el-select>
              <el-input v-model="row.valuesText" placeholder="多值逗号分隔，如 1140,1220" style="flex: 1" />
              <el-button link type="danger" @click="grantsForm.grantRows.splice(idx, 1)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addGrantRow(grantsForm.grantRows)">添加维度</el-button>
          </div>
        </el-form-item>
        <el-form-item label="可见表">
          <el-select
            v-model="grantsForm.tableNames"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择可查询的表"
            style="width: 100%"
          >
            <el-option v-for="t in metaTables" :key="t.id" :label="t.tableName" :value="t.tableName" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantsVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitGrants">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 超管用户管理：列表、创建、数据授权（DataScope） */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import { createUser, listUsers, patchUser, replaceSchools } from '../api/admin'
import { listMetaTables } from '../api/meta'
import {
  getUserGrants,
  listScopeDimensions,
  putUserDataGrants,
  putUserTableGrants,
} from '../api/scope'
import { formatGrantsSummary, parseGrantValues } from '../utils/scopeGrants'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const roleFilter = ref(null)
const scopeDimensions = ref([])
const metaTables = ref([])
const grantSummaryMap = ref({})

const createVisible = ref(false)
const createForm = reactive({
  username: '',
  password: '',
  role: 'OPERATOR',
  displayName: '',
  grantRows: [],
  tableNames: [],
})

const patchVisible = ref(false)
const patchForm = reactive({
  userId: null,
  username: '',
  displayName: '',
  password: '',
})

const grantsVisible = ref(false)
const grantsForm = reactive({
  userId: null,
  role: '',
  grantRows: [],
  tableNames: [],
})

function roleLabel(role) {
  return { ADMIN: '超管', OPERATOR: '运营', SCHOOL: '渠道' }[role] || role
}

function dimValueType(code) {
  return scopeDimensions.value.find((d) => d.code === code)?.value_type || 'int'
}

function normalizeTableNames(saved) {
  const byLower = new Map(
    metaTables.value.map((t) => [String(t.tableName || '').toLowerCase(), t.tableName]),
  )
  return (saved || [])
    .map((n) => byLower.get(String(n).toLowerCase()) || n)
    .filter(Boolean)
}

function addGrantRow(rows) {
  rows.push({ dimensionCode: '', valuesText: '' })
}

function buildGrantsPayload(grantRows) {
  const grants = {}
  for (const row of grantRows) {
    if (!row.dimensionCode) continue
    const values = parseGrantValues(row.valuesText, dimValueType(row.dimensionCode))
    if (values.length) grants[row.dimensionCode] = values
  }
  return grants
}

function grantRowsFromData(dataGrants) {
  if (!dataGrants || !Object.keys(dataGrants).length) {
    // 无行级授权 = 不限制维度；不要默认塞空的 school 行
    return []
  }
  return Object.entries(dataGrants).map(([code, vals]) => ({
    dimensionCode: code,
    valuesText: (vals || []).join(', '),
  }))
}

async function syncSchoolLegacy(userId, grants, role) {
  if (role !== 'SCHOOL' || !grants.school?.length) return
  await replaceSchools(userId, { schIds: grants.school })
}

async function loadGrantSummaries(items) {
  const map = {}
  const targets = items.filter((u) => u.role !== 'ADMIN')
  await Promise.all(
    targets.map(async (u) => {
      try {
        const res = await getUserGrants(u.id)
        const parts = []
        const dg = res.dataGrants || {}
        const summary = formatGrantsSummary(dg, scopeDimensions.value)
        if (summary !== '—') parts.push(summary)
        const tables = res.tableGrants || []
        if (tables.length) parts.push(`表×${tables.length}`)
        map[u.id] = parts.length ? parts.join('；') : '未配置'
      } catch {
        map[u.id] = '—'
      }
    }),
  )
  grantSummaryMap.value = map
}

onMounted(async () => {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可访问用户管理')
      router.replace('/')
      return
    }
    localStorage.setItem('userRole', res.user.role)
    await Promise.all([loadScopeDimensions(), loadMetaTables()])
    await loadList()
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

async function loadMetaTables() {
  try {
    const res = await listMetaTables({ offset: 0, limit: 200 })
    metaTables.value = res.items || []
  } catch {
    metaTables.value = []
  }
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, pageSize: pageSize.value }
    if (roleFilter.value) params.role = roleFilter.value
    const res = await listUsers(params)
    users.value = res.items
    total.value = res.total
    await loadGrantSummaries(res.items)
  } finally {
    loading.value = false
  }
}

function onCreateRoleChange() {
  if (createForm.role === 'SCHOOL' && !createForm.grantRows.length) {
    createForm.grantRows = [{ dimensionCode: 'school', valuesText: '' }]
  }
}

function openCreate() {
  Object.assign(createForm, {
    username: '',
    password: '',
    role: 'OPERATOR',
    displayName: '',
    grantRows: [],
    tableNames: [],
  })
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.username.trim() || !createForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  const grants = buildGrantsPayload(createForm.grantRows)
  if (createForm.role === 'SCHOOL' && !grants.school?.length) {
    ElMessage.warning('渠道账户须配置 school 维度授权（或兼容的渠道 ID）')
    return
  }
  saving.value = true
  try {
    const body = {
      username: createForm.username.trim(),
      password: createForm.password,
      role: createForm.role,
      displayName: createForm.displayName.trim() || undefined,
    }
    if (createForm.role === 'SCHOOL' && grants.school?.length) {
      body.schIds = grants.school
    }
    const created = await createUser(body)
    const userId = created.id
    if (Object.keys(grants).length) {
      await putUserDataGrants(userId, grants)
    }
    if (createForm.tableNames.length) {
      await putUserTableGrants(userId, createForm.tableNames)
    }
    if (createForm.role === 'SCHOOL' && grants.school?.length) {
      await syncSchoolLegacy(userId, grants, createForm.role)
    }
    ElMessage.success('创建成功')
    createVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

function openPatch(row) {
  Object.assign(patchForm, {
    userId: row.id,
    username: row.username,
    displayName: row.displayName || '',
    password: '',
  })
  patchVisible.value = true
}

async function submitPatch() {
  const body = { displayName: patchForm.displayName.trim() || null }
  if (patchForm.password) body.password = patchForm.password
  saving.value = true
  try {
    await patchUser(patchForm.userId, body)
    ElMessage.success('已保存')
    patchVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function openGrants(row) {
  grantsForm.userId = row.id
  grantsForm.role = row.role
  grantsForm.grantRows = []
  grantsForm.tableNames = []
  try {
    const res = await getUserGrants(row.id)
    grantsForm.grantRows = grantRowsFromData(res.dataGrants)
    grantsForm.tableNames = normalizeTableNames(res.tableGrants)
  } catch {
    if (row.role === 'SCHOOL' && row.boundSchools?.length) {
      grantsForm.grantRows = [{
        dimensionCode: 'school',
        valuesText: row.boundSchools.map((s) => s.schId).join(', '),
      }]
    } else {
      grantsForm.grantRows = []
    }
  }
  grantsVisible.value = true
}

async function submitGrants() {
  const grants = buildGrantsPayload(grantsForm.grantRows)
  if (grantsForm.role === 'SCHOOL' && !grants.school?.length) {
    ElMessage.warning('渠道账户至少配置 school 维度的一个值')
    return
  }
  saving.value = true
  try {
    await putUserDataGrants(grantsForm.userId, grants)
    await putUserTableGrants(grantsForm.userId, grantsForm.tableNames)
    await syncSchoolLegacy(grantsForm.userId, grants, grantsForm.role)
    ElMessage.success('数据授权已更新')
    grantsVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function toggleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  const action = next === 0 ? '禁用' : '启用'
  await ElMessageBox.confirm(`确定${action}用户「${row.username}」？`, '确认', { type: 'warning' })
  await patchUser(row.id, { status: next })
  ElMessage.success(`已${action}`)
  await loadList()
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
  align-items: center;
}
.main {
  max-width: 1100px;
  margin: 24px auto;
  padding: 0 16px;
}
.muted {
  color: #909399;
  font-size: 12px;
}
.hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
  line-height: 1.5;
}
.grant-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.grant-block {
  width: 100%;
}
</style>
