<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <template #header>
            <div class="card-header">
              <span class="card-title">基地档案</span>
              <el-button type="primary" size="small" @click="showCreate = true">新增基地</el-button>
            </div>
          </template>
          <el-table :data="bases" v-loading="loading" highlight-current-row @current-change="onSelectBase">
            <el-table-column prop="code" label="编码" width="90" />
            <el-table-column prop="name" label="名称" width="90" />
            <el-table-column prop="stack_type" label="堆型" width="90" />
            <el-table-column prop="status" label="状态" width="80" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card v-loading="detailLoading">
          <template #header>
            <span class="card-title">基地差异：{{ current?.name || '请选择基地' }}</span>
          </template>
          <template v-if="current">
            <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
              <el-descriptions-item label="编码">{{ current.code }}</el-descriptions-item>
              <el-descriptions-item label="堆型">{{ current.stack_type || '-' }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ current.status }}</el-descriptions-item>
            </el-descriptions>
            <el-tabs v-model="tab">
              <el-tab-pane label="标准差异" name="std">
                <el-button type="primary" size="small" @click="openDiff('std')" style="margin-bottom: 8px">登记标准差异</el-button>
                <el-table :data="current.std_diffs" empty-text="暂无标准差异（使用集团共性）">
                  <el-table-column prop="std_code" label="标准编码" width="100" />
                  <el-table-column prop="std_name" label="标准名称" width="150" />
                  <el-table-column prop="diff_type" label="差异类型" width="90" />
                  <el-table-column prop="reason" label="差异原因" min-width="180" />
                  <el-table-column prop="status" label="状态" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.status === '已发布' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="90">
                    <template #default="{ row }">
                      <el-button v-if="row.status !== '已发布'" link type="primary" size="small" @click="publishDiff('std', row.id)">发布</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="指标差异" name="ind">
                <el-button type="primary" size="small" @click="openDiff('ind')" style="margin-bottom: 8px">登记指标差异</el-button>
                <el-table :data="current.indicator_diffs" empty-text="暂无指标差异（使用集团共性）">
                  <el-table-column prop="ind_code" label="指标编码" width="150" />
                  <el-table-column prop="ind_name" label="指标名称" width="150" />
                  <el-table-column prop="diff_type" label="差异类型" width="90" />
                  <el-table-column prop="reason" label="差异原因" min-width="180" />
                  <el-table-column prop="status" label="状态" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.status === '已发布' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="90">
                    <template #default="{ row }">
                      <el-button v-if="row.status !== '已发布'" link type="primary" size="small" @click="publishDiff('ind', row.id)">发布</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="有效口径预览" name="preview">
                <el-form inline size="small">
                  <el-form-item label="标准">
                    <el-select v-model="pvStd" placeholder="选择标准" style="width: 220px" @change="loadPreview">
                      <el-option v-for="s in standards" :key="s.id" :label="s.code + ' ' + s.name" :value="s.id" />
                    </el-select>
                  </el-form-item>
                </el-form>
                <el-descriptions v-if="preview" :column="1" border size="small">
                  <el-descriptions-item label="标准">{{ preview.code }} {{ preview.name }}（{{ preview.version }}）</el-descriptions-item>
                  <el-descriptions-item label="有效允许值">{{ (preview.effective_allowed_values || []).join(' / ') || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="口径声明">{{ preview.base_note || '集团共性口径' }}</el-descriptions-item>
                </el-descriptions>
              </el-tab-pane>
            </el-tabs>
          </template>
          <el-empty v-else description="请选择左侧基地查看差异" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showCreate" title="新增基地" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="编码"><el-input v-model="form.code" placeholder="如 BASE-C" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如 基地C" /></el-form-item>
        <el-form-item label="堆型"><el-input v-model="form.stack_type" placeholder="如 PWR1000" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status"><el-option label="运行中" value="运行中" /><el-option label="建设中" value="建设中" /></el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createBase">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDiff" :title="diffKind === 'std' ? '登记标准差异' : '登记指标差异'" width="520px">
      <el-form :model="diffForm" label-width="90px">
        <el-form-item :label="diffKind === 'std' ? '标准' : '指标'">
          <el-select v-model="diffForm.targetId" style="width: 100%">
            <el-option v-for="t in diffTargets" :key="t.id" :label="(t.code || '') + ' ' + t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="差异类型"><el-input v-model="diffForm.diff_type" :placeholder="diffKind === 'std' ? '允许值/口径/必填/格式' : '口径'" /></el-form-item>
        <el-form-item label="差异内容(JSON)">
          <el-input v-model="diffForm.diff_desc" type="textarea" :rows="4" placeholder='如 {"allowed_values": ["NS1","NS2"], "note": "说明"}' />
        </el-form-item>
        <el-form-item label="差异原因"><el-input v-model="diffForm.reason" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDiff = false">取消</el-button>
        <el-button type="primary" @click="createDiff">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listBasesApi, createBaseApi, getBaseApi,
  createStdDiffApi, publishStdDiffApi, createIndDiffApi, publishIndDiffApi,
  effectiveStandardApi, listStandardsApi, listMetricsApi,
} from '../api/index.js'

const bases = ref([])
const loading = ref(false)
const current = ref(null)
const detailLoading = ref(false)
const tab = ref('std')
const showCreate = ref(false)
const showDiff = ref(false)
const diffKind = ref('std')
const standards = ref([])
const metrics = ref([])
const pvStd = ref(null)
const preview = ref(null)
const form = ref({ code: '', name: '', stack_type: '', status: '运行中', description: '' })
const diffForm = ref({ targetId: null, diff_type: '', diff_desc: '', reason: '' })

const diffTargets = computed(() => diffKind.value === 'std' ? standards.value : metrics.value)

async function load() {
  loading.value = true
  try {
    const [{ data: b }, { data: s }, { data: m }] = await Promise.all([
      listBasesApi(), listStandardsApi(), listMetricsApi(),
    ])
    bases.value = b || []
    standards.value = s || []
    metrics.value = Array.isArray(m) ? m : (m?.items || [])
    if (bases.value.length && !current.value) onSelectBase(bases.value[0])
  } finally { loading.value = false }
}

async function onSelectBase(row) {
  if (!row) return
  detailLoading.value = true
  try {
    const { data } = await getBaseApi(row.code)
    current.value = data
  } finally { detailLoading.value = false }
}

async function createBase() {
  try {
    await createBaseApi(form.value)
    ElMessage.success('基地已创建')
    showCreate.value = false
    form.value = { code: '', name: '', stack_type: '', status: '运行中', description: '' }
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '创建失败') }
}

function openDiff(kind) {
  diffKind.value = kind
  diffForm.value = { targetId: null, diff_type: kind === 'std' ? '允许值' : '口径', diff_desc: '', reason: '' }
  showDiff.value = true
}

async function createDiff() {
  let desc = {}
  try { desc = diffForm.value.diff_desc ? JSON.parse(diffForm.value.diff_desc) : {} }
  catch { ElMessage.error('差异内容不是合法 JSON'); return }
  const payload = { base_code: current.value.code, diff_type: diffForm.value.diff_type, diff_desc: desc, reason: diffForm.value.reason }
  try {
    if (diffKind.value === 'std') await createStdDiffApi(diffForm.value.targetId, payload)
    else await createIndDiffApi(diffForm.value.targetId, payload)
    ElMessage.success('差异已登记（草稿），发布后生效')
    showDiff.value = false
    onSelectBase(current.value)
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '登记失败') }
}

async function publishDiff(kind, id) {
  try {
    if (kind === 'std') await publishStdDiffApi(id)
    else await publishIndDiffApi(id)
    ElMessage.success('已发布')
    onSelectBase(current.value)
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '发布失败') }
}

async function loadPreview() {
  if (!pvStd.value || !current.value) return
  try {
    const { data } = await effectiveStandardApi(pvStd.value, current.value.code)
    preview.value = data
  } catch (e) { ElMessage.error('预览失败') }
}

onMounted(load)
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-weight: 600; }
</style>
