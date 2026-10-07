<template>
  <el-container class="layout">
    <el-aside width="220px" class="sidebar">
      <div class="brand">
        <div class="brand-title">数治通</div>
        <div class="brand-sub">治理基础 · 一期</div>
      </div>
      <el-menu
        :default-active="activePath"
        router
        background-color="#1f2d3d"
        text-color="#c0cbd8"
        active-text-color="#409eff"
      >
        <template v-for="item in menus" :key="item.path">
          <el-menu-item
            v-if="!(item.meta.needAudit && !auth.canViewAudit)"
            :index="'/' + item.path"
          >
            {{ item.meta.title }}
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ pageTitle }}</span>
        <div class="user-box">
          <span class="user-name">{{ auth.user?.real_name || auth.user?.username }}</span>
          <el-tag size="small" type="info">{{ auth.roleLabel() }}</el-tag>
          <el-button link type="primary" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { auth } from '../store/auth.js'

const route = useRoute()
const router = useRouter()

const menus = computed(() =>
  router
    .getRoutes()
    .find((r) => r.path === '/')
    ?.children.filter((c) => c.meta?.title) || []
)

const activePath = computed(() => '/' + (route.path.split('/')[1] || ''))

const pageTitle = computed(() => route.meta?.title || '数治通')

function handleLogout() {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
    .then(() => {
      auth.clear()
      router.push('/login')
    })
    .catch(() => {})
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.sidebar {
  background-color: #1f2d3d;
  display: flex;
  flex-direction: column;
}
.brand {
  padding: 20px 16px;
  color: #fff;
  border-bottom: 1px solid #2d3f54;
}
.brand-title {
  font-size: 20px;
  font-weight: bold;
  letter-spacing: 2px;
}
.brand-sub {
  font-size: 12px;
  color: #8a9bad;
  margin-top: 4px;
}
.sidebar .el-menu {
  border-right: none;
  flex: 1;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e6e8eb;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.user-box {
  display: flex;
  align-items: center;
  gap: 10px;
}
.user-name {
  font-size: 14px;
  color: #333;
}
.main {
  background: #f2f4f7;
  padding: 20px;
}
</style>
