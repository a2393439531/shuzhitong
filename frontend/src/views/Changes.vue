<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="9">
        <el-card>
          <template #header>
            <div class="card-header">
              <span class="card-title">变更申请</span>
              <el-button type="primary" size="small" @click="showCreate = true">新建申请</el-button>
            </div>
          </template>
          <el-table :data="changes" v-loading="loading" highlight-current-row @current-change="onSelect">
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="change_type" label="类型" width="90" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="created_at" label="申请时间" width="150" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="15">
        <el-card v-if="detail" v-loading="detailLoading">
          <template #header><span class="card-title">{{ detail.title }}</span></template>
          <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
            <el-descriptions-item label="类型">{{ detail.change_type }}</el-descriptions-item>
            <el-descriptions-item label="目标">{{ detail.target_code || detail.target_id }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ detail.version_from || '-' }} → {{ detail.version_to || '-' }}</el-descriptions-item>
            <el-descriptions-item label="状态"><el-tag :type="statusType(detail.status)" size="small">{{ detail.status }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="申请人">{{ detail.applicant }}</el-descriptions-item>
            <el-descriptions-item label="生效时间">{{ detail.effective_at || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div class="sec-title">变更说明</div>
          <div class="sec-text">{{ detail.change_desc || '-' }}</div>

          <div class="sec-title">影响分析（{{ detail.impacts?.length || 0 }} 项）</div>
          <el-table :data="detail.impacts" size="small" empty-text="提交后自动生成影响分析">
            <el-table-column prop="category" label="类别" width="90" />
            <el-table-column prop="ref_desc" label="受影响资产" min-width="180" show-overflow-tooltip />
            <el-table-column prop="action_needed" label="需采取的行动" min-width="200" show-overflow-tooltip />
          </el-table>

          <div class="sec-title">责任人确认（{{ confirmedCount }}/{{ detail.confirmations?.length || 0 }}）</div>
          <el-table :data="detail.confirmations" size="small" empty-text="暂无确认项">
            <el-table-column prop="confirmer" label="确认人" width="120" />
            <el-table-column prop="confirm_role" label="责任说明" min-width="180" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }"><el-tag :type="row.status === '已确认' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="comment" label="意见" min-width="120" />
          </el-table>

          <div class="sec-title" v-if="detail.notices?.length">变更通知（{{ detail.notices.length }} 条）</div>
          <el-table v-if="detail.notices?.length" :data="detail.notices" size="small">
            <el-table-column prop="audience" label="受众" width="90" />
            <el-table-column prop="recipient" label="接收人" width="120" />
            <el-table-column prop="content" label="内容" min-width="220" show-overflow-tooltip />
            <el-table-column prop="sent_at" label="发送时间" width="150" />
          </el-table>

          <div class="sec-title">操作</div>
          <el-space wrap>
            <el-button v-if="detail.status === '草稿'" type="primary" @click="doSubmit">提交并分析影响</el-button>
            <el-button v-if="detail.status === '待确认'" type="success" @click="doConfirm">确认（本人/代确认）</el-button>
            <el-button v-if="detail.status === '待确认'" type="warning" @click="doEffect">生效</el-button>
            <el-button v-if="detail.status === '待确认' || detail.status === '草稿'" type="danger" @click="doReject">驳回</el-button>
            <el-button v-if="detail.status === '已生效'" type="info" @click="doRollback">一键回退</el-button>
          </el-space>
          <el-form v-if="detail.status === '待确认'" :model="confirmForm" label-width="70px" style="margin-top: 8px; max-width: 420px">
            <el-form-item label="确认意见"><el-input v-model="confirmForm.comment" placeholder="可选" /></el-form-item>
          </el-form>
        </el-card>
        <el-card v-else><el-empty description="请选择一条变更申请" /></el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showCreate" title="新建变更申请" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="变更类型">
          <el-select v-model="form.change_type" style="width: 100%">
            <el-option label="标准版本" value="标准版本" />
            <el-option label="指标口径" value="指标口径" />
            <el-option label="服务接口" value="服务接口" />
            <el-option label="主数据模型" value="主数据模型" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标ID"><el-input-number v-model="form.target_id" :min="1" style="width: 100%" /></el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="新版本号"><el-input v-model="form.version_to" placeholder="如 v1.1" /></el-form-item>
        <el-form-item label="变更说明"><el-input v-model="form.change_desc" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createChange">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listChangesApi, createChangeApi, getChangeApi, submitChangeApi,
  confirmChangeApi, effectChangeApi, rejectChangeApi, rollbackChangeApi,
} from '../api/index.js'

const changes = ref([])
const loading = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const showCreate = ref(false)
const confirmForm = ref({ comment: '' })
const form = ref({ change_type: '标准版本', target_id: 1, title: '', version_to: '', change_desc: '' })

const confirmedCount = computed(() => (detail.value?.confirmations || []).filter(c => c.status === '已确认').length)

function statusType(s) {
  return { '草稿': 'info', '影响分析中': 'warning', '待确认': 'warning', '已生效': 'success', '已回退': '', '已驳回': 'danger' }[s] || 'info'
}

async function load() {
  loading.value = true
  try {
    const { data } = await listChangesApi()
    changes.value = data || []
  } finally { loading.value = false }
}

async function onSelect(row) {
  if (!row) return
  detailLoading.value = true
  try {
    const { data } = await getChangeApi(row.id)
    detail.value = data
  } finally { detailLoading.value = false }
}

async function refresh() { await load(); if (detail.value) onSelect({ id: detail.value.id }) }

async function createChange() {
  try {
    await createChangeApi(form.value)
    ElMessage.success('变更申请已创建')
    showCreate.value = false
    form.value = { change_type: '标准版本', target_id: 1, title: '', version_to: '', change_desc: '' }
    refresh()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '创建失败') }
}

async function doSubmit() {
  try {
    const { data } = await submitChangeApi(detail.value.id)
    detail.value = data
    ElMessage.success(`影响分析完成：${data.impacts.length} 项影响，${data.confirmations.length} 人待确认`)
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '提交失败') }
}

async function doConfirm() {
  try {
    await confirmChangeApi(detail.value.id, { comment: confirmForm.value.comment })
    ElMessage.success('已确认')
    confirmForm.value.comment = ''
    refresh()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '确认失败') }
}

async function doEffect() {
  try {
    await ElMessageBox.confirm('确认使变更生效吗？将写入新版本并通知相关方。', '提示', { type: 'warning' })
  } catch { return }
  try {
    const { data } = await effectChangeApi(detail.value.id)
    detail.value = data
    ElMessage.success(`已生效，通知 ${data.notices.length} 条`)
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '生效失败') }
}

async function doReject() {
  try {
    await rejectChangeApi(detail.value.id, {})
    ElMessage.success('已驳回')
    refresh()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '驳回失败') }
}

async function doRollback() {
  try {
    await ElMessageBox.confirm('确认回退到变更前版本吗？', '提示', { type: 'warning' })
  } catch { return }
  try {
    const { data } = await rollbackChangeApi(detail.value.id)
    detail.value = data
    ElMessage.success('已回退')
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '回退失败') }
}

onMounted(load)
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-weight: 600; }
.sec-title { font-weight: 600; margin: 14px 0 8px; }
.sec-text { color: #606266; font-size: 13px; }
</style>
