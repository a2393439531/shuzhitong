<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="title">数治通 · 数据治理与智能问数一体化平台</div>
      <div class="subtitle">一期：治理基础</div>
      <el-form :model="form" @submit.prevent="handleLogin" label-width="0">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" clearable />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="handleLogin">
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <el-divider>演示账号一键填入</el-divider>
      <div class="demo-list">
        <el-button
          v-for="d in demos"
          :key="d.username"
          size="small"
          @click="fillDemo(d)"
        >
          {{ d.label }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { loginApi } from '../api/index.js'
import { auth } from '../store/auth.js'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

const demos = [
  { label: 'admin 超级管理员', username: 'admin', password: 'Admin@123' },
  { label: 'heping 管理员', username: 'heping', password: 'Heping@123' },
  { label: 'weixiu 操作员', username: 'weixiu', password: 'Weixiu@123' },
  { label: 'audit 只读', username: 'audit', password: 'Audit@123' },
]

function fillDemo(d) {
  form.username = d.username
  form.password = d.password
}

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const { data } = await loginApi(form.username, form.password)
    auth.save(data.token, data.user)
    ElMessage.success(`欢迎回来，${data.user.real_name || data.user.username}`)
    router.push('/')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || '登录失败，请检查用户名和密码')
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
  background: linear-gradient(135deg, #1f2d3d 0%, #2d5a8f 100%);
}
.login-card {
  width: 420px;
  padding: 10px;
}
.title {
  font-size: 19px;
  font-weight: bold;
  text-align: center;
  margin-top: 8px;
}
.subtitle {
  font-size: 14px;
  color: #909399;
  text-align: center;
  margin: 8px 0 24px;
}
.demo-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  padding-bottom: 8px;
}
</style>
