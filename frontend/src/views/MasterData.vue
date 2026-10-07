<template>
  <el-row :gutter="16">
    <el-col :span="5">
      <el-card v-loading="modelsLoading">
        <template #header>
          <div class="card-header">
            <span>主数据模型</span>
            <el-button v-if="auth.isAdmin" size="small" type="primary" @click="openModelDialog">新建</el-button>
          </div>
        </template>
        <el-table :data="models" highlight-current-row @current-change="onModelSelect" style="width: 100%">
          <el-table-column prop="code" label="模型编码" min-width="90" show-overflow-tooltip />
          <el-table-column prop="name" label="模型名称" min-width="110" show-overflow-tooltip />
          <el-table-column prop="record_count" label="记录" width="60" />
        </el-table>
        <div v-if="selectedModel" class="model-meta">
          <div>对象：{{ selectedModel.object_name || '-' }}（{{ selectedModel.object_code || '-' }}）</div>
          <div>编码规则：{{ selectedModel.id_rule || '-' }}</div>
          <div>版本：{{ selectedModel.version || '-' }}　状态：{{ selectedModel.status || '-' }}</div>
        </div>
      </el-card>
    </el-col>

    <el-col :span="19">
      <el-card v-loading="tabLoading">
        <el-tabs v-model="activeTab" @tab-change="onTabChange">
          <!-- 主数据记录 -->
          <el-tab-pane label="主数据记录" name="records">
            <div class="filter-bar">
              <el-input v-model="recQuery.status" placeholder="状态筛选" clearable style="width: 140px" />
              <el-input v-model="recQuery.q" placeholder="编码/属性关键字" clearable style="width: 220px" @keyup.enter="loadRecords" />
              <el-button type="primary" @click="loadRecords" :disabled="!selectedModel">搜索</el-button>
              <el-button @click="openApplyDialog('新增')" :disabled="!selectedModel">新增申请</el-button>
            </div>
            <el-table :data="records">
              <el-table-column prop="master_code" label="统一编码" width="150" />
              <el-table-column label="属性" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ attrsSummary(row) }}</template>
              </el-table-column>
              <el-table-column prop="source_system" label="来源系统" width="130" show-overflow-tooltip />
              <el-table-column prop="source_code" label="来源编码" width="130" show-overflow-tooltip />
              <el-table-column prop="status" label="状态" width="90">
                <template #default="{ row }"><el-tag :type="recordStatusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="version" label="版本" width="70" />
              <el-table-column prop="updated_at" label="更新时间" width="160" />
              <el-table-column label="操作" width="210" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openRecordDrawer(row)">详情</el-button>
                  <el-button link type="primary" size="small" @click="openApplyDialog('变更', row)">变更</el-button>
                  <el-button link type="primary" size="small" @click="openDistributeDialog(row)">分发</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!selectedModel" description="请先在左侧选择一个主数据模型" />
          </el-tab-pane>

          <!-- 申请审核 -->
          <el-tab-pane label="申请审核" name="apps">
            <div class="filter-bar">
              <el-select v-model="appQuery.status" placeholder="状态筛选" clearable filterable allow-create style="width: 160px">
                <el-option label="待审核" value="待审核" />
                <el-option label="已通过" value="已通过" />
                <el-option label="已驳回" value="已驳回" />
              </el-select>
              <el-button type="primary" @click="loadApplications" :disabled="!selectedModel">搜索</el-button>
            </div>
            <el-table :data="applications">
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column prop="model_code" label="模型" width="120" />
              <el-table-column prop="app_type" label="申请类型" width="100" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }"><el-tag :type="appStatusType(row.status)" size="small">{{ row.status || '-' }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="applicant" label="申请人" width="110" />
              <el-table-column prop="reason" label="申请理由" min-width="200" show-overflow-tooltip />
              <el-table-column prop="created_at" label="申请时间" width="160" />
              <el-table-column label="操作" width="100" fixed="right">
                <template #default="{ row }">
                  <el-button
                    v-if="auth.isAdmin && (row.status === '待审核' || !row.status)"
                    link type="primary" size="small" @click="openReviewDialog(row)">审核</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 三码映射 -->
          <el-tab-pane label="三码映射" name="links">
            <div class="filter-bar">
              <el-input v-model="linkQuery.physical_code" placeholder="物理编码" clearable style="width: 180px" />
              <el-input v-model="linkQuery.logic_code" placeholder="逻辑编码" clearable style="width: 180px" />
              <el-button type="primary" @click="loadDeviceLinks">搜索</el-button>
              <el-button @click="linkDialogVisible = true; linkForm.physical_code=''; linkForm.logic_code=''; linkForm.model_code=selectedModel?.code||''; linkForm.effective_from=''; linkForm.effective_to=''">新增映射</el-button>
            </div>
            <el-table :data="deviceLinks">
              <el-table-column prop="logic_code" label="逻辑编码" width="170" />
              <el-table-column prop="model_code" label="模型编码" width="130" />
              <el-table-column prop="physical_code" label="物理编码" width="170" />
              <el-table-column prop="effective_from" label="生效起" width="130" />
              <el-table-column prop="effective_to" label="生效止" width="130" />
            </el-table>
          </el-tab-pane>

          <!-- 统一编码映射 -->
          <el-tab-pane label="统一编码映射" name="codemap">
            <div class="filter-bar">
              <el-input v-model="mapQuery.source_system" placeholder="来源系统" clearable style="width: 180px" />
              <el-button type="primary" @click="loadCodeMaps" :disabled="!selectedModel">搜索</el-button>
              <el-button @click="openCodeMapDialog" :disabled="!selectedModel">新增映射</el-button>
            </div>
            <el-table :data="codeMaps">
              <el-table-column prop="model_code" label="模型编码" width="130" />
              <el-table-column prop="master_code" label="统一编码" width="150" />
              <el-table-column prop="source_system" label="来源系统" width="150" />
              <el-table-column prop="source_code" label="来源编码" width="150" />
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </el-col>
  </el-row>

  <!-- 新建模型 -->
  <el-dialog v-model="modelDialogVisible" title="新建主数据模型" width="520px">
    <el-form :model="modelForm" label-width="100px">
      <el-form-item label="业务对象">
        <el-select v-model="modelForm.object_id" placeholder="请选择" style="width: 100%">
          <el-option v-for="o in objects" :key="o.id" :label="`${o.code || ''} ${o.name || ''}`" :value="o.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="模型编码"><el-input v-model="modelForm.code" placeholder="如 MD-EQ" /></el-form-item>
      <el-form-item label="模型名称"><el-input v-model="modelForm.name" placeholder="如 设备主数据" /></el-form-item>
      <el-form-item label="编码规则"><el-input v-model="modelForm.id_rule" placeholder="如 前缀+流水号" /></el-form-item>
      <el-form-item label="关键字段"><el-input v-model="modelForm.key_fields" placeholder="逗号分隔，如 设备名称,规格型号" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="modelDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submitModel" :loading="submitting">确定</el-button>
    </template>
  </el-dialog>

  <!-- 主数据申请 -->
  <el-dialog v-model="applyDialogVisible" :title="applyTitle" width="600px">
    <el-form :model="applyForm" label-width="100px">
      <el-form-item label="申请类型">
        <el-select v-model="applyForm.app_type" style="width: 100%">
          <el-option v-for="t in ['新增', '变更', '停用', '合并']" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>
      <el-form-item label="统一编码" v-if="applyForm.app_type !== '新增'">
        <el-input v-model="applyForm.master_code" placeholder="变更/停用/合并的目标记录编码" />
      </el-form-item>
      <el-form-item label="合并到" v-if="applyForm.app_type === '合并'">
        <el-input v-model="applyForm.merge_to_code" placeholder="合并目标记录的统一编码" />
      </el-form-item>
      <el-form-item label="属性(JSON)" v-if="applyForm.app_type === '新增' || applyForm.app_type === '变更'">
        <el-input v-model="applyForm.attrsText" type="textarea" :rows="6" placeholder='{"设备名称": "主泵", "规格型号": "100D-45"}' />
      </el-form-item>
      <el-form-item label="申请理由">
        <el-input v-model="applyForm.reason" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="applyDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submitApply" :loading="submitting">提交申请</el-button>
    </template>
  </el-dialog>

  <!-- 重复提示 -->
  <el-dialog v-model="dupDialogVisible" title="检测到重复记录" width="560px">
    <el-alert title="申请已提交。以下记录与申请属性高度相似，请确认是否为重复：" type="warning" :closable="false" style="margin-bottom: 12px" />
    <el-table :data="duplicates">
      <el-table-column prop="master_code" label="统一编码" width="150" />
      <el-table-column label="属性" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ JSON.stringify(row.attrs || {}) }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button type="primary" @click="dupDialogVisible = false">知道了</el-button>
    </template>
  </el-dialog>

  <!-- 分发 -->
  <el-dialog v-model="distributeDialogVisible" title="分发主数据" width="480px">
    <el-form label-width="100px">
      <el-form-item label="记录编码">{{ distributeRow?.master_code }}</el-form-item>
      <el-form-item label="目标系统">
        <el-select v-model="distributeTargets" multiple filterable allow-create placeholder="选择或输入目标系统" style="width: 100%">
          <el-option v-for="s in systemOptions" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="distributeDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submitDistribute" :loading="submitting" :disabled="!distributeTargets.length">确定分发</el-button>
    </template>
  </el-dialog>

  <!-- 申请审核 -->
  <el-dialog v-model="reviewDialogVisible" title="申请审核" width="560px">
    <el-descriptions :column="2" border v-if="reviewRow">
      <el-descriptions-item label="申请ID">{{ reviewRow.id }}</el-descriptions-item>
      <el-descriptions-item label="申请类型">{{ reviewRow.app_type }}</el-descriptions-item>
      <el-descriptions-item label="模型">{{ reviewRow.model_code }}</el-descriptions-item>
      <el-descriptions-item label="申请人">{{ reviewRow.applicant }}</el-descriptions-item>
      <el-descriptions-item label="理由" :span="2">{{ reviewRow.reason }}</el-descriptions-item>
      <el-descriptions-item label="申请时间" :span="2">{{ reviewRow.created_at }}</el-descriptions-item>
    </el-descriptions>
    <el-form style="margin-top: 16px">
      <el-form-item label="审核意见">
        <el-input v-model="reviewComment" type="textarea" :rows="3" placeholder="请输入审核意见" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewDialogVisible = false">取消</el-button>
      <el-button type="danger" @click="submitReview('驳回')" :loading="submitting">驳回</el-button>
      <el-button type="success" @click="submitReview('通过')" :loading="submitting">通过</el-button>
    </template>
  </el-dialog>

  <!-- 新增三码映射 -->
  <el-dialog v-model="linkDialogVisible" title="新增三码映射" width="520px">
    <el-form :model="linkForm" label-width="100px">
      <el-form-item label="逻辑编码"><el-input v-model="linkForm.logic_code" /></el-form-item>
      <el-form-item label="模型编码"><el-input v-model="linkForm.model_code" /></el-form-item>
      <el-form-item label="物理编码"><el-input v-model="linkForm.physical_code" /></el-form-item>
      <el-form-item label="生效起"><el-date-picker v-model="linkForm.effective_from" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
      <el-form-item label="生效止"><el-date-picker v-model="linkForm.effective_to" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="linkDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submitDeviceLink" :loading="submitting">确定</el-button>
    </template>
  </el-dialog>

  <!-- 新增统一编码映射 -->
  <el-dialog v-model="codeMapDialogVisible" title="新增统一编码映射" width="520px">
    <el-form :model="codeMapForm" label-width="100px">
      <el-form-item label="主数据模型">
        <el-select v-model="codeMapForm.model_id" style="width: 100%">
          <el-option v-for="m in models" :key="m.id" :label="`${m.code} ${m.name}`" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="统一编码"><el-input v-model="codeMapForm.master_code" /></el-form-item>
      <el-form-item label="来源系统"><el-input v-model="codeMapForm.source_system" /></el-form-item>
      <el-form-item label="来源编码"><el-input v-model="codeMapForm.source_code" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="codeMapDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submitCodeMap" :loading="submitting">确定</el-button>
    </template>
  </el-dialog>

  <!-- 记录详情抽屉 -->
  <el-drawer v-model="drawerVisible" :title="`记录详情：${detailRow?.master_code || ''}`" size="640px">
    <div v-loading="detailLoading">
      <div class="section-title">基本信息</div>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="统一编码">{{ detail?.record?.master_code }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ detail?.record?.status }}</el-descriptions-item>
        <el-descriptions-item label="来源系统">{{ detail?.record?.source_system }}</el-descriptions-item>
        <el-descriptions-item label="来源编码">{{ detail?.record?.source_code }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ detail?.record?.version }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ detail?.record?.updated_at }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-title">属性</div>
      <el-descriptions :column="1" border>
        <el-descriptions-item v-for="(v, k) in detailAttrs" :key="k" :label="k">{{ fmtVal(v) }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="!Object.keys(detailAttrs).length"><el-empty description="无属性" :image-size="60" /></div>

      <div class="section-title" v-if="auth.isAdmin">直接修改属性（管理员）</div>
      <el-input
        v-if="auth.isAdmin"
        v-model="detailAttrsText"
        type="textarea"
        :rows="5"
        placeholder='{"属性名": "值"}'
      />
      <div v-if="auth.isAdmin" style="margin-top: 8px; text-align: right">
        <el-button size="small" type="primary" @click="submitRecordUpdate" :loading="submitting">保存修改</el-button>
      </div>

      <div class="section-title">历史版本</div>
      <el-timeline v-if="histories.length">
        <el-timeline-item
          v-for="(h, i) in histories"
          :key="i"
          :timestamp="h.version ? `版本 ${h.version}` : (h.changed_at || h.created_at || h.updated_at || '')"
        >
          <div>{{ h.change_desc || h.description || fmtVal(h.attrs || h.changes) }}</div>
          <div class="step-info" v-if="h.operator || h.operated_by">操作人：{{ h.operator || h.operated_by }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无历史版本" :image-size="60" />

      <div class="section-title">分发记录</div>
      <el-table :data="distributions" v-if="distributions.length">
        <el-table-column prop="target_system" label="目标系统" width="160" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="distributed_at" label="分发时间" width="170" />
        <el-table-column prop="operator" label="操作人" width="110" />
      </el-table>
      <el-empty v-else description="暂无分发记录" :image-size="60" />

      <div class="section-title">编码映射</div>
      <el-table :data="detailCodeMaps" v-if="detailCodeMaps.length">
        <el-table-column prop="source_system" label="来源系统" width="160" />
        <el-table-column prop="source_code" label="来源编码" width="160" />
      </el-table>
      <el-empty v-else description="暂无编码映射" :image-size="60" />
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auth } from '../store/auth.js'
import {
  listMdModelsApi,
  createMdModelApi,
  applyMdModelApi,
  listMdApplicationsApi,
  reviewMdApplicationApi,
  listMdRecordsApi,
  getMdRecordApi,
  updateMdRecordApi,
  distributeMdRecordApi,
  createCodeMapApi,
  listCodeMapsApi,
  createDeviceLinkApi,
  listDeviceLinksApi,
  listObjectsApi,
} from '../api/index.js'

// ---------- 左侧模型 ----------
const models = ref([])
const modelsLoading = ref(false)
const selectedModel = ref(null)
const activeTab = ref('records')
const tabLoading = ref(false)
const submitting = ref(false)
const objects = ref([])

const systemOptions = ['设备管理系统', '维修管理系统', '物资管理系统', '财务系统']

// ---------- 记录 tab ----------
const records = ref([])
const recQuery = reactive({ status: '', q: '' })

// ---------- 申请 tab ----------
const applications = ref([])
const appQuery = reactive({ status: '' })

// ---------- 三码 tab ----------
const deviceLinks = ref([])
const linkQuery = reactive({ physical_code: '', logic_code: '' })

// ---------- 编码映射 tab ----------
const codeMaps = ref([])
const mapQuery = reactive({ source_system: '' })

// ---------- dialogs ----------
const modelDialogVisible = ref(false)
const modelForm = reactive({ object_id: null, code: '', name: '', id_rule: '', key_fields: '' })

const applyDialogVisible = ref(false)
const applyTitle = ref('主数据申请')
const applyForm = reactive({ app_type: '新增', master_code: '', merge_to_code: '', attrsText: '', reason: '' })

const dupDialogVisible = ref(false)
const duplicates = ref([])

const distributeDialogVisible = ref(false)
const distributeRow = ref(null)
const distributeTargets = ref([])

const reviewDialogVisible = ref(false)
const reviewRow = ref(null)
const reviewComment = ref('')

const linkDialogVisible = ref(false)
const linkForm = reactive({ logic_code: '', model_code: '', physical_code: '', effective_from: '', effective_to: '' })

const codeMapDialogVisible = ref(false)
const codeMapForm = reactive({ model_id: null, master_code: '', source_system: '', source_code: '' })

// ---------- 详情抽屉 ----------
const drawerVisible = ref(false)
const detailRow = ref(null)
const detail = ref({})
const detailAttrsText = ref('')
const detailLoading = ref(false)

const detailAttrs = computed(() => {
  const a = detail.value?.record?.attrs
  return a && typeof a === 'object' ? a : {}
})
const histories = computed(() => detail.value?.history || [])
const distributions = computed(() => detail.value?.distributions || [])
const detailCodeMaps = computed(() => detail.value?.code_maps || [])

// ---------- 工具 ----------
function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}
function attrsSummary(row) {
  const a = row.attrs
  if (!a) return '-'
  const s = typeof a === 'string' ? a : JSON.stringify(a)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}
function fmtVal(v) {
  return typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')
}
function recordStatusType(s) {
  if (s === '有效' || s === '启用') return 'success'
  if (s === '停用' || s === '无效') return 'danger'
  return 'info'
}
function appStatusType(s) {
  if (s === '已通过') return 'success'
  if (s === '已驳回') return 'danger'
  if (s === '待审核') return 'warning'
  return 'info'
}
function parseAttrsText(text) {
  if (!text || !text.trim()) return {}
  try {
    const obj = JSON.parse(text)
    if (typeof obj !== 'object' || obj === null) throw new Error('必须是 JSON 对象')
    return obj
  } catch (e) {
    ElMessage.error('属性 JSON 格式错误：' + e.message)
    return null
  }
}

// ---------- 加载 ----------
async function loadModels() {
  modelsLoading.value = true
  try {
    const { data } = await listMdModelsApi()
    models.value = asList(data)
    if (!selectedModel.value && models.value.length) {
      selectedModel.value = models.value[0]
      await loadTab()
    }
  } catch (e) {
    ElMessage.error('模型加载失败')
  } finally {
    modelsLoading.value = false
  }
}
async function loadObjects() {
  try {
    const { data } = await listObjectsApi()
    objects.value = asList(data)
  } catch (_) {}
}

async function onModelSelect(row) {
  if (!row) return
  selectedModel.value = row
  await loadTab()
}
function onTabChange() {
  loadTab()
}
async function loadTab() {
  if (!selectedModel.value) return
  if (activeTab.value === 'records') return loadRecords()
  if (activeTab.value === 'apps') return loadApplications()
  if (activeTab.value === 'links') return loadDeviceLinks()
  if (activeTab.value === 'codemap') return loadCodeMaps()
}

async function loadRecords() {
  if (!selectedModel.value) return
  tabLoading.value = true
  try {
    const params = { model_id: selectedModel.value.id }
    if (recQuery.status) params.status = recQuery.status
    if (recQuery.q) params.q = recQuery.q
    const { data } = await listMdRecordsApi(params)
    records.value = asList(data)
  } catch (e) {
    ElMessage.error('记录加载失败')
  } finally {
    tabLoading.value = false
  }
}

async function loadApplications() {
  if (!selectedModel.value) return
  tabLoading.value = true
  try {
    const params = { model_id: selectedModel.value.id }
    if (appQuery.status) params.status = appQuery.status
    const { data } = await listMdApplicationsApi(params)
    applications.value = asList(data)
  } catch (e) {
    ElMessage.error('申请加载失败')
  } finally {
    tabLoading.value = false
  }
}

async function loadDeviceLinks() {
  tabLoading.value = true
  try {
    const params = {}
    if (linkQuery.physical_code) params.physical_code = linkQuery.physical_code
    if (linkQuery.logic_code) params.logic_code = linkQuery.logic_code
    const { data } = await listDeviceLinksApi(params)
    deviceLinks.value = asList(data)
  } catch (e) {
    ElMessage.error('三码映射加载失败')
  } finally {
    tabLoading.value = false
  }
}

async function loadCodeMaps() {
  if (!selectedModel.value) return
  tabLoading.value = true
  try {
    const params = { model_id: selectedModel.value.id }
    if (mapQuery.source_system) params.source_system = mapQuery.source_system
    const { data } = await listCodeMapsApi(params)
    codeMaps.value = asList(data)
  } catch (e) {
    ElMessage.error('编码映射加载失败')
  } finally {
    tabLoading.value = false
  }
}

// ---------- 新建模型 ----------
function openModelDialog() {
  Object.assign(modelForm, { object_id: null, code: '', name: '', id_rule: '', key_fields: '' })
  modelDialogVisible.value = true
}
async function submitModel() {
  if (!modelForm.code || !modelForm.name) {
    ElMessage.warning('请填写模型编码和名称')
    return
  }
  submitting.value = true
  try {
    await createMdModelApi({ ...modelForm })
    ElMessage.success('模型创建成功')
    modelDialogVisible.value = false
    await loadModels()
  } catch (e) {
    ElMessage.error('创建失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 申请 ----------
function openApplyDialog(type, row) {
  Object.assign(applyForm, {
    app_type: type,
    master_code: row?.master_code || '',
    merge_to_code: '',
    attrsText: row?.attrs ? JSON.stringify(row.attrs, null, 2) : '',
    reason: '',
  })
  applyTitle.value = type === '新增' ? '新增主数据申请' : `${type}主数据申请`
  applyDialogVisible.value = true
}
async function submitApply() {
  const body = { app_type: applyForm.app_type, reason: applyForm.reason }
  if (applyForm.app_type !== '新增') {
    if (!applyForm.master_code) {
      ElMessage.warning('请填写统一编码')
      return
    }
    body.master_code = applyForm.master_code
  }
  if (applyForm.app_type === '合并') {
    if (!applyForm.merge_to_code) {
      ElMessage.warning('请填写合并目标编码')
      return
    }
    body.merge_to_code = applyForm.merge_to_code
  }
  if (applyForm.app_type === '新增' || applyForm.app_type === '变更') {
    const attrs = parseAttrsText(applyForm.attrsText)
    if (attrs === null) return
    body.payload = attrs
  }
  submitting.value = true
  try {
    const { data } = await applyMdModelApi(selectedModel.value.id, body)
    applyDialogVisible.value = false
    ElMessage.success(`申请已提交（ID: ${data?.application_id ?? '-'}）`)
    if (data?.duplicates?.length) {
      duplicates.value = data.duplicates
      dupDialogVisible.value = true
    }
    if (activeTab.value === 'apps') loadApplications()
    else loadRecords()
  } catch (e) {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 分发 ----------
function openDistributeDialog(row) {
  distributeRow.value = row
  distributeTargets.value = []
  distributeDialogVisible.value = true
}
async function submitDistribute() {
  submitting.value = true
  try {
    await distributeMdRecordApi(distributeRow.value.id, { target_systems: distributeTargets.value })
    ElMessage.success('分发任务已提交')
    distributeDialogVisible.value = false
  } catch (e) {
    ElMessage.error('分发失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 审核 ----------
function openReviewDialog(row) {
  reviewRow.value = row
  reviewComment.value = ''
  reviewDialogVisible.value = true
}
async function submitReview(decision) {
  submitting.value = true
  try {
    await reviewMdApplicationApi(reviewRow.value.id, { decision, comment: reviewComment.value })
    ElMessage.success(`已${decision}`)
    reviewDialogVisible.value = false
    loadApplications()
    loadRecords()
  } catch (e) {
    ElMessage.error('审核失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 三码映射 ----------
async function submitDeviceLink() {
  if (!linkForm.logic_code || !linkForm.physical_code) {
    ElMessage.warning('请填写逻辑编码和物理编码')
    return
  }
  submitting.value = true
  try {
    const body = { ...linkForm }
    if (!body.effective_to) delete body.effective_to
    await createDeviceLinkApi(body)
    ElMessage.success('三码映射已创建')
    linkDialogVisible.value = false
    loadDeviceLinks()
  } catch (e) {
    ElMessage.error('创建失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 统一编码映射 ----------
function openCodeMapDialog() {
  Object.assign(codeMapForm, {
    model_id: selectedModel.value?.id || null,
    master_code: '',
    source_system: '',
    source_code: '',
  })
  codeMapDialogVisible.value = true
}
async function submitCodeMap() {
  if (!codeMapForm.model_id || !codeMapForm.master_code || !codeMapForm.source_system || !codeMapForm.source_code) {
    ElMessage.warning('请填写完整映射信息')
    return
  }
  submitting.value = true
  try {
    await createCodeMapApi({ ...codeMapForm })
    ElMessage.success('编码映射已创建')
    codeMapDialogVisible.value = false
    loadCodeMaps()
  } catch (e) {
    ElMessage.error('创建失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 记录详情 ----------
async function openRecordDrawer(row) {
  detailRow.value = row
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const { data } = await getMdRecordApi(row.id)
    detail.value = data?.record ? data : { record: data, history: [], distributions: [], code_maps: [] }
    const attrs = detail.value.record?.attrs
    detailAttrsText.value = attrs ? JSON.stringify(attrs, null, 2) : ''
  } catch (e) {
    ElMessage.error('详情加载失败')
  } finally {
    detailLoading.value = false
  }
}
async function submitRecordUpdate() {
  const attrs = parseAttrsText(detailAttrsText.value)
  if (attrs === null) return
  submitting.value = true
  try {
    await updateMdRecordApi(detailRow.value.id, { attrs })
    ElMessage.success('属性已更新')
    await openRecordDrawerRefresh()
    loadRecords()
  } catch (e) {
    ElMessage.error('更新失败')
  } finally {
    submitting.value = false
  }
}
async function openRecordDrawerRefresh() {
  detailLoading.value = true
  try {
    const { data } = await getMdRecordApi(detailRow.value.id)
    detail.value = data?.record ? data : { record: data, history: [], distributions: [], code_maps: [] }
    const attrs = detail.value.record?.attrs
    detailAttrsText.value = attrs ? JSON.stringify(attrs, null, 2) : ''
  } catch (_) {
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  loadModels()
  loadObjects()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.model-meta {
  margin-top: 12px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
  border-top: 1px solid #ebeef5;
  padding-top: 8px;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  margin: 20px 0 10px;
}
.step-info {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
