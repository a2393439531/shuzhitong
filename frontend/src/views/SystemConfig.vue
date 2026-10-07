<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span>系统配置（只读）</span>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border v-loading="loading">
        <el-descriptions-item label="平台版本">{{ cfg.version }}</el-descriptions-item>
        <el-descriptions-item label="数据库类型">
          <el-tag :type="cfg.db_type === 'postgresql' ? 'success' : ''">{{ cfg.db_type }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="数据库连接（脱敏）" :span="2">{{ cfg.db_dsn }}</el-descriptions-item>
        <el-descriptions-item label="LLM 提供方">{{ cfg.llm_provider }}</el-descriptions-item>
        <el-descriptions-item label="LLM 是否可用">
          <el-tag :type="cfg.llm_configured ? 'success' : 'info'">
            {{ cfg.llm_configured ? '已配置' : '未配置（降级模式）' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="LLM 模型">{{ cfg.llm_model || '—' }}</el-descriptions-item>
        <el-descriptions-item label="演示数据开关">
          <el-tag :type="cfg.seed_enabled ? '' : 'warning'">{{ cfg.seed_enabled ? '开启' : '关闭' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="服务监听">{{ cfg.host }}:{{ cfg.port }}</el-descriptions-item>
        <el-descriptions-item label="日志级别">{{ cfg.log_level }}</el-descriptions-item>
        <el-descriptions-item label="JWT 密钥状态">
          <el-tag :type="cfg.jwt_is_default ? 'danger' : 'success'">
            {{ cfg.jwt_is_default ? '默认值（生产请更换）' : '已自定义' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Token 有效期">{{ cfg.token_expire_minutes }} 分钟</el-descriptions-item>
      </el-descriptions>
      <el-alert
        title="敏感配置（JWT 密钥、LLM Key、数据库密码）不会经此接口返回；修改配置请编辑 .env 或环境变量后重启服务。"
        type="info"
        :closable="false"
        style="margin-top: 16px"
      />
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header><span>大模型辅助验证（口径解释）</span></template>
      <div class="filter-bar">
        <el-input v-model="q" placeholder="输入要解释的内容，如：核安全分级" style="width: 320px" @keyup.enter="doExplain" />
        <el-button type="primary" @click="doExplain" :loading="explaining">解释</el-button>
        <el-tag v-if="via" :type="via === 'llm' ? 'success' : 'info'" style="margin-left: 8px">
          {{ via === 'llm' ? '大模型生成' : '本地规则' }}
        </el-tag>
      </div>
      <div v-if="reason" style="margin-bottom: 8px"><el-text type="info">{{ reason }}</el-text></div>
      <el-input v-model="answer" type="textarea" :rows="6" readonly placeholder="解释结果将显示在这里" />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSystemConfigApi, llmExplainApi } from '../api/index.js'

const cfg = ref({})
const loading = ref(false)
const q = ref('')
const answer = ref('')
const via = ref('')
const reason = ref('')
const explaining = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await getSystemConfigApi()
    cfg.value = data
  } catch (e) {
    ElMessage.error('配置加载失败')
  } finally {
    loading.value = false
  }
}

async function doExplain() {
  if (!q.value.trim()) return
  explaining.value = true
  try {
    const { data } = await llmExplainApi({ kind: '口径澄清', text: q.value.trim() })
    answer.value = data.content || ''
    via.value = data.via || ''
    reason.value = data.reason || ''
  } catch (e) {
    ElMessage.error('解释失败')
  } finally {
    explaining.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
</style>
