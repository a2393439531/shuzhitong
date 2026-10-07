<template>
  <div>
    <el-card>
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 规则管理 -->
        <el-tab-pane label="规则管理" name="rules">
          <div class="filter-bar">
            <el-input v-model="ruleQuery.q" placeholder="规则名称关键字" clearable style="width: 220px" @keyup.enter="loadRules" />
            <el-button type="primary" @click="loadRules">搜索</el-button>
            <el-button @click="openRuleDialog()">新增规则</el-button>
            <el-button type="warning" @click="runAll" :loading="runningAll">全部执行</el-button>
          </div>
          <el-table :data="rules" v-loading="rulesLoading">
            <el-table-column prop="name" label="规则名称" min-width="180" />
            <el-table-column prop="object_name" label="业务对象" width="130" />
            <el-table-column prop="target_table" label="目标表" width="150" show-overflow-tooltip />
            <el-table-column prop="target_field" label="目标字段" width="140" show-overflow-tooltip />
            <el-table-column prop="rule_type" label="规则类型" width="120" />
            <el-table-column prop="severity" label="严重程度" width="100">
              <template #default="{ row }"><el-tag :type="severityType(row.severity)" size="small">{{ row.severity || '-' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="assignee_type" label="派发对象" width="140" />
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-switch :model-value="!!row.is_enabled" @change="() => toggleRule(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="runOne(row)" :loading="row._running">运行</el-button>
                <el-button link type="primary" size="small" @click="openRuleDialog(row)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeRule(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 执行记录 -->
        <el-tab-pane label="执行记录" name="runs">
          <el-table :data="runs" v-loading="runsLoading">
            <el-table-column prop="id" label="执行ID" width="90" />
            <el-table-column prop="rule_name" label="规则" min-width="180" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="issue_count" label="问题数" width="90" />
            <el-table-column prop="started_at" label="开始时间" width="170" />
            <el-table-column prop="finished_at" label="结束时间" width="170" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openRunDetail(row)">查看问题</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 问题整改 -->
        <el-tab-pane label="问题整改" name="issues">
          <div class="filter-bar">
            <el-select v-model="issueQuery.status" placeholder="状态筛选" clearable style="width: 160px">
              <el-option v-for="s in issueStatuses" :key="s" :label="s" :value="s" />
            </el-select>
            <el-button type="primary" @click="loadIssues">搜索</el-button>
          </div>
          <el-table :data="issues" v-loading="issuesLoading">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="title" label="问题标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="issue_type" label="类型" width="110" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }"><el-tag :type="issueStatusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="assignee" label="派发给" width="120" show-overflow-tooltip />
            <el-table-column prop="lead_assignee" label="整改牵头人" width="120" show-overflow-tooltip />
            <el-table-column prop="record_ref" label="问题记录" width="150" show-overflow-tooltip />
            <el-table-column prop="created_at" label="创建时间" width="160" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === '待确认'" link type="primary" size="small" @click="openConfirmDialog(row)">确认</el-button>
                <el-button v-if="row.status === '已确认'" link type="primary" size="small" @click="openFixDialog(row)">整改</el-button>
                <el-button v-if="row.status === '整改中'" link type="primary" size="small" @click="doRecheck(row)">重新检测</el-button>
                <el-button v-if="row.status === '待复核'" link type="primary" size="small" @click="openCloseDialog(row)">关闭</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 定时计划 -->
        <el-tab-pane label="定时计划" name="schedules">
          <div class="filter-bar">
            <el-button @click="openScheduleDialog">新增计划</el-button>
            <el-button type="warning" @click="triggerDue" :loading="triggering">立即触发到期计划</el-button>
          </div>
          <el-table :data="schedules" v-loading="schedulesLoading">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="rule_name" label="规则" min-width="180" show-overflow-tooltip />
            <el-table-column prop="cron_expr" label="Cron 表达式" width="160" />
            <el-table-column label="启用" width="90">
              <template #default="{ row }"><el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '启用' : '停用' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="last_triggered_at" label="上次触发" width="170" />
            <el-table-column prop="next_run_at" label="下次运行" width="170" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 规则 dialog -->
    <el-dialog v-model="ruleDialogVisible" :title="editingRule ? '编辑规则' : '新增规则'" width="560px">
      <el-form :model="ruleForm" label-width="100px">
        <el-form-item label="规则名称"><el-input v-model="ruleForm.name" /></el-form-item>
        <el-form-item label="业务对象">
          <el-select v-model="ruleForm.object_id" clearable placeholder="请选择" style="width: 100%">
            <el-option v-for="o in objects" :key="o.id" :label="`${o.code || ''} ${o.name || ''}`" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标表"><el-input v-model="ruleForm.target_table" placeholder="如 EQ_EQUIPMENT" /></el-form-item>
        <el-form-item label="目标字段"><el-input v-model="ruleForm.target_field" placeholder="如 SAFETY_LEVEL" /></el-form-item>
        <el-form-item label="规则类型">
          <el-select v-model="ruleForm.rule_type" style="width: 100%">
            <el-option v-for="t in ruleTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="ruleForm.severity" style="width: 100%">
            <el-option v-for="s in ['高', '中', '低']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="派发对象">
          <el-select v-model="ruleForm.assignee_type" style="width: 100%">
            <el-option v-for="t in assigneeTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否启用"><el-switch v-model="ruleForm.is_enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitRule" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 执行结果 dialog -->
    <el-dialog v-model="runDetailVisible" title="执行问题清单" width="640px">
      <el-table :data="runIssues" v-loading="runDetailLoading">
        <el-table-column prop="title" label="问题标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="assignee" label="派发给" width="140" />
        <el-table-column prop="record_ref" label="问题记录" width="160" show-overflow-tooltip />
      </el-table>
    </el-dialog>

    <!-- 问题确认 -->
    <el-dialog v-model="confirmDialogVisible" title="确认问题" width="480px">
      <el-form label-width="110px">
        <el-form-item label="问题">{{ confirmRow?.title }}</el-form-item>
        <el-form-item label="整改牵头人"><el-input v-model="confirmLead" placeholder="指定整改牵头人" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitConfirm" :loading="submitting">确认</el-button>
      </template>
    </el-dialog>

    <!-- 问题整改 -->
    <el-dialog v-model="fixDialogVisible" title="提交整改" width="520px">
      <el-form label-width="110px">
        <el-form-item label="问题">{{ fixRow?.title }}</el-form-item>
        <el-form-item label="根本原因"><el-input v-model="fixForm.root_cause" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="整改说明"><el-input v-model="fixForm.fix_desc" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fixDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFix" :loading="submitting">提交</el-button>
      </template>
    </el-dialog>

    <!-- 关闭问题 -->
    <el-dialog v-model="closeDialogVisible" title="关闭问题" width="480px">
      <el-form label-width="110px">
        <el-form-item label="问题">{{ closeRow?.title }}</el-form-item>
        <el-form-item label="复核意见"><el-input v-model="closeComment" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitClose" :loading="submitting">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 定时计划 dialog -->
    <el-dialog v-model="scheduleDialogVisible" title="新增定时计划" width="500px">
      <el-form :model="scheduleForm" label-width="100px">
        <el-form-item label="质量规则">
          <el-select v-model="scheduleForm.rule_id" placeholder="请选择" style="width: 100%">
            <el-option v-for="r in rules" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Cron 表达式"><el-input v-model="scheduleForm.cron_expr" placeholder="如 0 2 * * *（每天2点）" /></el-form-item>
        <el-form-item label="是否启用"><el-switch v-model="scheduleForm.is_enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitSchedule" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listQualityRulesApi,
  createQualityRuleApi,
  updateQualityRuleApi,
  deleteQualityRuleApi,
  toggleQualityRuleApi,
  runQualityRuleApi,
  runAllQualityRulesApi,
  listQualityRunsApi,
  getQualityRunApi,
  listQualitySchedulesApi,
  createQualityScheduleApi,
  triggerDueSchedulesApi,
  listQualityApi,
  confirmIssueApi,
  fixIssueApi,
  recheckIssueApi,
  closeIssueApi,
  listObjectsApi,
} from '../api/index.js'

const activeTab = ref('rules')
const submitting = ref(false)
const objects = ref([])

const ruleTypes = ['完整性', '唯一性', '有效性', '一致性', '及时性', '关联完整性']
const assigneeTypes = ['业务', '技术']
const issueStatuses = ['待确认', '已确认', '整改中', '待复核', '已关闭']

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}
function severityType(s) {
  if (s === '高') return 'danger'
  if (s === '中') return 'warning'
  if (s === '低') return 'success'
  return 'info'
}
function issueStatusType(s) {
  const map = { 待确认: 'warning', 已确认: 'primary', 整改中: '', 待复核: 'info', 已关闭: 'success' }
  return map[s] || 'info'
}

// ---------- 规则 ----------
const rules = ref([])
const rulesLoading = ref(false)
const ruleQuery = reactive({ q: '' })
const runningAll = ref(false)

const ruleDialogVisible = ref(false)
const editingRule = ref(null)
const ruleForm = reactive({
  name: '', object_id: null, target_table: '', target_field: '',
  rule_type: '完整性', severity: '中', assignee_type: '业务', is_enabled: true,
})

async function loadRules() {
  rulesLoading.value = true
  try {
    const params = {}
    if (ruleQuery.q) params.q = ruleQuery.q
    const { data } = await listQualityRulesApi(params)
    rules.value = asList(data)
  } catch (e) {
    ElMessage.error('规则加载失败')
  } finally {
    rulesLoading.value = false
  }
}

function openRuleDialog(row) {
  editingRule.value = row || null
  Object.assign(ruleForm, {
    name: row?.name || '',
    object_id: row?.object_id || null,
    target_table: row?.target_table || '',
    target_field: row?.target_field || '',
    rule_type: row?.rule_type || '完整性',
    severity: row?.severity || '中',
    assignee_type: row?.assignee_type || '数据管理责任人',
    is_enabled: row ? !!row.is_enabled : true,
  })
  ruleDialogVisible.value = true
}

async function submitRule() {
  if (!ruleForm.name) {
    ElMessage.warning('请填写规则名称')
    return
  }
  const body = { ...ruleForm }
  if (!body.object_id) delete body.object_id
  submitting.value = true
  try {
    if (editingRule.value) {
      await updateQualityRuleApi(editingRule.value.id, body)
      ElMessage.success('规则已更新')
    } else {
      await createQualityRuleApi(body)
      ElMessage.success('规则已创建')
    }
    ruleDialogVisible.value = false
    loadRules()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    submitting.value = false
  }
}

async function toggleRule(row) {
  try {
    await toggleQualityRuleApi(row.id)
    row.is_enabled = !row.is_enabled
    ElMessage.success(row.is_enabled ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error('切换失败')
  }
}

async function removeRule(row) {
  try {
    await ElMessageBox.confirm(`确定删除规则「${row.name}」吗？`, '提示', { type: 'warning' })
    await deleteQualityRuleApi(row.id)
    ElMessage.success('已删除')
    loadRules()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

async function runOne(row) {
  row._running = true
  try {
    const { data } = await runQualityRuleApi(row.id)
    ElMessage.success(`执行完成，发现 ${data?.issue_count ?? 0} 个问题`)
    loadIssues()
  } catch (e) {
    ElMessage.error('执行失败')
  } finally {
    row._running = false
  }
}

async function runAll() {
  runningAll.value = true
  try {
    const { data } = await runAllQualityRulesApi()
    ElMessage.success(`全部执行完成，发现 ${data?.issue_count ?? 0} 个问题`)
    loadIssues()
  } catch (e) {
    ElMessage.error('执行失败')
  } finally {
    runningAll.value = false
  }
}

// ---------- 执行记录 ----------
const runs = ref([])
const runsLoading = ref(false)
const runDetailVisible = ref(false)
const runIssues = ref([])
const runDetailLoading = ref(false)

async function loadRuns() {
  runsLoading.value = true
  try {
    const { data } = await listQualityRunsApi()
    runs.value = asList(data)
  } catch (e) {
    ElMessage.error('执行记录加载失败')
  } finally {
    runsLoading.value = false
  }
}

async function openRunDetail(row) {
  runDetailVisible.value = true
  runDetailLoading.value = true
  try {
    const { data } = await getQualityRunApi(row.id)
    runIssues.value = asList(data?.issues ?? data)
  } catch (e) {
    ElMessage.error('执行详情加载失败')
  } finally {
    runDetailLoading.value = false
  }
}

// ---------- 问题整改 ----------
const issues = ref([])
const issuesLoading = ref(false)
const issueQuery = reactive({ status: '' })

const confirmDialogVisible = ref(false)
const confirmRow = ref(null)
const confirmLead = ref('')

const fixDialogVisible = ref(false)
const fixRow = ref(null)
const fixForm = reactive({ root_cause: '', fix_desc: '' })

const closeDialogVisible = ref(false)
const closeRow = ref(null)
const closeComment = ref('')

async function loadIssues() {
  issuesLoading.value = true
  try {
    const params = {}
    if (issueQuery.status) params.status = issueQuery.status
    const { data } = await listQualityApi(params)
    issues.value = asList(data)
  } catch (e) {
    ElMessage.error('问题加载失败')
  } finally {
    issuesLoading.value = false
  }
}

function openConfirmDialog(row) {
  confirmRow.value = row
  confirmLead.value = ''
  confirmDialogVisible.value = true
}
async function submitConfirm() {
  submitting.value = true
  try {
    await confirmIssueApi(confirmRow.value.id, confirmLead.value ? { lead_assignee: confirmLead.value } : {})
    ElMessage.success('已确认')
    confirmDialogVisible.value = false
    loadIssues()
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    submitting.value = false
  }
}

function openFixDialog(row) {
  fixRow.value = row
  Object.assign(fixForm, { root_cause: '', fix_desc: '' })
  fixDialogVisible.value = true
}
async function submitFix() {
  if (!fixForm.fix_desc) {
    ElMessage.warning('请填写整改说明')
    return
  }
  submitting.value = true
  try {
    const body = { fix_desc: fixForm.fix_desc }
    if (fixForm.root_cause) body.root_cause = fixForm.root_cause
    await fixIssueApi(fixRow.value.id, body)
    ElMessage.success('整改已提交')
    fixDialogVisible.value = false
    loadIssues()
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    submitting.value = false
  }
}

async function doRecheck(row) {
  try {
    const { data } = await recheckIssueApi(row.id)
    if (data?.clean) {
      ElMessage.success('复核通过，问题已消除')
    } else {
      ElMessage.warning('复核未通过，问题仍然存在')
    }
    loadIssues()
  } catch (e) {
    ElMessage.error('重新检测失败')
  }
}

function openCloseDialog(row) {
  closeRow.value = row
  closeComment.value = ''
  closeDialogVisible.value = true
}
async function submitClose() {
  submitting.value = true
  try {
    await closeIssueApi(closeRow.value.id, { review_comment: closeComment.value })
    ElMessage.success('问题已关闭')
    closeDialogVisible.value = false
    loadIssues()
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 定时计划 ----------
const schedules = ref([])
const schedulesLoading = ref(false)
const scheduleDialogVisible = ref(false)
const scheduleForm = reactive({ rule_id: null, cron_expr: '', is_enabled: true })
const triggering = ref(false)

async function loadSchedules() {
  schedulesLoading.value = true
  try {
    const { data } = await listQualitySchedulesApi()
    schedules.value = asList(data)
  } catch (e) {
    ElMessage.error('定时计划加载失败')
  } finally {
    schedulesLoading.value = false
  }
}

function openScheduleDialog() {
  Object.assign(scheduleForm, { rule_id: null, cron_expr: '', is_enabled: true })
  scheduleDialogVisible.value = true
}
async function submitSchedule() {
  if (!scheduleForm.rule_id || !scheduleForm.cron_expr) {
    ElMessage.warning('请选择规则并填写 Cron 表达式')
    return
  }
  submitting.value = true
  try {
    await createQualityScheduleApi({ ...scheduleForm })
    ElMessage.success('定时计划已创建')
    scheduleDialogVisible.value = false
    loadSchedules()
  } catch (e) {
    ElMessage.error('创建失败')
  } finally {
    submitting.value = false
  }
}

async function triggerDue() {
  triggering.value = true
  try {
    const { data } = await triggerDueSchedulesApi()
    ElMessage.success(`已触发 ${data?.triggered_count ?? 0} 个到期计划`)
    loadRuns()
  } catch (e) {
    ElMessage.error('触发失败')
  } finally {
    triggering.value = false
  }
}

// ---------- tabs ----------
function onTabChange() {
  if (activeTab.value === 'runs') loadRuns()
  else if (activeTab.value === 'issues') loadIssues()
  else if (activeTab.value === 'schedules') loadSchedules()
  else loadRules()
}

onMounted(async () => {
  loadRules()
  try {
    const { data } = await listObjectsApi()
    objects.value = asList(data)
  } catch (_) {}
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
