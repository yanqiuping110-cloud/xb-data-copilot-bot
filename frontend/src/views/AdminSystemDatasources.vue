<template>
  <div class="sys-page">
    <header class="sys-header">
      <span class="sys-header__title">系统 · 数据源</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="sys-main">
      <MetaAdminNav />
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="当前默认数据源用于问数 SQL 执行与 Meta「从业务库读取」。切换默认后请确认已注册表在新库中存在。"
        style="margin-bottom: 16px"
      />

      <div class="sys-toolbar">
        <div class="sys-toolbar__left">
          <el-input
            v-model="search"
            class="sys-search"
            clearable
            placeholder="搜索名称 / 主机 / 库"
            :prefix-icon="Search"
          />
          <el-select v-model="typeFilter" clearable placeholder="全部类型" style="width: 150px">
            <el-option
              v-for="t in types"
              :key="t.code"
              :label="t.name"
              :value="t.code"
            />
          </el-select>
        </div>
        <div class="sys-toolbar__right">
          <el-button class="sys-btn-accent" type="primary" @click="openCreate">
            + 新建数据源
          </el-button>
        </div>
      </div>

      <div v-loading="loading">
        <div v-if="filteredItems.length" class="sys-card-grid">
          <DatasourceCard
            v-for="row in filteredItems"
            :key="row.id"
            :item="row"
            :types="types"
            :testing="testingId === row.id"
            @test="onTest"
            @set-default="onSetDefault"
            @edit="openEdit"
            @delete="onDelete"
          />
        </div>
        <div v-else class="sys-empty">
          <p class="sys-empty__title">还没有业务数据源</p>
          <p>新建后设为默认，即可作为当前问数库。</p>
          <el-button class="sys-btn-accent" type="primary" style="margin-top: 16px" @click="openCreate">
            新建数据源
          </el-button>
        </div>
      </div>
    </main>

    <el-dialog
      v-model="dialogVisible"
      :title="editId ? '编辑数据源' : '新建数据源'"
      width="860px"
      destroy-on-close
      top="6vh"
    >
      <el-steps
        v-if="!editId"
        :active="wizardStep"
        align-center
        finish-status="success"
        style="margin-bottom: 18px"
      >
        <el-step title="选择数据源" />
        <el-step title="配置信息" />
        <el-step title="完成" />
      </el-steps>

      <div v-if="!editId" class="sys-wizard">
        <div class="sys-wizard__side">
          <div class="sys-wizard__side-search">
            <el-input v-model="typeQuery" size="small" clearable placeholder="搜索类型" />
          </div>
          <DatasourceTypePicker v-model="form.dbType" :types="types" :query="typeQuery" />
        </div>
        <div class="sys-wizard__main">
          <template v-if="wizardStep <= 1">
            <h3 class="sys-wizard__heading">{{ selectedType?.name || '数据源' }}</h3>
            <p class="sys-wizard__sub">
              <template v-if="selectedType?.versionHint">
                支持版本: {{ selectedType.versionHint }}
              </template>
              <template v-else>请从左侧选择类型</template>
            </p>
            <el-form :model="form" label-width="120px">
              <el-form-item label="名称" required>
                <el-input v-model="form.name" placeholder="如 生产制造销售数据" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="2"
                  maxlength="200"
                  show-word-limit
                  placeholder="可选"
                />
              </el-form-item>
              <template v-if="form.dbType === 'excel'">
                <el-form-item label="文件路径" required>
                  <el-input
                    v-model="form.databaseName"
                    placeholder="如 data/demo.xlsx 或绝对路径"
                  />
                </el-form-item>
              </template>
              <template v-else>
                <el-form-item label="主机名/IP地址" required>
                  <el-input v-model="form.host" placeholder="127.0.0.1" />
                </el-form-item>
                <el-form-item label="端口" required>
                  <el-input-number v-model="form.port" :min="1" :max="65535" />
                </el-form-item>
                <el-form-item label="用户名" required>
                  <el-input v-model="form.username" />
                </el-form-item>
                <el-form-item label="密码">
                  <el-input
                    v-model="form.password"
                    type="password"
                    show-password
                    placeholder="只读账号密码"
                    autocomplete="new-password"
                  />
                </el-form-item>
                <el-form-item :label="form.dbType === 'oracle' ? 'Service Name' : '数据库'" required>
                  <el-input v-model="form.databaseName" />
                </el-form-item>
              </template>
            </el-form>
          </template>
          <template v-else>
            <h3 class="sys-wizard__heading">完成配置</h3>
            <p class="sys-wizard__sub">
              保存后可在「表管理」注册/刷新结构。选表与语义层仍在 Meta，不在本向导内嵌。
            </p>
            <el-form label-width="140px">
              <el-form-item label="设为当前问数库">
                <el-switch v-model="form.isDefault" />
              </el-form-item>
            </el-form>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              title="连接信息已就绪，点击保存即可。也可先点「校验」确认连通。"
            />
          </template>
        </div>
      </div>

      <el-form v-else :model="form" label-width="120px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="主机" required>
          <el-input v-model="form.host" />
        </el-form-item>
        <el-form-item label="端口" required>
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="库名" required>
          <el-input v-model="form.databaseName" />
        </el-form-item>
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="留空则不修改"
            autocomplete="new-password"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="!editId && wizardStep > 0" @click="wizardStep -= 1">上一步</el-button>
        <el-button :loading="testingDraft" @click="onTestDraft">校验</el-button>
        <el-button
          v-if="!editId && wizardStep < 2"
          class="sys-btn-accent"
          type="primary"
          @click="nextWizard"
        >
          下一步
        </el-button>
        <el-button
          v-else
          class="sys-btn-accent"
          type="primary"
          :loading="saving"
          @click="submit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import DatasourceCard from '../components/system-config/DatasourceCard.vue'
import DatasourceTypePicker from '../components/system-config/DatasourceTypePicker.vue'
import { fetchMe } from '../api/auth'
import {
  createDatasource,
  deleteDatasource,
  listDatasources,
  listDatasourceTypes,
  setDefaultDatasource,
  testDatasourceDraft,
  testDatasourceSaved,
  updateDatasource,
} from '../api/systemConfig'
import { DATASOURCE_TYPES_FALLBACK } from '../constants/datasourceTypes.fallback'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const testingId = ref(null)
const testingDraft = ref(false)
const items = ref([])
const types = ref([...DATASOURCE_TYPES_FALLBACK])
const search = ref('')
const typeFilter = ref(null)
const typeQuery = ref('')
const dialogVisible = ref(false)
const editId = ref(null)
const wizardStep = ref(1)
const form = reactive({
  name: '',
  description: '',
  dbType: 'mysql',
  host: '127.0.0.1',
  port: 3306,
  databaseName: '',
  username: '',
  password: '',
  isDefault: false,
})

const selectedType = computed(() => types.value.find((t) => t.code === form.dbType))

const filteredItems = computed(() => {
  let list = items.value
  if (typeFilter.value) list = list.filter((d) => d.dbType === typeFilter.value)
  const key = search.value.trim().toLowerCase()
  if (key) {
    list = list.filter(
      (d) =>
        d.name.toLowerCase().includes(key) ||
        String(d.host || '')
          .toLowerCase()
          .includes(key) ||
        String(d.databaseName || '')
          .toLowerCase()
          .includes(key),
    )
  }
  return list
})

watch(
  () => form.dbType,
  (code) => {
    const t = types.value.find((x) => x.code === code)
    if (t?.defaultPort) form.port = t.defaultPort
  },
)

async function guardAdmin() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可配置业务数据源')
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

async function loadTypes() {
  try {
    const res = await listDatasourceTypes()
    if (res.items?.length) types.value = res.items
  } catch {
    /* fallback */
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await listDatasources()
    items.value = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  wizardStep.value = 1
  typeQuery.value = ''
  Object.assign(form, {
    name: '',
    description: '',
    dbType: 'mysql',
    host: '127.0.0.1',
    port: 3306,
    databaseName: '',
    username: '',
    password: '',
    isDefault: false,
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  wizardStep.value = 1
  Object.assign(form, {
    name: row.name,
    description: '',
    dbType: row.dbType || 'mysql',
    host: row.host,
    port: row.port,
    databaseName: row.databaseName,
    username: row.username,
    password: '',
    isDefault: row.isDefault,
  })
  dialogVisible.value = true
}

function validateFormBasics() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return false
  }
  const t = selectedType.value
  if (!editId.value && (!t || !t.selectable)) {
    ElMessage.warning('请选择当前已支持的数据源类型')
    return false
  }
  if (form.dbType === 'excel') {
    if (!form.databaseName.trim()) {
      ElMessage.warning('请填写 Excel/CSV 文件路径')
      return false
    }
    return true
  }
  if (!form.host.trim() || !form.databaseName.trim() || !form.username.trim()) {
    ElMessage.warning('请填写主机、数据库、用户名')
    return false
  }
  return true
}

function nextWizard() {
  if (wizardStep.value === 1) {
    if (!validateFormBasics()) return
    wizardStep.value = 2
    return
  }
  wizardStep.value += 1
}

async function onTestDraft() {
  if (!validateFormBasics()) return
  testingDraft.value = true
  try {
    const res = await testDatasourceDraft({
      host: form.dbType === 'excel' ? 'local' : form.host.trim(),
      port: form.dbType === 'excel' ? 0 : form.port,
      databaseName: form.databaseName.trim(),
      username: form.dbType === 'excel' ? 'file' : form.username.trim(),
      password: form.password || '',
      dbType: form.dbType,
    })
    if (res.ok) ElMessage.success(res.message || '连通成功')
    else ElMessage.error(res.message || '连通失败')
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '测试失败')
  } finally {
    testingDraft.value = false
  }
}

async function submit() {
  if (!validateFormBasics()) return
  saving.value = true
  try {
    if (editId.value) {
      const payload = {
        name: form.name.trim(),
        host: form.host.trim(),
        port: form.port,
        databaseName: form.databaseName.trim(),
        username: form.username.trim(),
      }
      if (form.password.trim()) payload.password = form.password
      await updateDatasource(editId.value, payload)
    } else {
      await createDatasource({
        name: form.name.trim(),
        dbType: form.dbType,
        host: form.dbType === 'excel' ? 'local' : form.host.trim(),
        port: form.dbType === 'excel' ? 0 : form.port,
        databaseName: form.databaseName.trim(),
        username: form.dbType === 'excel' ? 'file' : form.username.trim(),
        password: form.password || null,
        isDefault: form.isDefault,
        status: 1,
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onTest(row) {
  testingId.value = row.id
  try {
    const res = await testDatasourceSaved(row.id)
    if (res.ok) ElMessage.success(res.message || '连通成功')
    else ElMessage.error(res.message || '连通失败')
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '测试失败')
  } finally {
    testingId.value = null
  }
}

async function onSetDefault(row) {
  await ElMessageBox.confirm(
    `将「${row.name}」设为当前问数库？已注册 Meta 表可能对新库无效，需重新 introspect。`,
    '切换默认数据源',
    { type: 'warning' },
  )
  try {
    await setDefaultDatasource(row.id)
    ElMessage.success('已切换默认业务库')
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '设置失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`删除数据源「${row.name}」？`, '确认', { type: 'warning' })
  try {
    await deleteDatasource(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '删除失败')
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}

onMounted(async () => {
  if (!(await guardAdmin())) return
  await Promise.all([loadTypes(), loadList()])
})
</script>
