<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-input
          v-model="query.q"
          placeholder="搜索资源编码/名称"
          clearable
          style="width: 280px"
          @keyup.enter="loadResources"
        />
        <el-select v-model="query.status" placeholder="状态筛选" clearable style="width: 160px">
          <el-option label="已登记" value="已登记" />
          <el-option label="已发布" value="已发布" />
          <el-option label="审批中" value="审批中" />
          <el-option label="已下架" value="已下架" />
        </el-select>
        <el-button type="primary" @click="loadResources">搜索</el-button>
      </div>
      <el-row :gutter="16" v-loading="loading">
        <el-col :span="8" v-for="r in resources" :key="r.id" class="res-col">
          <el-card shadow="hover" class="res-card" @click="openDetail(r)">
            <div class="res-head">
              <span class="res-name">{{ r.name }}</span>
              <el-tag :type="statusTag(r.status)" size="small">{{ r.status }}</el-tag>
            </div>
            <div class="res-meta">
              <div>编码：{{ r.res_code }}</div>
              <div>来源系统：{{ r.source_system }}</div>
              <div>归口部门：{{ r.owner_dept }}</div>
              <div>更新频率：{{ r.update_freq }}</div>
            </div>
          </el-card>
        </el-col>
      </el-row>
      <el-empty v-if="!loading && !resources.length" description="暂无资源" />
    </el-card>

    <!-- 资源详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="资源详情" size="52%">
      <el-tabs v-if="detail">
        <el-tab-pane label="业务视图">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="中文名">{{ detail.name }}</el-descriptions-item>
            <el-descriptions-item label="资源编码">{{ detail.res_code }}</el-descriptions-item>
            <el-descriptions-item label="业务对象">{{ detail.object_name || detail.object_code }}</el-descriptions-item>
            <el-descriptions-item label="来源系统">{{ detail.source_system }}</el-descriptions-item>
            <el-descriptions-item label="权威来源">{{ detail.authority_source }}</el-descriptions-item>
            <el-descriptions-item label="管理责任">{{ detail.owner_dept }} / {{ detail.data_steward }}</el-descriptions-item>
            <el-descriptions-item label="更新频率">{{ detail.update_freq }}</el-descriptions-item>
            <el-descriptions-item label="访问范围">{{ detail.access_scope }}</el-descriptions-item>
            <el-descriptions-item label="服务方式">{{ detail.service_mode }}</el-descriptions-item>
            <el-descriptions-item label="业务说明">{{ detail.description }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
        <el-tab-pane label="技术视图">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="表或接口">{{ detail.table_or_api }}</el-descriptions-item>
            <el-descriptions-item label="字段">{{ detail.fields }}</el-descriptions-item>
            <el-descriptions-item label="血缘">{{ detail.lineage }}</el-descriptions-item>
            <el-descriptions-item label="关联标准">{{ relatedStandards }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
      <div class="drawer-actions" v-if="detail">
        <el-button
          type="primary"
          :disabled="!canSubmit"
          @click="handleSubmit"
        >
          提交审批
        </el-button>
        <el-button
          type="danger"
          :disabled="!canOffline"
          @click="handleOffline"
        >
          下架
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listResourcesApi,
  getResourceApi,
  submitResourceApi,
  offlineResourceApi,
} from '../api/index.js'

const resources = ref([])
const loading = ref(false)
const query = reactive({ q: '', status: '' })

const drawerVisible = ref(false)
const detail = ref(null)

const canSubmit = computed(() => ['已登记'].includes(detail.value?.status))
const canOffline = computed(() => ['已发布'].includes(detail.value?.status))
const relatedStandards = computed(() => {
  const s = detail.value?.standards
  if (Array.isArray(s)) return s.map((x) => x.name || x.code).join('、')
  return s || '-'
})

function statusTag(status) {
  const map = { '已发布': 'success', '已登记': 'info', '审批中': 'warning', '已下架': 'danger' }
  return map[status] || 'info'
}

async function loadResources() {
  loading.value = true
  try {
    const params = {}
    if (query.q) params.q = query.q
    if (query.status) params.status = query.status
    const { data } = await listResourcesApi(params)
    resources.value = Array.isArray(data) ? data : data.items || []
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  try {
    const { data } = await getResourceApi(row.id)
    detail.value = data
    drawerVisible.value = true
  } catch (_) {
    ElMessage.error('加载资源详情失败')
  }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm('确定提交该资源进入审批吗？', '提示', { type: 'warning' })
    await submitResourceApi(detail.value.id)
    ElMessage.success('已提交审批')
    drawerVisible.value = false
    loadResources()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('提交失败')
  }
}

async function handleOffline() {
  try {
    await ElMessageBox.confirm('确定下架该资源吗？', '提示', { type: 'warning' })
    await offlineResourceApi(detail.value.id)
    ElMessage.success('已下架')
    drawerVisible.value = false
    loadResources()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('下架失败')
  }
}

onMounted(loadResources)
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.res-col {
  margin-bottom: 16px;
}
.res-card {
  cursor: pointer;
}
.res-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.res-name {
  font-weight: 600;
  font-size: 15px;
}
.res-meta {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}
.drawer-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
}
</style>
