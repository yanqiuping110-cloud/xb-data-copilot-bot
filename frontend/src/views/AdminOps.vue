<template>
  <div class="layout">
    <header class="header">
      <span class="title">运营中心</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-row :gutter="16" class="stats-row">
        <el-col :span="4"><el-statistic title="7日 Badcase" :value="stats.badcaseCount7d" /></el-col>
        <el-col :span="4"><el-statistic title="30日术语发布" :value="stats.glossaryPublished30d" /></el-col>
        <el-col :span="4"><el-statistic title="30日 L1 发布" :value="stats.l1Published30d" /></el-col>
        <el-col :span="4"><el-statistic title="L1 草稿" :value="stats.l1DraftCount" /></el-col>
        <el-col :span="4"><el-statistic title="术语草稿" :value="stats.glossaryDraftCount" /></el-col>
      </el-row>

      <el-card style="margin-top: 16px">
        <div class="toolbar">
          <span class="section-title">术语库</span>
          <el-button type="primary" @click="openGlossaryCreate">新增术语</el-button>
        </div>
        <el-table v-loading="loading" :data="glossaryItems" border style="margin-top: 12px">
          <el-table-column prop="term" label="业务术语" width="140" />
          <el-table-column prop="canonicalName" label="标准表述" min-width="160" />
          <el-table-column prop="definition" label="口径说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.status === 1" type="success" size="small">已发布</el-tag>
              <el-tag v-else-if="row.status === 2" type="info" size="small">停用</el-tag>
              <el-tag v-else type="warning" size="small">草稿</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openGlossaryEdit(row)">编辑</el-button>
              <el-button v-if="row.status === 0" link type="success" @click="publishGlossary(row)">发布</el-button>
              <el-button link type="danger" @click="onDeleteGlossary(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑术语' : '新增术语'" width="560px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="业务术语" required>
          <el-input v-model="form.term" />
        </el-form-item>
        <el-form-item label="标准表述" required>
          <el-input v-model="form.canonicalName" />
        </el-form-item>
        <el-form-item label="口径说明">
          <el-input v-model="form.definition" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="草稿" :value="0" />
            <el-option label="已发布" :value="1" />
            <el-option label="停用" :value="2" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitGlossary">保存</el-button>
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
  createGlossary,
  deleteGlossary,
  fetchOpsStats,
  listGlossary,
  updateGlossary,
} from '../api/adminOps'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const glossaryItems = ref([])
const dialogVisible = ref(false)
const editId = ref(null)
const stats = reactive({
  badcaseCount7d: 0,
  glossaryPublished30d: 0,
  l1Published30d: 0,
  l1DraftCount: 0,
  glossaryDraftCount: 0,
})
const form = reactive({
  term: '',
  canonicalName: '',
  definition: '',
  status: 0,
})

onMounted(async () => {
  if (!(await guardMetaManager())) return
  await refresh()
})

async function guardMetaManager() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN' && res.user.role !== 'OPERATOR') {
      router.replace('/')
      return false
    }
    return true
  } catch {
    router.push('/login')
    return false
  }
}

async function refresh() {
  loading.value = true
  try {
    const [s, g] = await Promise.all([fetchOpsStats(), listGlossary({ limit: 200 })])
    Object.assign(stats, s)
    glossaryItems.value = g.items
  } finally {
    loading.value = false
  }
}

function openGlossaryCreate() {
  editId.value = null
  form.term = ''
  form.canonicalName = ''
  form.definition = ''
  form.status = 0
  dialogVisible.value = true
}

function openGlossaryEdit(row) {
  editId.value = row.id
  form.term = row.term
  form.canonicalName = row.canonicalName
  form.definition = row.definition || ''
  form.status = row.status
  dialogVisible.value = true
}

async function submitGlossary() {
  if (!form.term.trim() || !form.canonicalName.trim()) {
    ElMessage.warning('请填写术语与标准表述')
    return
  }
  saving.value = true
  try {
    const payload = {
      term: form.term.trim(),
      canonicalName: form.canonicalName.trim(),
      definition: form.definition.trim() || null,
      status: form.status,
    }
    if (editId.value) {
      await updateGlossary(editId.value, payload)
    } else {
      await createGlossary(payload)
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    await refresh()
  } finally {
    saving.value = false
  }
}

async function publishGlossary(row) {
  await updateGlossary(row.id, { status: 1 })
  ElMessage.success('术语已发布')
  await refresh()
}

async function onDeleteGlossary(row) {
  await ElMessageBox.confirm(`删除术语「${row.term}」？`, '确认')
  await deleteGlossary(row.id)
  ElMessage.success('已删除')
  await refresh()
}

function logout() {
  localStorage.removeItem('accessToken')
  router.push('/login')
}
</script>

<style scoped>
.layout { min-height: 100vh; background: #f5f7fa; }
.header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; background: #fff; border-bottom: 1px solid #ebeef5;
}
.title { font-size: 18px; font-weight: 600; }
.main { max-width: 1200px; margin: 0 auto; padding: 16px 24px 48px; }
.stats-row { margin-top: 8px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-weight: 600; }
</style>
