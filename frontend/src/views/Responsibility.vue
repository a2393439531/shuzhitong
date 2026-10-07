<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-select
          v-model="selectedObjectId"
          placeholder="选择业务对象"
          filterable
          clearable
          style="width: 280px"
          @change="loadAll"
        >
          <el-option
            v-for="o in objects"
            :key="o.id"
            :label="`${o.name}（${o.code}）`"
            :value="o.id"
          />
        </el-select>
        <el-button type="primary" @click="loadAll" :disabled="!selectedObjectId">加载</el-button>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="字段—流程—责任矩阵" name="matrix">
          <el-table :data="matrix" v-loading="loading" empty-text="请先选择业务对象">
            <el-table-column prop="field_name" label="字段" width="170" fixed />
            <el-table-column prop="process_name" label="关联流程" width="200" />
            <el-table-column prop="business_owner_dept" label="业务归口部门" width="150" />
            <el-table-column prop="authority_source" label="权威来源" min-width="160" />
            <el-table-column prop="input_role" label="录入角色" width="130" />
            <el-table-column prop="review_role" label="审核角色" width="130" />
            <el-table-column prop="data_steward" label="数据管家" width="130" />
            <el-table-column prop="tech_owner" label="技术负责人" width="130" />
            <el-table-column prop="org_unit" label="组织单元" width="130" />
            <el-table-column prop="agent_for" label="代办说明" min-width="150" />
            <el-table-column label="有效期" width="230">
              <template #default="{ row }">{{ row.valid_from || '-' }} ~ {{ row.valid_to || '-' }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="质量问题" name="issues">
          <div class="filter-bar">
            <el-select v-model="issueStatus" placeholder="状态筛选" clearable style="width: 160px">
              <el-option label="待整改" value="待整改" />
              <el-option label="整改中" value="整改中" />
              <el-option label="已关闭" value="已关闭" />
            </el-select>
            <el-button type="primary" @click="loadIssues">搜索</el-button>
            <el-button @click="issueDialogVisible = true">新增问题</el-button>
          </div>
          <el-table :data="issues" v-loading="issueLoading" empty-text="请先选择业务对象">
            <el-table-column prop="title" label="标题" min-width="220" />
            <el-table-column prop="issue_type" label="问题类型" width="130" />
            <el-table-column prop="assignee" label="责任人" width="120" />
            <el-table-column prop="status" label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.status === '已关闭' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="170" />
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button link type="primary" :disabled="row.status === '已关闭'" @click="updateIssue(row, '整改中')">
                  整改
                </el-button>
                <el-button link type="success" :disabled="row.status === '已关闭'" @click="updateIssue(row, '已关闭')">
                  关闭
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新增质量问题弹窗 -->
    <el-dialog v-model="issueDialogVisible" title="新增质量问题" width="520px">
      <el-form :model="issueForm" label-width="100px">
        <el-form-item label="标题"><el-input v-model="issueForm.title" /></el-form-item>
        <el-form-item label="问题类型">
          <el-select v-model="issueForm.issue_type" style="width: 100%">
            <el-option label="完整性" value="完整性" />
            <el-option label="准确性" value="准确性" />
            <el-option label="一致性" value="一致性" />
            <el-option label="及时性" value="及时性" />
            <el-option label="唯一性" value="唯一性" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任人"><el-input v-model="issueForm.assignee" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="issueForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="issueDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveIssue">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listObjectsApi,
  listResponsibilitiesApi,
  listProcessesApi,
  listQualityApi,
  createQualityApi,
  updateQualityApi,
} from '../api/index.js'

const objects = ref([])
const selectedObjectId = ref('')
const activeTab = ref('matrix')
const loading = ref(false)
const matrix = ref([])

const issueStatus = ref('')
const issues = ref([])
const issueLoading = ref(false)
const issueDialogVisible = ref(false)
const issueForm = reactive({ title: '', issue_type: '', assignee: '', description: '' })

async function loadAll() {
  if (!selectedObjectId.value) return
  await Promise.all([loadMatrix(), loadIssues()])
}

async function loadMatrix() {
  loading.value = true
  try {
    const [{ data: resp }, { data: procs }] = await Promise.all([
      listResponsibilitiesApi({ object_id: selectedObjectId.value }),
      listProcessesApi().catch(() => ({ data: [] })),
    ])
    const rows = Array.isArray(resp) ? resp : resp.items || []
    const procList = Array.isArray(procs) ? procs : procs.items || []
    const procName = (id) => procList.find((p) => p.id === id)?.name || id || '-'
    matrix.value = rows.map((r) => ({ ...r, process_name: procName(r.source_process_id) }))
  } catch (_) {
    ElMessage.error('加载责任矩阵失败')
  } finally {
    loading.value = false
  }
}

async function loadIssues() {
  if (!selectedObjectId.value) return
  issueLoading.value = true
  try {
    const params = { object_id: selectedObjectId.value }
    if (issueStatus.value) params.status = issueStatus.value
    const { data } = await listQualityApi(params)
    issues.value = Array.isArray(data) ? data : data.items || []
  } catch (_) {
    ElMessage.error('加载质量问题失败')
  } finally {
    issueLoading.value = false
  }
}

async function updateIssue(row, status) {
  try {
    await updateQualityApi(row.id, { status })
    ElMessage.success(status === '已关闭' ? '问题已关闭' : '已转入整改')
    loadIssues()
  } catch (_) {
    ElMessage.error('操作失败')
  }
}

async function saveIssue() {
  if (!issueForm.title) {
    ElMessage.warning('请填写标题')
    return
  }
  try {
    await createQualityApi({ ...issueForm, object_id: selectedObjectId.value })
    ElMessage.success('新增成功')
    issueDialogVisible.value = false
    Object.assign(issueForm, { title: '', issue_type: '', assignee: '', description: '' })
    loadIssues()
  } catch (_) {
    ElMessage.error('新增失败')
  }
}

onMounted(async () => {
  const { data } = await listObjectsApi({})
  objects.value = Array.isArray(data) ? data : data.items || []
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
</style>
