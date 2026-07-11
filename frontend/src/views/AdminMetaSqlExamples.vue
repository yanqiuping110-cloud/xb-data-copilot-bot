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
          <el-button :loading="rebuilding" @click="onRebuildIndex">重建知识库索引</el-button>
        </div>
        <p class="hint">
          L1 样例通过知识库召回（问句模式 + 详细描述），由 LLM 结合 STAR 精选后注入规划/SQL。匹配规则与优先级字段已弃用。
        </p>
        <el-table v-loading="loading" :data="examples" border style="margin-top: 16px">
          <el-table-column label="审核" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.reviewStatus === 0 || row.metaJson?.draft" type="warning" size="small">草稿</el-tag>
              <el-tag v-else type="success" size="small">已发布</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="questionPattern" label="问句模式" min-width="160" show-overflow-tooltip />
          <el-table-column prop="description" label="详细描述" min-width="180" show-overflow-tooltip />
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
          <el-input v-model="form.questionPattern" placeholder="示例问句或典型问法" />
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="业务口径、适用场景、涉及表/指标说明（用于知识库召回）"
          />
        </el-form-item>
        <el-form-item label="SQL 样例" required>
          <el-input v-model="form.sqlText" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item label="角色范围">
          <el-select v-model="form.roleScope" clearable placeholder="全部" style="width: 100%">
            <el-option label="全部" :value="null" />
            <el-option label="渠道" value="SCHOOL" />
            <el-option label="运营" value="OPERATOR" />
            <el-option label="超管" value="ADMIN" />
          </el-select>
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
import { createSqlExample, deleteSqlExample, listSqlExamples, rebuildMetaIndex, updateSqlExample } from '../api/meta'
import { publishL1Example } from '../api/adminOps'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const examples = ref([])
const dialogVisible = ref(false)
const editId = ref(null)
const form = reactive({
  questionPattern: '',
  description: '',
  sqlText: '',
  roleScope: null,
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
      form.description = data.description || ''
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
    description: '',
    sqlText: '',
    roleScope: null,
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  Object.assign(form, {
    questionPattern: row.questionPattern,
    description: row.description || '',
    sqlText: row.sqlText,
    roleScope: row.roleScope,
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.questionPattern.trim() || !form.sqlText.trim()) {
    ElMessage.warning('请填写问句模式与 SQL 样例')
    return
  }
  const body = {
    questionPattern: form.questionPattern.trim(),
    description: form.description.trim() || null,
    sqlText: form.sqlText.trim(),
    roleScope: form.roleScope,
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
  try {
    await ElMessageBox.confirm('样例已发布，是否立即重建知识库索引以使召回生效？', '重建知识库索引', {
      confirmButtonText: '重建',
      cancelButtonText: '稍后',
      type: 'info',
    })
    await doRebuild()
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      /* 用户取消确认框，或 rebuild 失败（doRebuild 内已有提示） */
    }
  }
}

async function doRebuild() {
  rebuilding.value = true
  try {
    const res = await rebuildMetaIndex()
    const l1Count = res.sqlExamples ?? 0
    ElMessage.success(
      `索引重建完成：L1 样例 ${l1Count}、字段 ${res.columns}、指标 ${res.metrics}、取值 ${res.fieldValues}`,
    )
  } finally {
    rebuilding.value = false
  }
}

async function onRebuildIndex() {
  await ElMessageBox.confirm(
    '将全量重建表/字段/指标/取值/L1 样例检索索引，需 Embedding 服务可用。继续？',
    '重建知识库索引',
    { type: 'warning' },
  )
  await doRebuild()
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
.hint { margin: 12px 0 0; color: #606266; font-size: 13px; line-height: 1.5; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
