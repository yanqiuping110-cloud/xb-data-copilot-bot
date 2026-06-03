<template>
  <div class="layout">
    <header class="header">
      <span class="title">用户管理</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <el-card>
        <div class="toolbar">
          <el-select v-model="roleFilter" placeholder="全部角色" clearable style="width: 140px" @change="loadList">
            <el-option label="运营" value="OPERATOR" />
            <el-option label="学校" value="SCHOOL" />
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
          <el-table-column label="绑定学校" min-width="200">
            <template #default="{ row }">
              <span v-if="row.role !== 'SCHOOL'">—</span>
              <span v-else>
                {{
                  (row.boundSchools || [])
                    .map((s) => (s.schName ? `${s.schName}(${s.schId})` : s.schId))
                    .join('、') || '—'
                }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <template v-if="row.role !== 'ADMIN'">
                <el-button link type="primary" @click="openPatch(row)">编辑</el-button>
                <el-button
                  v-if="row.role === 'SCHOOL'"
                  link
                  type="primary"
                  @click="openSchools(row)"
                >
                  学校绑定
                </el-button>
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
    <el-dialog v-model="createVisible" title="新建用户" width="480px" destroy-on-close>
      <el-form :model="createForm" label-width="88px">
        <el-form-item label="用户名" required>
          <el-input v-model="createForm.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="createForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="运营" value="OPERATOR" />
            <el-option label="学校" value="SCHOOL" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="createForm.displayName" />
        </el-form-item>
        <el-form-item v-if="createForm.role === 'SCHOOL'" label="学校 ID" required>
          <el-input
            v-model="createForm.schIdsText"
            placeholder="多个用英文逗号分隔，如 1140,1220"
          />
        </el-form-item>
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

    <!-- 学校绑定 -->
    <el-dialog v-model="schoolsVisible" title="学校绑定" width="480px" destroy-on-close>
      <p class="hint">全量覆盖绑定，至少保留一所学校。</p>
      <el-form label-width="88px">
        <el-form-item label="学校 ID">
          <el-input
            v-model="schoolsForm.schIdsText"
            placeholder="多个用英文逗号分隔，如 1140,1220"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="schoolsVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitSchools">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 超管用户管理页：列表、创建、禁用/启用、学校绑定 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import { createUser, listUsers, patchUser, replaceSchools } from '../api/admin'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const roleFilter = ref(null)

const createVisible = ref(false)
const createForm = reactive({
  username: '',
  password: '',
  role: 'OPERATOR',
  displayName: '',
  schIdsText: '',
})

const patchVisible = ref(false)
const patchForm = reactive({
  userId: null,
  username: '',
  displayName: '',
  password: '',
})

const schoolsVisible = ref(false)
const schoolsForm = reactive({
  userId: null,
  schIdsText: '',
})

function roleLabel(role) {
  return { ADMIN: '超管', OPERATOR: '运营', SCHOOL: '学校' }[role] || role
}

function parseSchIds(text) {
  return text
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => !Number.isNaN(n) && n > 0)
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
    await loadList()
  } catch {
    router.push('/login')
  }
})

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, pageSize: pageSize.value }
    if (roleFilter.value) params.role = roleFilter.value
    const res = await listUsers(params)
    users.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(createForm, {
    username: '',
    password: '',
    role: 'OPERATOR',
    displayName: '',
    schIdsText: '',
  })
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.username.trim() || !createForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  const body = {
    username: createForm.username.trim(),
    password: createForm.password,
    role: createForm.role,
    displayName: createForm.displayName.trim() || undefined,
  }
  if (createForm.role === 'SCHOOL') {
    const schIds = parseSchIds(createForm.schIdsText)
    if (!schIds.length) {
      ElMessage.warning('学校账户至少绑定一个学校 ID')
      return
    }
    body.schIds = schIds
  }
  saving.value = true
  try {
    await createUser(body)
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

function openSchools(row) {
  schoolsForm.userId = row.id
  schoolsForm.schIdsText = (row.boundSchools || []).map((s) => s.schId).join(',')
  schoolsVisible.value = true
}

async function submitSchools() {
  const schIds = parseSchIds(schoolsForm.schIdsText)
  if (!schIds.length) {
    ElMessage.warning('至少绑定一所学校')
    return
  }
  saving.value = true
  try {
    await replaceSchools(schoolsForm.userId, { schIds })
    ElMessage.success('学校绑定已更新')
    schoolsVisible.value = false
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
}
</style>
