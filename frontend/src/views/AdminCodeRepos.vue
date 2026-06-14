<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · Git 仓库</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-button type="primary" @click="openCreate">新增仓库</el-button>
          <el-button :loading="rebuilding" @click="onRebuildIndex">重建代码 ES 索引</el-button>
        </div>

        <el-table v-loading="loading" :data="repos" border style="margin-top: 16px">
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column label="来源" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatSource(row) }}
            </template>
          </el-table-column>
          <el-table-column prop="branch" label="分支" width="100">
            <template #default="{ row }">
              {{ isLocalRow(row) ? '—' : row.branch }}
            </template>
          </el-table-column>
          <el-table-column label="同步状态" width="100">
            <template #default="{ row }">
              <el-tag :type="syncTagType(row.syncStatus)" size="small">{{ row.syncStatus }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="syncMessage" label="同步消息" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.syncMessage || (row.syncStatus === 'pending' ? '尚未同步，请点击「同步」' : '—') }}
            </template>
          </el-table-column>
          <el-table-column label="最近同步" width="160">
            <template #default="{ row }">{{ formatTime(row.lastSyncAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :loading="syncingId === row.id" @click="onSync(row)">
                同步
              </el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑仓库' : '新增仓库'" width="600px" destroy-on-close>
      <el-form :model="form" label-width="120px">
        <el-form-item label="导入方式">
          <el-radio-group v-model="form.sourceMode">
            <el-radio value="local">本地目录（网页下载后导入）</el-radio>
            <el-radio value="git">Git 远程拉取</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="展示名"><el-input v-model="form.name" placeholder="如 xiaoben-mini-mobile" /></el-form-item>

        <template v-if="form.sourceMode === 'local'">
          <el-form-item label="项目目录" required>
            <el-input
              v-model="form.localPath"
              placeholder="如 D:\downloads\xiaoben-mini-mobile 或 C:\Users\...\project"
            />
          </el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="先在 GitLab 网页下载 ZIP 并解压，再把解压后的文件夹绝对路径填到上面。无需 Git Token。"
            style="margin-bottom: 16px"
          />
        </template>

        <template v-else>
          <el-form-item label="Git 地址"><el-input v-model="form.repoUrl" placeholder="https:// 或 http://" /></el-form-item>
          <el-form-item label="分支"><el-input v-model="form.branch" /></el-form-item>
          <el-form-item label="凭证 env 变量名">
            <el-input v-model="form.authSecretRef" placeholder="GIT_TOKEN（填 .env 变量名，不是 token 本身）" />
          </el-form-item>
        </template>

        <el-form-item label="包含路径 JSON">
          <el-input v-model="form.includePathsJson" type="textarea" :rows="2" placeholder='["**/*.java","**/*Mapper.xml"]' />
        </el-form-item>
        <el-form-item label="排除路径 JSON">
          <el-input v-model="form.excludePathsJson" type="textarea" :rows="2" placeholder='["**/test/**"]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 超管：Git 仓库配置、同步、代码 ES 索引重建（第 11 周） */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMe } from '../api/auth'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import {
  createCodeRepo,
  deleteCodeRepo,
  fetchCodeRepos,
  rebuildCodeIndex,
  syncCodeRepo,
  updateCodeRepo,
} from '../api/codeRepos'

const LOCAL_REPO_URL = 'local://import'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const syncingId = ref(null)
const repos = ref([])
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  sourceMode: 'local',
  name: '',
  repoUrl: '',
  branch: 'main',
  authSecretRef: '',
  includePathsJson: '["**/*.java","**/*Mapper.xml"]',
  excludePathsJson: '["**/test/**","**/target/**"]',
  localPath: '',
})

function isLocalRow(row) {
  return row.repoUrl?.startsWith('local://') || (!!row.localPath && !row.repoUrl?.startsWith('http'))
}

function formatSource(row) {
  if (isLocalRow(row)) {
    return row.localPath ? `本地: ${row.localPath}` : '本地目录导入'
  }
  return row.repoUrl || '—'
}

function formatTime(iso) {
  return iso ? iso.replace('T', ' ').slice(0, 19) : '—'
}

function syncTagType(status) {
  if (status === 'ok') return 'success'
  if (status === 'fail') return 'danger'
  if (status === 'syncing') return 'warning'
  return 'info'
}

function buildPayload() {
  if (form.sourceMode === 'local') {
    if (!form.localPath?.trim()) {
      throw new Error('请填写项目目录绝对路径')
    }
    return {
      name: form.name,
      repoUrl: LOCAL_REPO_URL,
      branch: 'main',
      authSecretRef: '',
      includePathsJson: form.includePathsJson,
      excludePathsJson: form.excludePathsJson,
      localPath: form.localPath.trim(),
    }
  }
  return {
    name: form.name,
    repoUrl: form.repoUrl,
    branch: form.branch,
    authSecretRef: form.authSecretRef,
    includePathsJson: form.includePathsJson,
    excludePathsJson: form.excludePathsJson,
    localPath: form.localPath || '',
  }
}

async function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}

async function loadRepos() {
  loading.value = true
  try {
    const res = await fetchCodeRepos()
    repos.value = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  Object.assign(form, {
    sourceMode: 'local',
    name: '',
    repoUrl: '',
    branch: 'main',
    authSecretRef: '',
    includePathsJson: '["**/*.java","**/*Mapper.xml"]',
    excludePathsJson: '["**/test/**","**/target/**"]',
    localPath: '',
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  const local = isLocalRow(row)
  Object.assign(form, {
    sourceMode: local ? 'local' : 'git',
    name: row.name,
    repoUrl: local ? '' : row.repoUrl,
    branch: row.branch || 'main',
    authSecretRef: row.authSecretRef || '',
    includePathsJson: row.includePathsJson || '',
    excludePathsJson: row.excludePathsJson || '',
    localPath: row.localPath || '',
  })
  dialogVisible.value = true
}

async function submitForm() {
  saving.value = true
  try {
    const payload = buildPayload()
    if (editId.value) {
      await updateCodeRepo(editId.value, payload)
      ElMessage.success('已更新')
      dialogVisible.value = false
      await loadRepos()
    } else {
      const created = await createCodeRepo(payload)
      ElMessage.success('已创建，正在扫描导入…')
      dialogVisible.value = false
      await loadRepos()
      await onSync(created)
    }
  } catch (e) {
    ElMessage.error(e?.message || e?.response?.data?.error?.message || e?.error || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onSync(row) {
  syncingId.value = row.id
  try {
    const res = await syncCodeRepo(row.id)
    if (res.ok) {
      ElMessage.success(res.message || '同步成功')
    } else {
      ElMessage.error(res.error || '同步失败')
    }
    await loadRepos()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '同步失败')
  } finally {
    syncingId.value = null
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`删除仓库「${row.name}」？`, '确认')
  try {
    await deleteCodeRepo(row.id)
    ElMessage.success('已删除')
    await loadRepos()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '删除失败')
  }
}

async function onRebuildIndex() {
  rebuilding.value = true
  try {
    const res = await rebuildCodeIndex()
    ElMessage.success(`已索引 ${res.codeArtifacts} 条 artifact`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '重建失败')
  } finally {
    rebuilding.value = false
  }
}

onMounted(async () => {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可访问 Git 仓库管理')
      router.replace('/admin/meta/tables')
      return
    }
    localStorage.setItem('userRole', res.user.role)
  } catch {
    router.push('/login')
    return
  }
  await loadRepos()
})
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
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
}
.title {
  font-size: 18px;
  font-weight: 600;
}
.main {
  max-width: 1200px;
  margin: 24px auto;
  padding: 0 16px;
}
.toolbar {
  display: flex;
  gap: 12px;
}
</style>
