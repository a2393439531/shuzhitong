<template>
  <div class="metrics-layout">
    <!-- 左侧指标列表 -->
    <el-card class="left-panel">
      <template #header>
        <div class="panel-header">
          <span>指标列表</span>
          <el-button v-if="auth.isAdmin" link type="primary" @click="openMetricDialog()">新建指标</el-button>
        </div>
      </template>
      <el-input v-model="query" placeholder="指标名称/编码搜索" clearable style="margin-bottom: 12px" @keyup.enter="() => {}" />
      <div class="metric-list" v-loading="listLoading">
        <div
          v-for="m in filteredMetrics"
          :key="m.code"
          class="metric-card"
          :class="{ active: current?.code === m.code }"
          @click="selectMetric(m)"
        >
          <div class="metric-name">{{ m.name }}</div>
          <div class="metric-meta">
            <span>{{ m.code }}</span>
            <el-tag :type="m.status === '已发布' || m.status === 'published' ? 'success' : 'info'" size="small">{{ m.status || '-' }}</el-tag>
          </div>
          <div class="metric-sub">v{{ m.version || '-' }} · {{ m.owner_dept || '' }}</div>
        </div>
        <el-empty v-if="!filteredMetrics.length" description="暂无指标" />
      </div>
    </el-card>

    <!-- 右侧详情 -->
    <el-card class="right-panel" v-loading="detailLoading">
      <el-empty v-if="!current" description="请选择一个指标" />
      <div v-else>
        <div class="detail-header">
          <div>
            <h3 style="margin: 0">{{ current.name }}</h3>
            <div class="code-line">{{ current.code }} · v{{ current.version }}</div>
          </div>
          <el-button v-if="auth.isAdmin" type="primary" @click="openMetricDialog(current)">发布新版本</el-button>
        </div>

        <el-tabs v-model="activeTab">
          <!-- 口径说明 -->
          <el-tab-pane label="口径说明" name="def">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="业务定义" label-width="110px">{{ current.biz_def || '-' }}</el-descriptions-item>
              <el-descriptions-item label="计算规则">{{ current.calc_rule?.description || current.calc_rule || '-' }}</el-descriptions-item>
              <el-descriptions-item label="计算规则详情">
                <pre v-if="calcRuleExtra" class="json-block">{{ calcRuleExtra }}</pre>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="纳入范围">{{ current.scope_include || '-' }}</el-descriptions-item>
              <el-descriptions-item label="排除范围">{{ current.scope_exclude || '-' }}</el-descriptions-item>
              <el-descriptions-item label="时间规则">{{ current.time_rule || '-' }}</el-descriptions-item>
              <el-descriptions-item label="统计粒度">{{ current.granularity || '-' }}</el-descriptions-item>
              <el-descriptions-item label="维度">{{ (current.dimensions || []).join('、') || '-' }}</el-descriptions-item>
              <el-descriptions-item label="数据来源">{{ (current.data_sources || []).join('、') || current.data_sources || '-' }}</el-descriptions-item>
              <el-descriptions-item label="责任部门">{{ current.owner_dept || '-' }}</el-descriptions-item>
              <el-descriptions-item label="责任角色">{{ current.owner_role || '-' }}</el-descriptions-item>
              <el-descriptions-item label="当前版本">{{ current.version || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <!-- 趋势图 -->
          <el-tab-pane label="趋势分析" name="trend">
            <div class="filter-bar">
              <el-input v-model="trendDimValue" placeholder="维度值（可选）" clearable style="width: 200px" />
              <el-button type="primary" @click="loadTrend">查询</el-button>
            </div>
            <div ref="trendChartRef" class="chart" v-loading="trendLoading"></div>
          </el-tab-pane>

          <!-- 版本对比 -->
          <el-tab-pane label="版本对比" name="compare">
            <div class="filter-bar">
              <el-select v-model="cmpFrom" placeholder="基准版本" style="width: 160px" clearable>
                <el-option v-for="v in versions" :key="v.version" :label="'v' + v.version" :value="v.version" />
              </el-select>
              <span>→</span>
              <el-select v-model="cmpTo" placeholder="对比版本" style="width: 160px" clearable>
                <el-option v-for="v in versions" :key="v.version" :label="'v' + v.version" :value="v.version" />
              </el-select>
              <el-button type="primary" @click="doCompare" :disabled="!cmpFrom || !cmpTo">对比</el-button>
            </div>
            <el-alert v-if="compareResult?.has_caliber_diff" type="warning" title="口径存在差异" description="两个版本的指标口径定义存在差异，引用前请确认适用口径。" show-icon style="margin-bottom: 12px" />
            <el-table :data="compareResult?.diff || []">
              <el-table-column prop="field" label="字段" width="180" />
              <el-table-column prop="from" label="基准版本" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ fmtVal(row.from) }}</template>
              </el-table-column>
              <el-table-column prop="to" label="对比版本" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ fmtVal(row.to) }}</template>
              </el-table-column>
            </el-table>
            <h4 class="sec-title">版本历史</h4>
            <el-table :data="versions" size="small">
              <el-table-column prop="version" label="版本" width="100" />
              <el-table-column prop="change_desc" label="变更说明" min-width="220" show-overflow-tooltip />
              <el-table-column prop="created_at" label="创建时间" width="170" />
            </el-table>
          </el-tab-pane>

          <!-- 指标计算 -->
          <el-tab-pane label="指标计算" name="compute">
            <div class="filter-bar">
              <el-date-picker v-model="computeForm.period_start" type="month" placeholder="开始月份" value-format="YYYY-MM" style="width: 150px" />
              <el-date-picker v-model="computeForm.period_end" type="month" placeholder="结束月份" value-format="YYYY-MM" style="width: 150px" />
              <el-input v-model="computeForm.dimension" placeholder="维度（可选）" clearable style="width: 150px" />
              <el-input v-model="computeForm.dimension_value" placeholder="维度值（可选）" clearable style="width: 150px" />
              <el-button type="primary" @click="doCompute" :loading="computing">计算</el-button>
            </div>
            <el-card v-if="computeResult" shadow="never" class="compute-card">
              <div class="compute-value">
                {{ computeResult.value }}
                <el-tag v-if="computeResult.cached" type="info" size="small" style="margin-left: 8px">缓存命中</el-tag>
              </div>
              <el-descriptions :column="2" border size="small" style="margin-top: 12px">
                <el-descriptions-item label="分子">{{ computeResult.numerator ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="分母">{{ computeResult.denominator ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="口径版本">{{ computeResult.version ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="统计周期">{{ computeResult.period ?? '-' }}</el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>

    <!-- 新建/新版本 dialog -->
    <el-dialog v-model="metricDialogVisible" :title="editingMetric ? '发布新版本' : '新建指标'" width="620px">
      <el-form :model="metricForm" label-width="110px">
        <el-form-item label="指标编码"><el-input v-model="metricForm.code" :disabled="!!editingMetric" /></el-form-item>
        <el-form-item label="指标名称"><el-input v-model="metricForm.name" :disabled="!!editingMetric" /></el-form-item>
        <el-form-item label="业务定义"><el-input v-model="metricForm.biz_def" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="计算规则描述"><el-input v-model="metricForm.calc_description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="统计粒度"><el-input v-model="metricForm.granularity" placeholder="如：月 / 日" /></el-form-item>
        <el-form-item label="维度（逗号分隔）"><el-input v-model="metricForm.dimensions" placeholder="如：机组,部门" /></el-form-item>
        <el-form-item label="责任部门"><el-input v-model="metricForm.owner_dept" /></el-form-item>
        <el-form-item label="变更说明" v-if="editingMetric">
          <el-input v-model="metricForm.change_desc" type="textarea" :rows="2" placeholder="本次版本变更说明（必填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metricDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitMetric" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { auth } from '../store/auth.js'
import {
  listMetricsApi, getMetricApi, createMetricApi, updateMetricApi,
  computeMetricApi, getMetricTrendApi, listMetricVersionsApi, compareMetricVersionsApi,
} from '../api/index.js'

const submitting = ref(false)
const activeTab = ref('def')

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}

// ---------- 列表 ----------
const metrics = ref([])
const listLoading = ref(false)
const query = ref('')

const filteredMetrics = computed(() => {
  const q = query.value.trim()
  if (!q) return metrics.value
  return metrics.value.filter((m) => (m.name || '').includes(q) || (m.code || '').includes(q))
})

async function loadMetrics() {
  listLoading.value = true
  try {
    const { data } = await listMetricsApi()
    metrics.value = asList(data)
  } catch (e) {
    ElMessage.error('指标列表加载失败')
  } finally {
    listLoading.value = false
  }
}

// ---------- 详情 ----------
const current = ref(null)
const detailLoading = ref(false)

const calcRuleExtra = computed(() => {
  const cr = current.value?.calc_rule
  if (!cr || typeof cr !== 'object') return ''
  const rest = { ...cr }
  delete rest.description
  return Object.keys(rest).length ? JSON.stringify(rest, null, 2) : ''
})

async function selectMetric(m) {
  detailLoading.value = true
  try {
    const { data } = await getMetricApi(m.code)
    current.value = data
    cmpFrom.value = ''
    cmpTo.value = ''
    compareResult.value = null
    computeResult.value = null
    trendDimValue.value = ''
    loadVersions()
  } catch (e) {
    ElMessage.error('指标详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

// ---------- 版本 ----------
const versions = ref([])
const cmpFrom = ref('')
const cmpTo = ref('')
const compareResult = ref(null)

async function loadVersions() {
  if (!current.value) return
  try {
    const { data } = await listMetricVersionsApi(current.value.code)
    versions.value = asList(data)
  } catch (_) {
    versions.value = []
  }
}

function fmtVal(v) {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function doCompare() {
  try {
    const { data } = await compareMetricVersionsApi(current.value.code, { from: cmpFrom.value, to: cmpTo.value })
    compareResult.value = data
  } catch (e) {
    ElMessage.error('版本对比失败')
  }
}

// ---------- 趋势 ----------
const trendChartRef = ref(null)
const trendLoading = ref(false)
const trendDimValue = ref('')
let chart = null

function disposeChart() {
  if (chart) {
    chart.dispose()
    chart = null
  }
}

async function loadTrend() {
  if (!current.value) return
  trendLoading.value = true
  try {
    const params = { months: 12 }
    if (trendDimValue.value) params.dimension_value = trendDimValue.value
    const { data } = await getMetricTrendApi(current.value.code, params)
    const list = asList(data)
    await nextTick()
    disposeChart()
    chart = echarts.init(trendChartRef.value)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: list.map((p) => p.period) },
      yAxis: { type: 'value' },
      series: [
        {
          name: current.value.name,
          type: 'line',
          smooth: true,
          data: list.map((p) => p.value),
          lineStyle: { width: 2 },
          itemStyle: { color: '#409eff' },
          areaStyle: { opacity: 0.12 },
        },
      ],
    })
  } catch (e) {
    ElMessage.error('趋势数据加载失败')
  } finally {
    trendLoading.value = false
  }
}

function onResize() {
  chart?.resize()
}

// ---------- 计算 ----------
const computeForm = reactive({ period_start: '', period_end: '', dimension: '', dimension_value: '' })
const computeResult = ref(null)
const computing = ref(false)

async function doCompute() {
  if (!computeForm.period_start || !computeForm.period_end) {
    ElMessage.warning('请选择开始与结束月份')
    return
  }
  computing.value = true
  try {
    const body = { period_start: computeForm.period_start, period_end: computeForm.period_end }
    if (computeForm.dimension) body.dimension = computeForm.dimension
    if (computeForm.dimension_value) body.dimension_value = computeForm.dimension_value
    const { data } = await computeMetricApi(current.value.code, body)
    computeResult.value = data
  } catch (e) {
    ElMessage.error('指标计算失败')
  } finally {
    computing.value = false
  }
}

// ---------- 新建 / 新版本 ----------
const metricDialogVisible = ref(false)
const editingMetric = ref(null)
const metricForm = reactive({
  code: '', name: '', biz_def: '', calc_description: '',
  granularity: '', dimensions: '', owner_dept: '', change_desc: '',
})

function openMetricDialog(row) {
  editingMetric.value = row || null
  Object.assign(metricForm, {
    code: row?.code || '',
    name: row?.name || '',
    biz_def: row?.biz_def || '',
    calc_description: row?.calc_rule?.description || '',
    granularity: row?.granularity || '',
    dimensions: Array.isArray(row?.dimensions) ? row.dimensions.join(',') : (row?.dimensions || ''),
    owner_dept: row?.owner_dept || '',
    change_desc: '',
  })
  metricDialogVisible.value = true
}

async function submitMetric() {
  if (!metricForm.code || !metricForm.name) {
    ElMessage.warning('请填写指标编码和名称')
    return
  }
  if (editingMetric.value && !metricForm.change_desc) {
    ElMessage.warning('请填写变更说明')
    return
  }
  const body = {
    code: metricForm.code,
    name: metricForm.name,
    biz_def: metricForm.biz_def,
    granularity: metricForm.granularity,
    owner_dept: metricForm.owner_dept,
    dimensions: metricForm.dimensions ? metricForm.dimensions.split(/[,，]/).map((s) => s.trim()).filter(Boolean) : [],
    calc_rule: { description: metricForm.calc_description },
  }
  if (editingMetric.value) body.change_desc = metricForm.change_desc
  submitting.value = true
  try {
    if (editingMetric.value) {
      await updateMetricApi(editingMetric.value.code, body)
      ElMessage.success('新版本已发布')
      selectMetric({ code: editingMetric.value.code })
    } else {
      await createMetricApi(body)
      ElMessage.success('指标已创建')
    }
    metricDialogVisible.value = false
    loadMetrics()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadMetrics()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  disposeChart()
})
</script>

<style scoped>
.metrics-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.left-panel {
  width: 300px;
  flex-shrink: 0;
}
.right-panel {
  flex: 1;
  min-width: 0;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.metric-list {
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metric-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.metric-card:hover {
  border-color: #a0cfff;
}
.metric-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.metric-name {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
}
.metric-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #909399;
}
.metric-sub {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 4px;
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.code-line {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.chart {
  width: 100%;
  height: 340px;
}
.sec-title {
  margin: 18px 0 10px;
  font-size: 14px;
}
.json-block {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.compute-card {
  max-width: 640px;
}
.compute-value {
  font-size: 40px;
  font-weight: bold;
  color: #409eff;
}
</style>
