<template>
  <div class="login-page">
    <div class="login-bg" aria-hidden="true">
      <div class="orb orb-a" />
      <div class="orb orb-b" />
      <div class="grid-lines" />
    </div>

    <div class="login-shell">
      <aside class="brand-panel">
        <div class="brand-inner">
          <p class="brand-kicker">Enterprise Analytics</p>
          <h1 class="brand-title">Data Copilot</h1>
          <p class="brand-subtitle">企业级智能问数与深度洞察平台</p>
          <ul class="brand-points">
            <li>
              <span class="point-icon">◆</span>
              <span>自然语言问数 · SQL 可审计 · 权限隔离</span>
            </li>
            <li>
              <span class="point-icon">◆</span>
              <span>Insight Engine · 多章深度报告 · PDF 交付</span>
            </li>
            <li>
              <span class="point-icon">◆</span>
              <span>实时进度反馈 · 全链路留痕 · 运营可用</span>
            </li>
          </ul>
        </div>
      </aside>

      <main class="form-panel">
        <div class="form-card">
          <header class="form-header">
            <h2>欢迎登录</h2>
            <p>使用企业账号进入智能问数工作台</p>
          </header>

          <el-form
            class="login-form"
            :model="form"
            label-position="top"
            @submit.prevent="onSubmit"
          >
            <el-form-item label="用户名">
              <el-input
                v-model="form.username"
                size="large"
                placeholder="请输入用户名"
                autocomplete="username"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                type="password"
                size="large"
                placeholder="请输入密码"
                show-password
                autocomplete="current-password"
                @keyup.enter="onSubmit"
              />
            </el-form-item>
            <el-button
              class="submit-btn"
              type="primary"
              size="large"
              native-type="submit"
              :loading="loading"
            >
              进入工作台
            </el-button>
          </el-form>

          <footer class="form-footer">
            <span>安全登录 · 数据受控 · 操作可审计</span>
          </footer>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
/** 登录页：调用问数自有 /api/v1/auth/login，token 存 localStorage */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api/auth'
import { defaultHomePath } from '../utils/roleHome'

const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

async function onSubmit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const res = await login({
      username: form.username,
      password: form.password,
    })
    localStorage.setItem('accessToken', res.accessToken)
    localStorage.setItem('userRole', res.user.role)
    ElMessage.success('登录成功')
    router.push(defaultHomePath(res.user.role))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  background: #f4f6fb;
  overflow: hidden;
}

.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.45;
}

.orb-a {
  width: 420px;
  height: 420px;
  top: -120px;
  left: -80px;
  background: radial-gradient(circle, #818cf8 0%, transparent 70%);
}

.orb-b {
  width: 360px;
  height: 360px;
  right: -60px;
  bottom: -80px;
  background: radial-gradient(circle, #a78bfa 0%, transparent 70%);
}

.grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(99, 102, 241, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99, 102, 241, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
}

.login-shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1fr 420px;
  width: min(960px, 100%);
  min-height: 520px;
  border-radius: 20px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.9) inset;
}

.brand-panel {
  padding: 48px 44px;
  background: linear-gradient(145deg, #4f46e5 0%, #7c3aed 52%, #6366f1 100%);
  color: #fff;
  display: flex;
  align-items: center;
}

.brand-inner {
  max-width: 360px;
}

.brand-kicker {
  margin: 0 0 12px;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.82;
}

.brand-title {
  margin: 0;
  font-size: 36px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.brand-subtitle {
  margin: 14px 0 36px;
  font-size: 15px;
  line-height: 1.6;
  opacity: 0.92;
}

.brand-points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.brand-points li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  font-size: 14px;
  line-height: 1.55;
  opacity: 0.95;
}

.point-icon {
  font-size: 8px;
  margin-top: 6px;
  opacity: 0.75;
}

.form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 36px;
  background: #fff;
}

.form-card {
  width: 100%;
  max-width: 320px;
}

.form-header h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.form-header p {
  margin: 0 0 28px;
  font-size: 14px;
  color: #64748b;
  line-height: 1.5;
}

.login-form :deep(.el-form-item__label) {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
  padding-bottom: 6px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px #e2e8f0 inset;
  transition: box-shadow 0.2s ease;
}

.login-form :deep(.el-input__wrapper:hover),
.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #6366f1 inset;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
  height: 44px;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  background: linear-gradient(135deg, #6366f1, #7c3aed);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.28);
}

.form-footer {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #f1f5f9;
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
}

@media (max-width: 860px) {
  .login-shell {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .brand-panel {
    padding: 32px 28px;
  }

  .brand-title {
    font-size: 28px;
  }

  .brand-points {
    gap: 10px;
  }

  .form-panel {
    padding: 32px 24px 36px;
  }
}
</style>
