import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../store/auth.js'
import Layout from '../components/Layout.vue'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '首页仪表盘', icon: 'Odometer' } },
      { path: 'objects', name: 'Objects', component: () => import('../views/Objects.vue'), meta: { title: '业务对象中心', icon: 'Box' } },
      { path: 'catalog', name: 'Catalog', component: () => import('../views/Catalog.vue'), meta: { title: '数据目录中心', icon: 'Folder' } },
      { path: 'standards', name: 'Standards', component: () => import('../views/Standards.vue'), meta: { title: '标准中心', icon: 'Document' } },
      { path: 'masterdata', name: 'MasterData', component: () => import('../views/MasterData.vue'), meta: { title: '主数据中心', icon: 'Key' } },
      { path: 'field-mapping', name: 'FieldMapping', component: () => import('../views/FieldMapping.vue'), meta: { title: '字段映射', icon: 'Connection' } },
      { path: 'quality-rules', name: 'QualityRules', component: () => import('../views/QualityRules.vue'), meta: { title: '质量规则', icon: 'DataAnalysis' } },
      { path: 'compliance', name: 'Compliance', component: () => import('../views/Compliance.vue'), meta: { title: '落标检查', icon: 'Checked' } },
      { path: 'responsibility', name: 'Responsibility', component: () => import('../views/Responsibility.vue'), meta: { title: '责任工作台', icon: 'Avatar' } },
      { path: 'approvals', name: 'Approvals', component: () => import('../views/Approvals.vue'), meta: { title: '审批中心', icon: 'Stamp' } },
      { path: 'audit', name: 'Audit', component: () => import('../views/Audit.vue'), meta: { title: '审计日志', icon: 'List', needAudit: true } },
      { path: 'system', name: 'SystemConfig', component: () => import('../views/SystemConfig.vue'), meta: { title: '系统配置', icon: 'Setting', needAdmin: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !auth.isLoggedIn) {
    return '/login'
  }
  if (to.path === '/login' && auth.isLoggedIn) {
    return '/'
  }
  if (to.meta.needAudit && !auth.canViewAudit) {
    return '/'
  }
  if (to.meta.needAdmin && !auth.isAdmin) {
    return '/'
  }
  return true
})

export default router
