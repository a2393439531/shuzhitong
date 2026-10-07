<template>
  <div>
    <el-row :gutter="16" class="stat-row">
      <el-col :span="4" v-for="card in cards" :key="card.key">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ dash[card.key] ?? '-' }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="todo-card">
      <template #header>
        <div class="card-header">
          <span>待审批事项</span>
          <el-button link type="primary" @click="$router.push('/approvals')">查看全部</el-button>
        </div>
      </template>
      <el-table :data="todos" v-loading="loading" empty-text="暂无待审批事项">
        <el-table-column prop="title" label="标题" min-width="220" />
        <el-table-column prop="biz_type" label="业务类型" width="120" />
        <el-table-column prop="applicant" label="申请人" width="120" />
        <el-table-column prop="current_step" label="当前环节" width="140" />
        <el-table-column prop="created_at" label="申请时间" width="170" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push('/approvals?id=' + row.id)">办理</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="ops-card">
      <template #header>
        <div class="card-header">
          <span>运营评价（近 {{ ops.trend_days || 14 }} 天）</span>
          <el-button link type="primary" @click="loadOps">刷新</el-button>
        </div>
      </template>
      <el-row :gutter="16" v-loading="opsLoading">
        <el-col :span="8">
          <div class="ops-title">质量趋势</div>
          <el-table :data="qualityRows" size="small" max-height="220">
            <el-table-column prop="day" label="日期" width="110" />
            <el-table-column prop="detected" label="检出" width="70" />
            <el-table-column prop="closed" label="关闭" width="70" />
          </el-table>
          <div class="ops-foot">未关闭质量问题：<b>{{ ops.quality_trend?.open ?? '-' }}</b></div>
        </el-col>
        <el-col :span="8">
          <div class="ops-title">服务使用 Top5</div>
          <el-table :data="ops.service_usage?.top || []" size="small" max-height="220" empty-text="暂无调用">
            <el-table-column prop="name" label="服务" min-width="140" show-overflow-tooltip />
            <el-table-column prop="calls" label="调用量" width="80" />
            <el-table-column prop="error_rate" label="错误率%" width="90" />
          </el-table>
          <div class="ops-foot">问数使用：<b>{{ ops.qa_usage?.total ?? '-' }}</b> 次，口径命中率 <b>{{ ops.qa_usage?.success_rate ?? '-' }}%</b></div>
        </el-col>
        <el-col :span="8">
          <div class="ops-title">变更统计</div>
          <el-table :data="ops.change_stats?.by_status || []" size="small" max-height="220" empty-text="暂无变更">
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="c" label="数量" width="80" />
          </el-table>
          <div class="ops-foot">已发送变更通知：<b>{{ ops.change_stats?.notices_sent ?? '-' }}</b> 条</div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { dashboardApi, listApprovalsApi, opsOverviewApi } from '../api/index.js'

const dash = ref({})
const todos = ref([])
const loading = ref(false)
const ops = ref({})
const opsLoading = ref(false)

const cards = [
  { key: 'todo_count', label: '待办事项' },
  { key: 'objects_count', label: '业务对象数' },
  { key: 'resources_published', label: '已发布资源' },
  { key: 'standards_published', label: '已发布标准' },
  { key: 'open_issues', label: '未关闭质量问题' },
]

const qualityRows = computed(() => {
  const t = ops.value.quality_trend
  if (!t) return []
  return t.days.map((d, i) => ({ day: d.slice(5), detected: t.detected[i], closed: t.closed[i] })).reverse()
})

async function load() {
  loading.value = true
  try {
    const [{ data: d }, { data: t }] = await Promise.all([
      dashboardApi(),
      listApprovalsApi({ todo: 1 }),
    ])
    dash.value = d
    todos.value = Array.isArray(t) ? t.slice(0, 10) : t.items?.slice(0, 10) || []
  } catch (_) {
    // 保留空状态
  } finally {
    loading.value = false
  }
}

async function loadOps() {
  opsLoading.value = true
  try {
    const { data } = await opsOverviewApi()
    ops.value = data || {}
  } catch (_) {
    // 保留空状态
  } finally {
    opsLoading.value = false
  }
}

onMounted(() => { load(); loadOps() })
</script>

<style scoped>
.stat-row {
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-label {
  font-size: 13px;
  color: #909399;
}
.stat-value {
  font-size: 26px;
  font-weight: 600;
  margin-top: 4px;
}
.todo-card {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.ops-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 14px;
}
.ops-foot {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
</style>
