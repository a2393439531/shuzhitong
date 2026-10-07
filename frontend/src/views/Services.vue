<template>
  <div>
    <el-card>
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 服务目录 -->
        <el-tab-pane label="服务目录" name="catalog">
          <div class="filter-bar">
            <el-select v-model="svcTypeFilter" placeholder="服务类型" clearable style="width: 180px" @change="loadServices">
              <el-option v-for="t in svcTypes" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
            <el-button type="primary" @click="loadServices">搜索</el-button>
            <el-button v-if="auth.isAdmin" @click="openServiceDialog()">新增服务</el-button>
          </div>
          <el-table :data="filteredServices" v-loading="servicesLoading" @row-click="openDetail" style="cursor: pointer">
            <el-table-column prop="name" label="服务名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="svc_type_label" label="类型" width="130">
              <template #default="{ row }">{{ row.svc_type_label || row.svc_type || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="api_version" label="接口版本" width="110" />
            <el-table-column prop="quality_status" label="质量" width="100">
              <template #default="{ row }"><el-tag :type="qualityType(row.quality_status)" size="small">{{ row.quality_status || '-' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="owner" label="责任人" width="120" show-overflow-tooltip />
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click.stop="subscribe(row)">申请授权</el-button>
                <el-button link type="primary" size="small" @click.stop="openInvokeDialog(row)">调用测试</el-button>
                <el-button v-if="auth.isAdmin" link type="primary" size="small" @click.stop="openServiceDialog(row)">编辑</el-button>
                <el-button v-if="auth.isAdmin && row.status !== '已发布'" link type="success" size="small" @click.stop="doPublish(row)">发布</el-button>
                <el-button v-if="auth.isAdmin && row.status !== '已下架'" link type="danger" size="small" @click.stop="doOffline(row)">下架</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 我的申请 -->
        <el-tab-pane label="我的申请" name="mine">
          <el-table :data="mySubs" v-loading="mySubsLoading">
            <el-table-column prop="service_name" label="服务" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="120">
              <template #default="{ row }"><el-tag :type="subStatusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="applied_at" label="申请时间" width="170" />
            <el-table-column prop="note" label="审核意见" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.note || row.review_note || row.comment || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="auth.isAdmin" label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button v-if="isPendingReview(row)" link type="success" size="small" @click="reviewSub(row, true)">通过</el-button>
                <el-button v-if="isPendingReview(row)" link type="danger" size="small" @click="reviewSub(row, false)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 调用监测 -->
        <el-tab-pane v-if="auth.isAdmin" label="调用监测" name="stats">
          <div class="filter-bar">
            <el-select v-model="statsServiceId" placeholder="选择服务" filterable style="width: 300px" @change="loadStats">
              <el-option v-for="s in services" :key="s.id" :label="`${s.name}（${s.code}）`" :value="s.id" />
            </el-select>
          </div>
          <el-row :gutter="16" v-loading="statsLoading">
            <el-col :span="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-label">近 7 天调用次数</div>
                <div class="stat-value">{{ stats?.calls_7d ?? '-' }}</div>
                <div class="stat-desc">统计该服务最近 7 天内被调用的总次数</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-label">平均响应耗时（ms）</div>
                <div class="stat-value">{{ stats?.avg_ms ?? '-' }}</div>
                <div class="stat-desc">最近 7 天全部调用的平均耗时，单位毫秒</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-label">错误率</div>
                <div class="stat-value">{{ stats?.error_rate ?? '-' }}</div>
                <div class="stat-desc">最近 7 天调用失败占比，错误率高需排查</div>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 服务详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="服务详情" size="560px" direction="rtl">
      <div v-if="detail" class="detail-body">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="服务名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="编码">{{ detail.code }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.svc_type_label || detail.svc_type }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
          <el-descriptions-item label="接口版本">{{ detail.api_version }}</el-descriptions-item>
          <el-descriptions-item label="描述">{{ detail.description || detail.desc || '-' }}</el-descriptions-item>
          <el-descriptions-item label="数据来源">{{ detail.data_sources || detail.data_source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="标准版本">{{ detail.standard_version || detail.std_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="权限要求">{{ detail.permission_required || detail.permission || '-' }}</el-descriptions-item>
          <el-descriptions-item label="更新频率">{{ detail.update_frequency || detail.refresh_freq || '-' }}</el-descriptions-item>
          <el-descriptions-item label="责任人">{{ detail.owner || '-' }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="sec-title">版本历史</h4>
        <el-table :data="detail.versions || []" size="small">
          <el-table-column prop="version" label="版本" width="110" />
          <el-table-column prop="change_desc" label="变更说明" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" width="160" />
        </el-table>
        <h4 class="sec-title">通知列表</h4>
        <el-table :data="detail.notices || []" size="small">
          <el-table-column prop="content" label="内容" min-width="240" show-overflow-tooltip />
          <el-table-column prop="version" label="版本" width="100" />
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </div>
    </el-drawer>

    <!-- 调用测试 dialog -->
    <el-dialog v-model="invokeVisible" title="调用测试" width="620px">
      <el-form label-width="90px">
        <el-form-item label="服务">{{ invokeRow?.name }}（{{ invokeRow?.code }}）</el-form-item>
        <el-form-item label="请求参数">
          <el-input v-model="invokeParams" type="textarea" :rows="6" placeholder='JSON 格式，如 {"date": "2026-09"}' />
        </el-form-item>
      </el-form>
      <el-button type="primary" @click="doInvoke" :loading="invoking">发送调用</el-button>
      <div v-if="invokeResult" class="invoke-result">
        <el-descriptions :column="2" border size="small" style="margin: 12px 0">
          <el-descriptions-item label="结果">{{ invokeResult.ok ? '成功' : '失败' }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ invokeResult.elapsed_ms }} ms</el-descriptions-item>
        </el-descriptions>
        <div class="result-label">返回数据</div>
        <pre class="json-block">{{ JSON.stringify(invokeResult.data, null, 2) }}</pre>
      </div>
    </el-dialog>

    <!-- 新增/编辑服务 dialog -->
    <el-dialog v-model="serviceDialogVisible" :title="editingService ? '编辑服务' : '新增服务'" width="560px">
      <el-form :model="serviceForm" label-width="100px">
        <el-form-item label="服务编码"><el-input v-model="serviceForm.code" /></el-form-item>
        <el-form-item label="服务名称"><el-input v-model="serviceForm.name" /></el-form-item>
        <el-form-item label="服务类型">
          <el-select v-model="serviceForm.svc_type" style="width: 100%">
            <el-option v-for="t in svcTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="serviceForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="责任人"><el-input v-model="serviceForm.owner" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="serviceDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitService" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { auth } from '../store/auth.js'
import {
  listServicesApi, getServiceApi, createServiceApi, updateServiceApi,
  publishServiceApi, offlineServiceApi, subscribeServiceApi,
  listMySubscriptionsApi, reviewSubscriptionApi,
  invokeServiceApi, getServiceStatsApi,
} from '../api/index.js'

const activeTab = ref('catalog')
const submitting = ref(false)

const svcTypes = [
  { value: 'master', label: '主数据服务' },
  { value: 'relation', label: '关系服务' },
  { value: 'detail', label: '明细查询服务' },
  { value: 'metric', label: '指标服务' },
  { value: 'combo', label: '组合分析服务' },
  { value: 'validate', label: '校验服务' },
]

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}
function statusType(s) {
  const map = { 已发布: 'success', 草稿: 'info', 待发布: 'warning', 已下架: 'danger', 已下线: 'danger' }
  return map[s] || 'info'
}
function qualityType(s) {
  const map = { 正常: 'success', 优: 'success', 良: 'warning', 差: 'danger', 异常: 'danger' }
  return map[s] || 'info'
}
function subStatusType(s) {
  const map = { 已通过: 'success', 待审核: 'warning', 已驳回: 'danger', pending: 'warning', approved: 'success', rejected: 'danger' }
  return map[s] || 'info'
}
function isPendingReview(row) {
  return ['待审核', 'pending'].includes(row.status)
}

// ---------- 服务目录 ----------
const services = ref([])
const servicesLoading = ref(false)
const svcTypeFilter = ref('')

const filteredServices = computed(() => {
  if (!svcTypeFilter.value) return services.value
  return services.value.filter((s) => s.svc_type === svcTypeFilter.value)
})

async function loadServices() {
  servicesLoading.value = true
  try {
    const { data } = await listServicesApi()
    services.value = asList(data)
  } catch (e) {
    ElMessage.error('服务列表加载失败')
  } finally {
    servicesLoading.value = false
  }
}

// ---------- 详情抽屉 ----------
const drawerVisible = ref(false)
const detail = ref(null)

async function openDetail(row) {
  drawerVisible.value = true
  detail.value = null
  try {
    const { data } = await getServiceApi(row.id)
    detail.value = data
  } catch (e) {
    ElMessage.error('服务详情加载失败')
  }
}

// ---------- 申请授权 ----------
async function subscribe(row) {
  try {
    await ElMessageBox.confirm(`确定向服务「${row.name}」申请调用授权吗？`, '提示', { type: 'info' })
    await subscribeServiceApi(row.id)
    ElMessage.success('申请已提交')
    loadMySubs()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('申请失败')
  }
}

// ---------- 调用测试 ----------
const invokeVisible = ref(false)
const invokeRow = ref(null)
const invokeParams = ref('')
const invokeResult = ref(null)
const invoking = ref(false)

function openInvokeDialog(row) {
  invokeRow.value = row
  invokeParams.value = '{}'
  invokeResult.value = null
  invokeVisible.value = true
}

async function doInvoke() {
  let params = {}
  try {
    params = invokeParams.value.trim() ? JSON.parse(invokeParams.value) : {}
  } catch (e) {
    ElMessage.warning('请求参数不是合法的 JSON')
    return
  }
  invoking.value = true
  try {
    const { data } = await invokeServiceApi(invokeRow.value.code, { params })
    invokeResult.value = data
  } catch (e) {
    ElMessage.error('调用失败')
  } finally {
    invoking.value = false
  }
}

// ---------- 发布 / 下架 ----------
async function doPublish(row) {
  try {
    await publishServiceApi(row.id)
    ElMessage.success('已发布')
    loadServices()
  } catch (e) {
    ElMessage.error('发布失败')
  }
}

async function doOffline(row) {
  try {
    await ElMessageBox.confirm(`确定下架服务「${row.name}」吗？`, '提示', { type: 'warning' })
    await offlineServiceApi(row.id)
    ElMessage.success('已下架')
    loadServices()
  } catch (e) {
    if (e === 'cancel') return
    const deps = e?.response?.data?.dependencies
    if (e?.response?.status === 400 && deps?.length) {
      ElMessageBox.alert(`存在依赖该服务的下游项，无法下架：\n${deps.map((d) => `- ${d}`).join('\n')}`, '下架失败', { type: 'error' })
    } else {
      ElMessage.error('下架失败')
    }
  }
}

// ---------- 新增 / 编辑 ----------
const serviceDialogVisible = ref(false)
const editingService = ref(null)
const serviceForm = reactive({ code: '', name: '', svc_type: 'detail', description: '', owner: '' })

function openServiceDialog(row) {
  editingService.value = row || null
  Object.assign(serviceForm, {
    code: row?.code || '',
    name: row?.name || '',
    svc_type: row?.svc_type || 'detail',
    description: row?.description || '',
    owner: row?.owner || '',
  })
  serviceDialogVisible.value = true
}

async function submitService() {
  if (!serviceForm.code || !serviceForm.name) {
    ElMessage.warning('请填写服务编码和名称')
    return
  }
  submitting.value = true
  try {
    if (editingService.value) {
      await updateServiceApi(editingService.value.id, { ...serviceForm })
      ElMessage.success('服务已更新')
    } else {
      await createServiceApi({ ...serviceForm })
      ElMessage.success('服务已创建')
    }
    serviceDialogVisible.value = false
    loadServices()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 我的申请 ----------
const mySubs = ref([])
const mySubsLoading = ref(false)

async function loadMySubs() {
  mySubsLoading.value = true
  try {
    const { data } = await listMySubscriptionsApi()
    mySubs.value = asList(data)
  } catch (e) {
    ElMessage.error('申请列表加载失败')
  } finally {
    mySubsLoading.value = false
  }
}

async function reviewSub(row, approve) {
  try {
    const { value: note } = await ElMessageBox.prompt('审核意见（可空）', approve ? '通过申请' : '驳回申请', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    await reviewSubscriptionApi(row.id, { approve, note: note || '' })
    ElMessage.success('审核完成')
    loadMySubs()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('审核失败')
  }
}

// ---------- 调用监测 ----------
const statsServiceId = ref(null)
const stats = ref(null)
const statsLoading = ref(false)

async function loadStats() {
  if (!statsServiceId.value) return
  statsLoading.value = true
  try {
    const { data } = await getServiceStatsApi(statsServiceId.value)
    stats.value = data
  } catch (e) {
    ElMessage.error('调用统计加载失败')
  } finally {
    statsLoading.value = false
  }
}

// ---------- tabs ----------
function onTabChange() {
  if (activeTab.value === 'mine') loadMySubs()
  else if (activeTab.value === 'stats') {
    if (services.value.length && !statsServiceId.value) {
      statsServiceId.value = services.value[0].id
    }
    loadStats()
  }
}

onMounted(() => {
  loadServices()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.sec-title {
  margin: 18px 0 10px;
  font-size: 14px;
}
.detail-body {
  padding: 0 8px;
}
.invoke-result {
  margin-top: 8px;
}
.result-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}
.json-block {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.stat-card {
  text-align: center;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 8px;
}
.stat-desc {
  font-size: 12px;
  color: #909399;
}
</style>
