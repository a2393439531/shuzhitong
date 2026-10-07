import { reactive } from 'vue'

const KEY = 'shuzhitong_auth'

function load() {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch (_) {}
  return { token: '', user: null }
}

export const auth = reactive({
  token: load().token,
  user: load().user,

  get isLoggedIn() {
    return !!this.token
  },

  get role() {
    return this.user?.role || ''
  },

  // 管理员及以上（含 super_admin）
  get isAdmin() {
    return ['super_admin', 'admin'].includes(this.role)
  },

  // 审计日志菜单：仅管理员及以上可见
  get canViewAudit() {
    return ['super_admin', 'admin'].includes(this.role)
  },

  roleLabel() {
    const map = {
      super_admin: '超级管理员',
      admin: '管理员',
      operator: '操作员',
      readonly: '只读',
    }
    return map[this.role] || this.role || '未知'
  },

  save(token, user) {
    this.token = token
    this.user = user
    localStorage.setItem(KEY, JSON.stringify({ token, user }))
  },

  clear() {
    this.token = ''
    this.user = null
    localStorage.removeItem(KEY)
  },
})
