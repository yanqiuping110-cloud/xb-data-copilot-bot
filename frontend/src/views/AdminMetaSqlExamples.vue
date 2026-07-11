<template>
  <div class="layout">
    <header class="header">
      <span class="title">元数据 · L1 样例 SQL</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <MetaAdminNav />
      <el-card>
        <div class="toolbar">
          <el-button type="primary" @click="openCreate">新增样例</el-button>
        </div>
        <el-table v-loading="loading" :data="examples" border style="margin-top: 16px">
          <el-table-column prop="degradePriority" label="优先级" width="80" />
          <el-table-column label="审核" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.reviewStatus === 0 || row.metaJson?.draft" type="warning" size="small">草稿</el-tag>
              <el-tag v-else type="success" size="small">已发布</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="questionPattern" label="问句模式" min-width="180" show-overflow-tooltip />
          <el-table-column prop="roleScope" label="角色" width="90">
            <template #default="{ row }">{{ row.roleScope || '全部' }}</template>
          </el-table-column>
          <el-table-column label="SQL" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.sqlText }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button
                v-if="row.reviewStatus === 0 || row.metaJson?.draft"
                link
                type="success"
                @click="onPublish(row)"
              >
                发布
              </el-button>
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑 L1 样例' : '新增 L1 样例'" width="720px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="问句模式" required>
          <el-input v-model="form.questionPattern" placeholder="示例问句或描述" />
        </el-form-item>
        <el-form-item label="SQL" required>
          <el-input v-model="form.sqlText" type="textarea" :rows="4" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="角色范围">
              <el-select v-model="form.roleScope" clearable placeholder="全部" style="width: 100%">
                <el-option label="全部" :value="null" />
                <el-option label="渠道" value="SCHOOL" />
                <el-option label="运营" value="OPERATOR" />
                <el-option label="超管" value="ADMIN" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="L1 优先级">
              <el-input-number v-model="form.degradePriority" :min="1" :max="999" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="匹配规则 JSON">
          <el-input
            v-model="form.metaJsonText"
            type="textarea"
            :rows="6"
            placeholder='{"matchAll":["参与人数"],"answerTemplate":"…","tables":["your_fact_table"]}'
          />
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import { fetchMe } from '../api/auth'
import { createSqlExample, deleteSqlExample, listSqlExamples, updateSqlExample } from '../api/meta'
import { publishL1Example } from '../api/adminOps'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const examples = ref([])
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  questionPattern: '',
  sqlText: '',
  roleScope: null,
  degradePriority: 100,
  metaJsonText: '',
})

onMounted(async () => {
  if (!(await guardMetaManager())) return
  await loadList()
  const editFromQuery = route.query.editId
  if (editFromQuery) {
    const row = examples.value.find((e) => String(e.id) === String(editFromQuery))
    if (row) openEdit(row)
  }
  const prefill = sessionStorage.getItem('badcasePrefill')
  if (prefill) {
    sessionStorage.removeItem('badcasePrefill')
    try {
      const data = JSON.parse(prefill)
      openCreate()
      form.questionPattern = data.questionPattern || ''
      form.sqlText = data.sqlText || ''
    } catch {
      /* ignore */
    }
  }
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
    examples.value = await listSqlExamples()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  Object.assign(form, {
    questionPattern: '',
    sqlText: '',
    roleScope: null,
    degradePriority: 100,
    metaJsonText: '{\n  "matchAll": [],\n  "answerTemplate": ""\n}',
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  Object.assign(form, {
    questionPattern: row.questionPattern,
    sqlText: row.sqlText,
    roleScope: row.roleScope,
    degradePriority: row.degradePriority,
    metaJsonText: row.metaJson ? JSON.stringify(row.metaJson, null, 2) : '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.questionPattern.trim() || !form.sqlText.trim()) {
    ElMessage.warning('请填写问句与 SQL')
    return
  }
  let metaJson = null
  if (form.metaJsonText.trim()) {
    try {
      metaJson = JSON.parse(form.metaJsonText)
    } catch {
      ElMessage.warning('匹配规则 JSON 格式不正确')
      return
    }
  }
  const body = {
    questionPattern: form.questionPattern.trim(),
    sqlText: form.sqlText.trim(),
    roleScope: form.roleScope,
    degradePriority: form.degradePriority,
    metaJson,
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateSqlExample(editId.value, body)
    } else {
      await createSqlExample(body)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function onPublish(row) {
  await publishL1Example(row.id)
  ElMessage.success('L1 样例已发布')
  await loadList()
}

async function onDelete(row) {
  await ElMessageBox.confirm('确定删除该 L1 样例？', '确认', { type: 'warning' })
  await deleteSqlExample(row.id)
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
</style>
