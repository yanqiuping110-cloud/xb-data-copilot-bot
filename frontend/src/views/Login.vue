<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>小奔问数</h2>
      <el-form :model="form" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
/** 登录页：调用问数自有 /api/v1/auth/login，token 存 localStorage */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api/auth'

const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: 'admin',
  password: '',
})

async function onSubmit() {
  loading.value = true
  try {
    const res = await login({
      username: form.username,
      password: form.password,
    })
    localStorage.setItem('accessToken', res.accessToken)
    ElMessage.success('登录成功')
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 400px;
}
.login-card h2 {
  text-align: center;
  margin: 0 0 24px;
}
</style>
