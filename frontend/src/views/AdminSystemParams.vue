<template>
  <div class="sys-page">
    <header class="sys-header">
      <span class="sys-header__title">系统 · 系统参数</span>
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
        title="仅超管可改。保存后立即对后续问数生效，无需重启服务。"
        style="margin-bottom: 16px"
      />

      <div v-loading="loading" class="param-list">
        <el-card v-for="item in items" :key="item.key" class="param-card" shadow="never">
          <div class="param-card__head">
            <div>
              <div class="param-card__title">{{ item.displayName }}</div>
              <p class="sys-muted param-card__desc">{{ item.description }}</p>
            </div>
            <el-tag size="small" type="info">{{ item.key }}</el-tag>
          </div>
          <div class="param-card__body">
            <el-input-number
              v-if="item.valueType === 'int'"
              v-model="draft[item.key]"
              :min="item.minValue ?? 1"
              :max="item.maxValue ?? 10000"
              :step="10"
              controls-position="right"
            />
            <el-input v-else v-model="draft[item.key]" style="max-width: 320px" />
            <span v-if="item.valueType === 'int'" class="sys-muted">行</span>
            <el-button
              class="sys-btn-accent"
              type="primary"
              :loading="savingKey === item.key"
              :disabled="String(draft[item.key]) === String(item.value)"
              @click="save(item)"
            >
              保存
            </el-button>
          </div>
          <p v-if="item.updatedAt" class="sys-muted param-card__meta">最近更新：{{ item.updatedAt }}</p>
        </el-card>
        <div v-if="!loading && !items.length" class="sys-empty">
          <p class="sys-empty__title">暂无系统参数</p>
          <p>请确认已在 copilot 库执行 V018__sys_param.sql。</p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import MetaAdminNav from '../components/MetaAdminNav.vue'
import { fetchMe } from '../api/auth'
import { listSysParams, updateSysParam } from '../api/systemConfig'

const router = useRouter()
const loading = ref(false)
const savingKey = ref('')
const items = ref([])
const draft = reactive({})

async function guardAdmin() {
  try {
    const res = await fetchMe()
    if (res.user.role !== 'ADMIN') {
      ElMessage.warning('仅超管可配置系统参数')
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
    const res = await listSysParams()
    items.value = res.items || []
    for (const item of items.value) {
      draft[item.key] = item.valueType === 'int' ? Number(item.value) : item.value
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function save(item) {
  savingKey.value = item.key
  try {
    const res = await updateSysParam(item.key, draft[item.key])
    ElMessage.success('已保存')
    item.value = res.value
    item.updatedAt = res.updatedAt
    draft[item.key] = item.valueType === 'int' ? Number(res.value) : res.value
  } catch (e) {
    ElMessage.error(e?.response?.data?.error?.message || '保存失败')
  } finally {
    savingKey.value = ''
  }
}

function logout() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('userRole')
  router.push('/login')
}

onMounted(async () => {
  if (!(await guardAdmin())) return
  await loadList()
})
</script>

<style scoped>
.param-list {
  max-width: 720px;
}
.param-card {
  border: 1px solid var(--sys-border);
  border-radius: var(--sys-radius-card);
  margin-bottom: 16px;
}
.param-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.param-card__title {
  font-weight: 600;
  font-size: 15px;
}
.param-card__desc {
  margin: 6px 0 0;
  line-height: 1.5;
}
.param-card__body {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}
.param-card__meta {
  margin: 12px 0 0;
  font-size: 12px;
}
</style>
