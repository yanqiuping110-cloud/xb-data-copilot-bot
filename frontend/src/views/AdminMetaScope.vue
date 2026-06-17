<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · 数据范围</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <MetaAdminNav />
      <el-card>
        <template #header>
          <div class="card-head">
            <span>范围维度</span>
            <el-button type="primary" size="small" @click="openCreateDim">注册维度</el-button>
          </div>
        </template>
        <p class="hint">
          维度 code 为逻辑标识（如 school、region），与物理列名无关；在「表管理」中为每张表配置维度绑列。
        </p>
        <el-table v-loading="dimLoading" :data="dimensions" border>
          <el-table-column prop="code" label="code" min-width="120" />
          <el-table-column prop="display_name" label="展示名" min-width="140" />
          <el-table-column label="值类型" width="90">
            <template #default="{ row }">{{ row.value_type === 'string' ? '字符串' : '整数' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
                {{ row.status === 1 ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card style="margin-top: 16px">
        <template #header>
          <div class="card-head">
            <span>敏感列 deny</span>
            <el-button type="primary" size="small" @click="openCreateDeny">新增规则</el-button>
          </div>
        </template>
        <p class="hint">命中 deny 列的 SELECT 将被 SQL 网关拒绝（COLUMN_DENIED）。userId 为空表示全局规则。</p>
        <el-table v-loading="denyLoading" :data="denyRules" border>
          <el-table-column prop="tableName" label="表名" min-width="160" />
          <el-table-column prop="columnName" label="列名" min-width="120" />
          <el-table-column label="范围" width="100">
            <template #default="{ row }">{{ row.userId ? `用户 ${row.userId}` : '全局' }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="说明" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dimVisible" title="注册范围维度" width="480px" destroy-on-close>
      <el-form :model="dimForm" label-width="88px">
        <el-form-item label="code" required>
          <el-input v-model="dimForm.code" placeholder="如 school、region、channel" />
        </el-form-item>
        <el-form-item label="展示名" required>
          <el-input v-model="dimForm.displayName" placeholder="如 学校、地区、渠道" />
        </el-form-item>
        <el-form-item label="值类型">
          <el-select v-model="dimForm.valueType" style="width: 100%">
            <el-option label="整数 (int)" value="int" />
            <el-option label="字符串 (string)" value="string" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dimVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDim">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="denyVisible" title="新增列 deny" width="480px" destroy-on-close>
      <el-form :model="denyForm" label-width="88px">
        <el-form-item label="表名" required>
          <el-input v-model="denyForm.tableName" placeholder="物理表名" />
        </el-form-item>
        <el-form-item label="列名" required>
          <el-input v-model="denyForm.columnName" />
        </el-form-item>
        <el-form-item label="用户 ID">
          <el-input v-model="denyForm.userId" placeholder="留空=全局" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="denyForm.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="denyVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDeny">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 范围维度注册 + 敏感列 deny（DataScope 配置） */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import { fetchMe } from '../api/auth'
import {
  addColumnDeny,
  createScopeDimension,
  listColumnDeny,
  listScopeDimensions,
} from '../api/scope'

const router = useRouter()
const dimLoading = ref(false)
const denyLoading = ref(false)
const saving = ref(false)
const dimensions = ref([])
const denyRules = ref([])

const dimVisible = ref(false)
const dimForm = reactive({
  code: '',
  displayName: '',
  valueType: 'int',
})

const denyVisible = ref(false)
const denyForm = reactive({
  tableName: '',
  columnName: '',
  userId: '',
  reason: '',
})

onMounted(async () => {
  if (!(await guardAdmin())) return
  await Promise.all([loadDimensions(), loadDenyRules()])
})

async function guardAdmin() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可管理数据范围')
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

async function loadDimensions() {
  dimLoading.value = true
  try {
    const res = await listScopeDimensions()
    dimensions.value = res.items || []
  } finally {
    dimLoading.value = false
  }
}

async function loadDenyRules() {
  denyLoading.value = true
  try {
    const res = await listColumnDeny()
    denyRules.value = res.items || []
  } finally {
    denyLoading.value = false
  }
}

function openCreateDim() {
  Object.assign(dimForm, { code: '', displayName: '', valueType: 'int' })
  dimVisible.value = true
}

async function submitDim() {
  const code = dimForm.code.trim()
  const displayName = dimForm.displayName.trim()
  if (!code || !displayName) {
    ElMessage.warning('请填写 code 与展示名')
    return
  }
  saving.value = true
  try {
    await createScopeDimension({
      code,
      display_name: displayName,
      value_type: dimForm.valueType,
      status: 1,
    })
    ElMessage.success('维度已注册')
    dimVisible.value = false
    await loadDimensions()
  } finally {
    saving.value = false
  }
}

function openCreateDeny() {
  Object.assign(denyForm, { tableName: '', columnName: '', userId: '', reason: '' })
  denyVisible.value = true
}

async function submitDeny() {
  if (!denyForm.tableName.trim() || !denyForm.columnName.trim()) {
    ElMessage.warning('请填写表名与列名')
    return
  }
  saving.value = true
  try {
    await addColumnDeny({
      tableName: denyForm.tableName.trim(),
      columnName: denyForm.columnName.trim(),
      userId: denyForm.userId.trim() ? Number(denyForm.userId) : null,
      reason: denyForm.reason.trim() || null,
    })
    ElMessage.success('已添加 deny 规则')
    denyVisible.value = false
    await loadDenyRules()
  } finally {
    saving.value = false
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
  max-width: 1000px;
  margin: 24px auto;
  padding: 0 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}
</style>
