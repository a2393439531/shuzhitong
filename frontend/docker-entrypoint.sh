#!/bin/sh
# 运行时配置：由环境变量生成前端 config.js，并渲染 nginx 反代目标
set -e
API_BASE="${SZT_API_BASE:-/api}"
cat > /usr/share/nginx/html/config.js <<EOJS
// 由容器启动时按环境变量 SZT_API_BASE 自动生成
window.__SZT_CONFIG__ = { apiBase: "${API_BASE}" };
EOJS
# 渲染 nginx 模板（SZT_API_UPSTREAM 指向后端，如 http://shuzhitong-api:8000）
export SZT_API_UPSTREAM="${SZT_API_UPSTREAM:-http://shuzhitong-api:8000}"
envsubst '${SZT_API_UPSTREAM}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
exec "$@"
