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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { dashboardApi, listApprovalsApi } from '../api/index.js'

const dash = ref({})
const todos = ref([])
const loading = ref(false)

const cards = [
  { key: 'todo_count', label: '待办事项' },
  { key: 'objects_count', label: '业务对象数' },
  { key: 'resources_published', label: '已发布资源' },
  { key: 'standards_published', label: '已发布标准' },
  { key: 'open_issues', label: '未关闭质量问题' },
]

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

onMounted(load)
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
  font-size: 30px;
  font-weight: bold;
  color: #1f2d3d;
  margin-top: 8px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.todo-card {
  margin-top: 4px;
}
</style>
