<template>
  <div class="layout">
    <header class="header">
      <span class="title">智能问数</span>
      <div class="user-area">
        <span v-if="user">{{ user.username }}（{{ user.role }}）</span>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </header>
    <main class="main">
      <el-alert
        title="问数对话页待接入 POST /api/v1/ask"
        type="info"
        :closable="false"
        show-icon
      />
      <el-card v-if="user" style="margin-top: 16px">
        <pre>{{ JSON.stringify(user, null, 2) }}</pre>
      </el-card>
    </main>
  </div>
</template>

<script setup>
/** 首页占位：展示 /auth/me；问数对话 UI 待接 POST /api/v1/ask */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchMe } from '../api/auth'

const router = useRouter()
const user = ref(null)

onMounted(async () => {
  try {
    const res = await fetchMe()
    user.value = res.user
  } catch {
    router.push('/login')
  }
})

function logout() {
  localStorage.removeItem('accessToken')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
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
.user-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.main {
  max-width: 960px;
  margin: 24px auto;
  padding: 0 16px;
}
</style>
