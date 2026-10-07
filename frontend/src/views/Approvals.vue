<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card>
          <template #header><span class="card-title">待办审批</span></template>
          <el-table :data="approvals" v-loading="loading" highlight-current-row @current-change="onSelect">
            <el-table-column prop="title" label="标题" min-width="200" />
            <el-table-column prop="biz_type" label="业务类型" width="110" />
            <el-table-column prop="applicant" label="申请人" width="100" />
            <el-table-column prop="current_step" label="当前环节" width="120" />
            <el-table-column prop="created_at" label="申请时间" width="160" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card v-if="detail" v-loading="detailLoading">
          <template #header><span class="card-title">审批详情：{{ detail.approval?.title }}</span></template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="业务类型">{{ detail.approval?.biz_type }}</el-descriptions-item>
            <el-descriptions-item label="申请人">{{ detail.approval?.applicant }}</el-descriptions-item>
            <el-descriptions-item label="当前状态">{{ detail.approval?.status }}</el-descriptions-item>
            <el-descriptions-item label="申请时间">{{ detail.approval?.created_at }}</el-descriptions-item>
          </el-descriptions>

          <div class="section-title">审批步骤</div>
          <el-timeline>
            <el-timeline-item
              v-for="s in detail.steps"
              :key="s.seq"
              :timestamp="s.acted_at || ''"
              :type="stepType(s.decision)"
            >
              <div class="step-name">{{ s.step_name }}（{{ s.approver_role }}）</div>
              <div class="step-info">
                审批人：{{ s.approver || '待审批' }}　
                结论：{{ s.decision || '未处理' }}
              </div>
              <div class="step-comment" v-if="s.comment">意见：{{ s.comment }}</div>
            </el-timeline-item>
          </el-timeline>

          <div class="section-title">审批操作</div>
          <el-form :model="decideForm" label-width="80px">
            <el-form-item label="审批意见">
              <el-input v-model="decideForm.comment" type="textarea" :rows="3" placeholder="请输入审批意见" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" @click="decide('通过')">通过</el-button>
              <el-button type="danger" @click="decide('驳回')">驳回</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <el-card v-else>
          <el-empty description="请选择一条待办查看详情" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listApprovalsApi, getApprovalApi, decideApprovalApi } from '../api/index.js'

const route = useRoute()
const approvals = ref([])
const loading = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const decideForm = reactive({ comment: '' })

function stepType(decision) {
  if (decision === '通过') return 'success'
  if (decision === '驳回') return 'danger'
  return 'primary'
}

async function loadApprovals() {
  loading.value = true
  try {
    const { data } = await listApprovalsApi({ todo: 1 })
    approvals.value = Array.isArray(data) ? data : data.items || []
    // 支持从仪表盘带 id 跳转
    const targetId = route.query.id
    if (targetId) {
      const row = approvals.value.find((a) => String(a.id) === String(targetId))
      if (row) onSelect(row)
    }
  } finally {
    loading.value = false
  }
}

async function onSelect(row) {
  if (!row) return
  detailLoading.value = true
  try {
    const { data } = await getApprovalApi(row.id)
    detail.value = data
    decideForm.comment = ''
  } catch (_) {
    ElMessage.error('加载审批详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function decide(decision) {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(`确定${decision}该申请吗？`, '提示', { type: 'warning' })
    await decideApprovalApi(detail.value.approval.id, decision, decideForm.comment)
    ElMessage.success(`已${decision}`)
    detail.value = null
    loadApprovals()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

onMounted(loadApprovals)
</script>

<style scoped>
.card-title {
  font-weight: 600;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  margin: 20px 0 12px;
}
.step-name {
  font-weight: 600;
}
.step-info {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}
.step-comment {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}
</style>
