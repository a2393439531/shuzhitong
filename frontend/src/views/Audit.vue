<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-input
          v-model="query.username"
          placeholder="用户名筛选"
          clearable
          style="width: 220px"
          @keyup.enter="loadAudit(1)"
        />
        <el-input
          v-model="query.action"
          placeholder="操作筛选"
          clearable
          style="width: 220px"
          @keyup.enter="loadAudit(1)"
        />
        <el-button type="primary" @click="loadAudit(1)">搜索</el-button>
      </div>
      <el-table :data="items" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="action" label="操作" width="180" />
        <el-table-column prop="detail" label="详情" min-width="240" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
      <el-pagination
        class="pager"
        background
        layout="total, prev, pager, next, sizes"
        :total="total"
        :page-size="query.page_size"
        :current-page="query.page"
        :page-sizes="[10, 20, 50]"
        @current-change="(p) => loadAudit(p)"
        @size-change="(s) => { query.page_size = s; loadAudit(1) }"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { listAuditApi } from '../api/index.js'

const items = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ username: '', action: '', page: 1, page_size: 20 })

async function loadAudit(page) {
  if (page) query.page = page
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size }
    if (query.username) params.username = query.username
    if (query.action) params.action = query.action
    const { data } = await listAuditApi(params)
    total.value = data.total || 0
    items.value = data.items || []
  } finally {
    loading.value = false
  }
}

onMounted(() => loadAudit(1))
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
