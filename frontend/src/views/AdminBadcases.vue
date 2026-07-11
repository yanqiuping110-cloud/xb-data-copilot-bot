<template>
  <div class="layout">
    <header class="header">
      <span class="title">Badcase 管理</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-card>
        <p class="hint">点踩或标记为 badcase 的问数记录；可填写修正 SQL 供后续补 meta 或 L1 样例。</p>
        <el-table v-loading="loading" :data="items" border style="margin-top: 12px">
          <el-table-column prop="createdAt" label="时间" width="160">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="question" label="问句" min-width="180" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="80" />
          <el-table-column label="反馈" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.userFeedback === 'down'" type="danger" size="small">点踩</el-tag>
              <el-tag v-else-if="row.isBadcase" type="warning" size="small">badcase</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="SQL" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.finalSql || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="380" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openCorrect(row)">修正 SQL</el-button>
              <el-button link type="primary" :loading="draftingId === row.traceId" @click="onDraftL1(row)">
                转 L1 草稿
              </el-button>
              <el-button link type="success" @click="onPromoteGlossary(row)">抽术语</el-button>
              <el-button link type="primary" @click="goAddExample(row)">手动补样例</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" title="人工修正 SQL" width="640px" destroy-on-close>
      <p class="q-preview">{{ currentRow?.question }}</p>
      <el-input v-model="correctedSql" type="textarea" :rows="6" placeholder="填写期望 SQL" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCorrect">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import { fetchMe } from '../api/auth'
import { draftSqlExampleFromBadcase, listBadcases, postFeedback } from '../api/feedback'
import { promoteGlossaryFromBadcase } from '../api/adminOps'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const items = ref([])
const dialogVisible = ref(false)
const currentRow = ref(null)
const correctedSql = ref('')
const draftingId = ref(null)

function formatTime(iso) {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 19)
}

onMounted(async () => {
  if (!(await guardMetaManager())) return
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

async function loadList() {
  loading.value = true
  try {
    const res = await listBadcases({ offset: 0, limit: 100 })
    items.value = res.items
  } finally {
    loading.value = false
  }
}

function openCorrect(row) {
  currentRow.value = row
  correctedSql.value = row.humanCorrectedSql || row.finalSql || ''
  dialogVisible.value = true
}

async function submitCorrect() {
  if (!currentRow.value) return
  saving.value = true
  try {
    await postFeedback({
      traceId: currentRow.value.traceId,
      isBadcase: true,
      correctedSql: correctedSql.value.trim() || null,
    })
    ElMessage.success('已保存修正 SQL')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function onDraftL1(row) {
  const sql = (row.humanCorrectedSql || row.finalSql || '').trim()
  if (!sql) {
    ElMessage.warning('请先填写修正 SQL 或确保原问数有 SQL')
    openCorrect(row)
    return
  }
  draftingId.value = row.traceId
  try {
    const res = await draftSqlExampleFromBadcase(row.traceId)
    ElMessage.success(`已创建 L1 草稿 #${res.id}，请在样例页审核发布`)
    router.push({ path: '/admin/meta/sql-examples', query: { editId: res.id } })
  } finally {
    draftingId.value = null
  }
}

function goAddExample(row) {
  sessionStorage.setItem(
    'badcasePrefill',
    JSON.stringify({
      questionPattern: row.question,
      sqlText: row.humanCorrectedSql || row.finalSql || '',
    }),
  )
  router.push('/admin/meta/sql-examples')
}

async function onPromoteGlossary(row) {
  try {
    const res = await promoteGlossaryFromBadcase(row.traceId)
    ElMessage.success(`已生成 ${res.items.length} 条术语草稿，请到运营中心审核发布`)
    router.push('/admin/meta/ops')
  } catch {
    /* request 拦截器已提示 */
  }
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
.hint { margin: 0; color: #909399; font-size: 13px; }
.q-preview { margin: 0 0 12px; font-weight: 500; }
</style>
