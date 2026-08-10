<template>
  <div class="sys-page">
    <header class="sys-header">
      <span class="sys-header__title">系统 · AI 模型配置</span>
      <div class="actions">
        <el-button link type="primary" @click="router.push('/ask')">返回问数</el-button>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="sys-main">
      <MetaAdminNav />

      <div class="sys-toolbar">
        <div class="sys-toolbar__left">
          <el-input
            v-model="search"
            class="sys-search"
            clearable
            placeholder="搜索名称 / 模型"
            :prefix-icon="Search"
          />
          <el-select v-model="roleFilter" clearable placeholder="全部类型" style="width: 140px">
            <el-option label="大语言模型" value="chat" />
            <el-option label="向量模型" value="embedding" />
          </el-select>
          <el-select v-model="providerFilter" clearable placeholder="全部供应商" style="width: 160px">
            <el-option
              v-for="p in providers"
              :key="p.code"
              :label="p.name"
              :value="p.code"
            />
          </el-select>
        </div>
        <div class="sys-toolbar__right">
          <DefaultModelSelect
            role="chat"
            :models="items"
            :providers="providers"
            @select="onSetDefault"
          />
          <DefaultModelSelect
            role="embedding"
            :models="items"
            :providers="providers"
            @select="onSetDefault"
          />
          <el-button class="sys-btn-accent" type="primary" @click="openCreate">
            + 添加模型
          </el-button>
        </div>
      </div>

      <div v-loading="loading">
        <div v-if="filteredItems.length" class="sys-card-grid">
          <LlmModelCard
            v-for="row in filteredItems"
            :key="row.id"
            :model="row"
            :providers="providers"
            :testing="testingId === row.id"
            @test="onTest"
            @set-default="onSetDefault"
            @edit="openEdit"
            @delete="onDelete"
          />
        </div>
        <div v-else class="sys-empty">
          <p class="sys-empty__title">还没有配置模型</p>
          <p>从供应商墙选择 DeepSeek / 百炼 / Ollama 等，添加后即可设为系统默认。</p>
          <el-button class="sys-btn-accent" type="primary" style="margin-top: 16px" @click="openCreate">
            添加第一个模型
          </el-button>
        </div>
      </div>
    </main>

    <el-dialog
      v-model="dialogVisible"
      :title="editId ? '编辑模型' : '添加模型'"
      width="720px"
      destroy-on-close
      class="sys-llm-dialog"
    >
      <el-steps v-if="!editId" :active="wizardStep" align-center finish-status="success" style="margin-bottom: 20px">
        <el-step title="选择供应商" />
        <el-step title="配置参数" />
        <el-step title="测试保存" />
      </el-steps>

      <div v-if="!editId && wizardStep === 0">
        <el-form-item label="模型角色" label-width="90px" style="margin-bottom: 16px">
          <el-radio-group v-model="form.role">
            <el-radio-button value="chat">大语言模型</el-radio-button>
            <el-radio-button value="embedding">向量模型</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <ProviderPicker v-model="form.provider" :providers="providers" :role="form.role" />
      </div>

      <el-form v-else :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如 阿里云百炼-plus" />
        </el-form-item>
        <el-form-item v-if="editId" label="角色">
          <el-tag>{{ form.role === 'embedding' ? '向量模型' : '大语言模型' }}</el-tag>
        </el-form-item>
        <el-form-item label="供应商">
          <el-select v-model="form.provider" style="width: 100%" @change="onProviderChange">
            <el-option
              v-for="p in providersForRole"
              :key="p.code"
              :label="p.name"
              :value="p.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="API Base" required>
          <el-input v-model="form.apiBase" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.apiKey"
            type="password"
            show-password
            :placeholder="editId ? '留空则不修改' : '可选'"
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="基础模型" required>
          <el-autocomplete
            v-model="form.modelName"
            :fetch-suggestions="suggestModels"
            placeholder="如 qwen-plus"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="超时(秒)">
          <el-input-number v-model="form.timeoutSec" :min="5" :max="600" />
        </el-form-item>
        <el-form-item v-if="form.role === 'chat'" label="温度">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <el-form-item v-if="form.role === 'embedding'" label="向量维度">
          <el-input-number v-model="form.embeddingDims" :min="64" :max="8192" />
        </el-form-item>
        <el-form-item v-if="!editId" label="设为默认">
          <el-switch v-model="form.isDefault" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="!editId && wizardStep > 0" @click="wizardStep -= 1">上一步</el-button>
        <el-button
          v-if="!editId && wizardStep === 0"
          class="sys-btn-accent"
          type="primary"
          @click="goConfigStep"
        >
          下一步
        </el-button>
        <el-button
          v-else-if="!editId && wizardStep === 1"
          class="sys-btn-accent"
          type="primary"
          @click="wizardStep = 2"
        >
          下一步
        </el-button>
        <el-button v-else class="sys-btn-accent" type="primary" :loading="saving" @click="submit">
          {{ editId ? '保存' : '保存模型' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import DefaultModelSelect from '../components/system-config/DefaultModelSelect.vue'
import LlmModelCard from '../components/system-config/LlmModelCard.vue'
import ProviderPicker from '../components/system-config/ProviderPicker.vue'
import { fetchMe } from '../api/auth'
import {
  createLlmModel,
  deleteLlmModel,
  listLlmModels,
  listLlmProviders,
  setDefaultLlmModel,
  testLlmModel,
  updateLlmModel,
} from '../api/systemConfig'
import { LLM_PROVIDERS_FALLBACK } from '../constants/llmProviders.fallback'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const testingId = ref(null)
const items = ref([])
const providers = ref([...LLM_PROVIDERS_FALLBACK])
const search = ref('')
const roleFilter = ref(null)
const providerFilter = ref(null)
const dialogVisible = ref(false)
const editId = ref(null)
const wizardStep = ref(0)
const form = reactive({
  name: '',
  role: 'chat',
  provider: 'openai_compatible',
  apiBase: '',
  apiKey: '',
  modelName: '',
  timeoutSec: 120,
  temperature: 0,
  embeddingDims: 2560,
  isDefault: false,
})

const providersForRole = computed(() =>
  providers.value.filter((p) => !p.roles?.length || p.roles.includes(form.role)),
)

const filteredItems = computed(() => {
  let list = items.value
  if (roleFilter.value) list = list.filter((m) => m.role === roleFilter.value)
  if (providerFilter.value) list = list.filter((m) => m.provider === providerFilter.value)
  const key = search.value.trim().toLowerCase()
  if (key) {
    list = list.filter(
      (m) =>
        m.name.toLowerCase().includes(key) ||
        String(m.modelName || '')
          .toLowerCase()
          .includes(key) ||
        String(m.provider || '')
          .toLowerCase()
          .includes(key),
    )
  }
  return list
})

const currentProvider = computed(() =>
  providers.value.find((p) => p.code === form.provider),
)

async function guardAdmin() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可配置 AI 模型')
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

async function loadProviders() {
  try {
    const res = await listLlmProviders()
    if (res.items?.length) providers.value = res.items
  } catch {
    /* 使用 fallback */
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await listLlmModels()
    items.value = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function applyProviderDefaults(code) {
  const p = providers.value.find((x) => x.code === code)
  if (!p) return
  if (p.defaultApiBase) form.apiBase = p.defaultApiBase
  if (!form.name && p.name) form.name = p.name
  if (!form.modelName && p.suggestedModels?.[0]) form.modelName = p.suggestedModels[0]
}

function onProviderChange(code) {
  applyProviderDefaults(code)
}

function goConfigStep() {
  if (!form.provider) {
    ElMessage.warning('请选择供应商')
    return
  }
  applyProviderDefaults(form.provider)
  wizardStep.value = 1
}

function suggestModels(query, cb) {
  const list = currentProvider.value?.suggestedModels || []
  const q = (query || '').toLowerCase()
  cb(
    list
      .filter((m) => !q || m.toLowerCase().includes(q))
      .map((value) => ({ value })),
  )
}

function openCreate() {
  editId.value = null
  wizardStep.value = 0
  Object.assign(form, {
    name: '',
    role: 'chat',
    provider: 'deepseek',
    apiBase: '',
    apiKey: '',
    modelName: '',
    timeoutSec: 120,
    temperature: 0,
    embeddingDims: 2560,
    isDefault: false,
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  wizardStep.value = 1
  Object.assign(form, {
    name: row.name,
    role: row.role,
    provider: row.provider,
    apiBase: row.apiBase,
    apiKey: '',
    modelName: row.modelName,
    timeoutSec: row.timeoutSec,
    temperature: row.temperature,
    embeddingDims: row.extra?.embedding_dims || 2560,
    isDefault: row.isDefault,
  })
  dialogVisible.value = true
}

function buildExtra() {
  if (form.role === 'embedding') {
    return { embedding_dims: form.embeddingDims }
  }
  return {}
}

async function submit() {
  if (!form.name.trim() || !form.apiBase.trim() || !form.modelName.trim()) {
    ElMessage.warning('请填写名称、API Base、基础模型')
    return
  }
  saving.value = true
  try {
    const extra = buildExtra()
    if (editId.value) {
      const payload = {
        name: form.name.trim(),
        provider: form.provider.trim() || 'openai_compatible',
        apiBase: form.apiBase.trim(),
        modelName: form.modelName.trim(),
        timeoutSec: form.timeoutSec,
        temperature: form.temperature,
        extra,
      }
      if (form.apiKey.trim()) payload.apiKey = form.apiKey
      await updateLlmModel(editId.value, payload)
    } else {
      await createLlmModel({
        name: form.name.trim(),
        provider: form.provider.trim() || 'openai_compatible',
        apiBase: form.apiBase.trim(),
        apiKey: form.apiKey || null,
        modelName: form.modelName.trim(),
        role: form.role,
        timeoutSec: form.timeoutSec,
        temperature: form.temperature,
        extra,
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
    const res = await testLlmModel(row.id)
    if (res.ok) ElMessage.success(res.message || '连通成功')
    else ElMessage.error(res.message || '连通失败')
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '测试失败')
  } finally {
    testingId.value = null
  }
}

async function onSetDefault(row) {
  try {
    await setDefaultLlmModel(row.id)
    ElMessage.success(`已设为默认 ${row.role === 'embedding' ? 'Embedding' : 'Chat'} 模型`)
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '设置失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`删除模型「${row.name}」？`, '确认', { type: 'warning' })
  try {
    await deleteLlmModel(row.id)
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
  await Promise.all([loadProviders(), loadList()])
})
</script>
