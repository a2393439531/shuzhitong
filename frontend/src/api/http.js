import axios from 'axios'
import { ElMessage } from 'element-plus'
import { auth } from '../store/auth.js'

const __runtimeApiBase =
  (typeof window !== 'undefined' && window.__SZT_CONFIG__ && window.__SZT_CONFIG__.apiBase) ||
  undefined

const http = axios.create({
  baseURL: __runtimeApiBase || import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
})

// 请求拦截：自动带 Bearer token
http.interceptors.request.use(
  (config) => {
    if (auth.token) {
      config.headers.Authorization = `Bearer ${auth.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截：401 跳登录
http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401 && auth.isLoggedIn) {
      auth.clear()
      ElMessage.warning('登录已过期，请重新登录')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default http
