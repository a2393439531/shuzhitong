<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-input
          v-model="query.q"
          placeholder="搜索标准编码/名称"
          clearable
          style="width: 280px"
          @keyup.enter="loadStandards"
        />
        <el-select v-model="query.status" placeholder="状态筛选" clearable style="width: 160px">
          <el-option label="草稿" value="草稿" />
          <el-option label="审批中" value="审批中" />
          <el-option label="已发布" value="已发布" />
          <el-option label="已废止" value="已废止" />
        </el-select>
        <el-button type="primary" @click="loadStandards">搜索</el-button>
      </div>
      <el-table :data="standards" v-loading="loading">
        <el-table-column prop="code" label="编码" width="170" />
        <el-table-column prop="name" label="名称" min-width="220" />
        <el-table-column prop="std_type" label="分类" width="130" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner_dept" label="归口部门" width="140" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看详情</el-button>
            <el-button link type="primary" :disabled="row.status !== '草稿'" @click="handleSubmit(row)">
              提交审批
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 标准详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="标准详情" size="52%">
      <div v-if="detail" v-loading="detailLoading">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="编码">{{ detail.code }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ detail.std_type }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
          <el-descriptions-item label="业务定义">{{ detail.business_def }}</el-descriptions-item>
          <el-descriptions-item label="允许值">
            <el-tag v-for="v in asList(detail.allowed_values)" :key="v" size="small" style="margin-right:4px">{{ v }}</el-tag>
            <span v-if="!asList(detail.allowed_values).length" class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="权威来源">{{ detail.authority_source }}</el-descriptions-item>
          <el-descriptions-item label="责任主体">{{ detail.owner_role }}</el-descriptions-item>
          <el-descriptions-item label="校验规则">
            <div v-for="(v, k) in asMap(detail.check_rules)" :key="k" class="rule-row">
              <span class="rule-key">{{ k }}</span>：{{ v }}
            </div>
            <span v-if="!Object.keys(asMap(detail.check_rules)).length" class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="变更要求">{{ detail.change_requirement }}</el-descriptions-item>
          <el-descriptions-item label="生效日期">{{ detail.effective_date }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">落标情况</div>
        <el-table :data="adoption" empty-text="暂无落标数据">
          <el-table-column prop="system_name" label="系统" width="200" />
          <el-table-column prop="status" label="状态" width="130">
            <template #default="{ row }">
              <el-tag :type="row.status === '已落标' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="diff_desc" label="差异说明" min-width="220" />
        </el-table>

        <div class="drawer-actions">
          <el-button type="primary" :disabled="detail.status !== '草稿'" @click="handleSubmit(detail)">
            提交审批
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listStandardsApi,
  getStandardApi,
  submitStandardApi,
  getStandardAdoptionApi,
} from '../api/index.js'

const standards = ref([])
const loading = ref(false)
const query = reactive({ q: '', status: '' })

const drawerVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const adoption = ref([])

function statusTag(status) {
  const map = { '已发布': 'success', '草稿': 'info', '审批中': 'warning', '已废止': 'danger' }
  return map[status] || 'info'
}

// 兼容后端返回的数组/对象与旧版 JSON 字符串
function asList(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v) {
    try {
      const p = JSON.parse(v)
      return Array.isArray(p) ? p : [v]
    } catch { return [v] }
  }
  return []
}
function asMap(v) {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v
  if (typeof v === 'string' && v) {
    try {
      const p = JSON.parse(v)
      return p && typeof p === 'object' && !Array.isArray(p) ? p : {}
    } catch { return {} }
  }
  return {}
}

async function loadStandards() {
  loading.value = true
  try {
    const params = {}
    if (query.q) params.q = query.q
    if (query.status) params.status = query.status
    const { data } = await listStandardsApi(params)
    standards.value = Array.isArray(data) ? data : data.items || []
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  adoption.value = []
  try {
    const [{ data: d }, { data: a }] = await Promise.all([
      getStandardApi(row.id),
      getStandardAdoptionApi(row.id).catch(() => ({ data: [] })),
    ])
    detail.value = d
    adoption.value = Array.isArray(a) ? a : a.items || []
  } catch (_) {
    ElMessage.error('加载标准详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function handleSubmit(row) {
  try {
    await ElMessageBox.confirm(`确定提交标准「${row.name}」进入审批吗？`, '提示', { type: 'warning' })
    await submitStandardApi(row.id)
    ElMessage.success('已提交审批')
    if (drawerVisible.value) drawerVisible.value = false
    loadStandards()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('提交失败')
  }
}

onMounted(loadStandards)
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  margin: 20px 0 12px;
}
.drawer-actions {
  margin-top: 20px;
}
.muted { color: #909399; }
.rule-row { line-height: 1.7; }
.rule-key { font-weight: 600; }
</style>
