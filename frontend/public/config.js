// 数治通前端运行时配置（部署时可直接替换此文件，无需重新构建）。
// docker-compose 会根据环境变量 SZT_API_BASE 自动生成此文件。
window.__SZT_CONFIG__ = {
  // 后端 API 基地址：默认 '/api'（走 nginx 同域反代）；
  // 前后端分离部署时改为绝对地址，如 'http://192.168.1.10:8000/api'
  apiBase: '/api',
}
