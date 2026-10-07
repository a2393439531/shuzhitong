<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-select v-model="standardId" filterable placeholder="选择要检查的数据标准" style="width: 320px" @change="onStandardChange">
          <el-option
            v-for="s in standards"
            :key="s.id"
            :label="`${s.standard_code || s.code || ''} ${s.standard_name || s.name || ''}`"
            :value="s.id"
          />
        </el-select>
        <el-button type="primary" @click="doRun" :disabled="!standardId" :loading="running">执行检查</el-button>
        <el-button @click="refresh" :disabled="!standardId">刷新</el-button>
      </div>

      <div class="section-title">系统落标状态矩阵</div>
      <div v-loading="statusLoading">
        <el-empty v-if="!standardId" description="请先选择数据标准" :image-size="80" />
        <div v-else class="status-grid">
          <el-card v-for="item in systemStatus" :key="item.system_name" shadow="hover" class="status-card">
            <div class="sys-name">{{ item.system_name }}</div>
            <div style="margin: 8px 0">
              <el-tag :type="sysStatusType(item.status)" size="large">{{ item.status || '-' }}</el-tag>
            </div>
            <div class="sys-diff">差异数：{{ item.diff_count ?? 0 }}</div>
          </el-card>
        </div>
        <el-empty v-if="standardId && !systemStatus.length && !statusLoading" description="暂无系统状态数据" :image-size="80" />
      </div>

      <div class="section-title">检查记录</div>
      <el-table :data="checks" v-loading="checksLoading">
        <el-table-column prop="id" label="检查ID" width="90" />
        <el-table-column prop="standard_code" label="标准编号" width="140" />
        <el-table-column prop="standard_name" label="标准名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="target_desc" label="检查目标" min-width="180" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }"><el-tag :type="checkStatusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="diff_count" label="差异数" width="90" />
        <el-table-column prop="created_at" label="检查时间" width="170" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDiffDialog(row)">查看差异</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="diffDialogVisible" :title="`差异清单（检查 #${checkRow?.id}）`" width="800px">
      <div v-loading="diffLoading">
        <el-descriptions :column="3" border style="margin-bottom: 12px" v-if="checkDetail?.check">
          <el-descriptions-item label="标准">{{ checkDetail.check.standard_code }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ checkDetail.check.status }}</el-descriptions-item>
          <el-descriptions-item label="差异数">{{ checkDetail.check.diff_count ?? diffs.length }}</el-descriptions-item>
        </el-descriptions>
        <el-table :data="diffs">
          <el-table-column prop="system_name" label="系统" width="150" />
          <el-table-column prop="field_name" label="字段" width="150" />
          <el-table-column prop="diff_type" label="差异类型" width="130">
            <template #default="{ row }"><el-tag type="warning" size="small">{{ row.diff_type || '-' }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="expected" label="标准期望" min-width="160" show-overflow-tooltip />
          <el-table-column prop="actual" label="系统实际" min-width="160" show-overflow-tooltip />
          <el-table-column prop="record_ref" label="问题记录" width="140" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="!diffs.length && !diffLoading" description="无差异，系统已全部落标" :image-size="80" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listStandardsApi,
  runComplianceApi,
  listComplianceChecksApi,
  getComplianceCheckApi,
  getSystemStatusApi,
} from '../api/index.js'

const standards = ref([])
const standardId = ref(null)

const systemStatus = ref([])
const statusLoading = ref(false)

const checks = ref([])
const checksLoading = ref(false)

const running = ref(false)

const diffDialogVisible = ref(false)
const checkRow = ref(null)
const checkDetail = ref(null)
const diffs = ref([])
const diffLoading = ref(false)

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}
function sysStatusType(s) {
  if (s === '已落标') return 'success'
  if (s === '有差异') return 'warning'
  if (s === '未接入') return 'info'
  return 'info'
}
function checkStatusType(s) {
  if (s === '完成' || s === '已完成') return 'success'
  if (s === '运行中') return 'primary'
  if (s === '失败') return 'danger'
  return 'info'
}

async function loadStandards() {
  try {
    const { data } = await listStandardsApi()
    standards.value = asList(data)
    if (standards.value.length) {
      standardId.value = standards.value[0].id
      refresh()
    }
  } catch (e) {
    ElMessage.error('标准加载失败')
  }
}

async function loadSystemStatus() {
  if (!standardId.value) return
  statusLoading.value = true
  try {
    const { data } = await getSystemStatusApi({ standard_id: standardId.value })
    systemStatus.value = asList(data)
  } catch (e) {
    ElMessage.error('系统状态加载失败')
  } finally {
    statusLoading.value = false
  }
}

async function loadChecks() {
  checksLoading.value = true
  try {
    const params = {}
    if (standardId.value) params.standard_id = standardId.value
    const { data } = await listComplianceChecksApi(params)
    checks.value = asList(data)
  } catch (e) {
    ElMessage.error('检查记录加载失败')
  } finally {
    checksLoading.value = false
  }
}

function onStandardChange() {
  refresh()
}
function refresh() {
  loadSystemStatus()
  loadChecks()
}

async function doRun() {
  running.value = true
  try {
    const { data } = await runComplianceApi({ standard_id: standardId.value })
    ElMessage.success(`检查完成（ID: ${data?.check_id ?? '-'}），发现 ${data?.diff_count ?? 0} 个差异`)
    refresh()
  } catch (e) {
    ElMessage.error('执行检查失败')
  } finally {
    running.value = false
  }
}

async function openDiffDialog(row) {
  checkRow.value = row
  diffDialogVisible.value = true
  diffLoading.value = true
  try {
    const { data } = await getComplianceCheckApi(row.id)
    checkDetail.value = data || null
    diffs.value = asList(data?.diffs)
  } catch (e) {
    ElMessage.error('差异清单加载失败')
  } finally {
    diffLoading.value = false
  }
}

onMounted(loadStandards)
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  margin: 20px 0 12px;
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.status-card {
  text-align: center;
}
.sys-name {
  font-weight: 600;
  font-size: 14px;
}
.sys-diff {
  font-size: 12px;
  color: #909399;
}
</style>
