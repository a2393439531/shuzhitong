<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="5">
        <el-card>
          <template #header><span class="card-title">领域</span></template>
          <el-tree
            :data="domains"
            :props="{ label: 'name', children: 'children' }"
            highlight-current
            node-key="id"
            @node-click="onDomainClick"
          />
        </el-card>
      </el-col>
      <el-col :span="19">
        <el-card>
          <template #header>
            <div class="list-header">
              <span class="card-title">业务对象</span>
              <div class="list-tools">
                <el-input
                  v-model="query.q"
                  placeholder="搜索对象编码/名称"
                  clearable
                  style="width: 260px"
                  @keyup.enter="loadObjects"
                />
                <el-button type="primary" @click="loadObjects">搜索</el-button>
                <el-button @click="openObjectDialog()">新增对象</el-button>
              </div>
            </div>
          </template>
          <el-table :data="objects" v-loading="loading" highlight-current-row @current-change="onObjectSelect">
            <el-table-column prop="code" label="编码" width="160" />
            <el-table-column prop="name" label="名称" width="180" />
            <el-table-column prop="definition" label="定义" min-width="220" show-overflow-tooltip />
            <el-table-column prop="owner_dept" label="归口部门" width="140" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 对象卡 -->
    <el-card v-if="currentObject" class="object-card">
      <template #header>
        <div class="list-header">
          <span class="card-title">对象卡：{{ currentObject.name }}（{{ currentObject.code }}）</span>
          <el-button size="small" @click="openObjectDialog(currentObject)">编辑</el-button>
        </div>
      </template>
      <el-tabs v-model="activeTab" v-loading="cardLoading">
        <el-tab-pane label="基本信息" name="basic">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="编码">{{ card.object?.code }}</el-descriptions-item>
            <el-descriptions-item label="名称">{{ card.object?.name }}</el-descriptions-item>
            <el-descriptions-item label="所属领域">{{ domainName(card.object?.domain_id) }}</el-descriptions-item>
            <el-descriptions-item label="归口部门">{{ card.object?.owner_dept }}</el-descriptions-item>
            <el-descriptions-item label="唯一性标识说明" :span="2">{{ card.object?.unique_id_desc }}</el-descriptions-item>
            <el-descriptions-item label="定义" :span="2">{{ card.object?.definition }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
        <el-tab-pane label="属性" name="attrs">
          <el-table :data="card.attrs" empty-text="暂无属性">
            <el-table-column prop="name" label="属性名" width="180" />
            <el-table-column prop="data_type" label="数据类型" width="140" />
            <el-table-column label="主键" width="90">
              <template #default="{ row }">{{ row.is_key ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="关系" name="relations">
          <el-table :data="card.relations" empty-text="暂无关系">
            <el-table-column prop="to_object_code" label="关联对象编码" width="160" />
            <el-table-column prop="to_object_name" label="关联对象名称" width="180" />
            <el-table-column prop="rel_type" label="关系类型" width="140" />
            <el-table-column prop="description" label="说明" min-width="180" />
            <el-table-column prop="effective_from" label="有效开始" width="130" />
            <el-table-column prop="effective_to" label="有效结束" width="130" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="关联流程" name="processes">
          <el-table :data="card.processes" empty-text="暂无关联流程">
            <el-table-column prop="process_code" label="流程编码" width="160" />
            <el-table-column prop="process_name" label="流程名称" width="200" />
            <el-table-column prop="role_in_process" label="在流程中的角色" min-width="200" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="目录资源" name="resources">
          <el-table :data="card.resources" empty-text="暂无目录资源">
            <el-table-column prop="res_code" label="资源编码" width="160" />
            <el-table-column prop="name" label="资源名称" width="200" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="source_system" label="来源系统" min-width="160" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="遵循标准" name="standards">
          <el-table :data="card.standards" empty-text="暂无遵循标准">
            <el-table-column prop="code" label="标准编码" width="160" />
            <el-table-column prop="name" label="标准名称" width="220" />
            <el-table-column prop="version" label="版本" width="100" />
            <el-table-column prop="status" label="状态" width="120" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="字段责任" name="responsibilities">
          <el-table :data="card.responsibilities" empty-text="暂无字段责任">
            <el-table-column prop="field_name" label="字段" width="160" />
            <el-table-column prop="business_owner_dept" label="业务归口部门" width="150" />
            <el-table-column prop="authority_source" label="权威来源" min-width="160" />
            <el-table-column prop="input_role" label="录入角色" width="120" />
            <el-table-column prop="review_role" label="审核角色" width="120" />
            <el-table-column prop="data_steward" label="数据管家" width="120" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="来源系统" name="source_systems">
          <el-tag v-for="s in card.source_systems" :key="s" style="margin: 0 8px 8px 0">{{ s }}</el-tag>
          <span v-if="!card.source_systems?.length" class="empty-tip">暂无来源系统</span>
        </el-tab-pane>
        <el-tab-pane label="质量问题" name="quality_issues">
          <el-table :data="card.quality_issues" empty-text="暂无质量问题">
            <el-table-column prop="title" label="标题" min-width="220" />
            <el-table-column prop="issue_type" label="问题类型" width="130" />
            <el-table-column prop="assignee" label="责任人" width="120" />
            <el-table-column prop="status" label="状态" width="110" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="发布服务" name="services">
          <el-table :data="card.services" empty-text="暂无发布服务">
            <el-table-column prop="name" label="服务名称" width="240" />
            <el-table-column prop="version" label="版本" width="120" />
            <el-table-column prop="status" label="状态" width="130" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="支撑指标" name="indicators">
          <el-table :data="card.indicators" empty-text="暂无支撑指标">
            <el-table-column prop="name" label="指标名称" width="240" />
            <el-table-column prop="version" label="版本" width="120" />
            <el-table-column prop="status" label="状态" width="130" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新增/编辑对象弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑业务对象' : '新增业务对象'" width="560px">
      <el-form :model="objectForm" label-width="120px">
        <el-form-item label="编码"><el-input v-model="objectForm.code" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="objectForm.name" /></el-form-item>
        <el-form-item label="所属领域">
          <el-select v-model="objectForm.domain_id" placeholder="请选择" style="width: 100%">
            <el-option v-for="d in domains" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="归口部门"><el-input v-model="objectForm.owner_dept" /></el-form-item>
        <el-form-item label="唯一性标识说明"><el-input v-model="objectForm.unique_id_desc" /></el-form-item>
        <el-form-item label="定义"><el-input v-model="objectForm.definition" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveObject">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listDomainsApi,
  listObjectsApi,
  createObjectApi,
  updateObjectApi,
  getObjectCardApi,
} from '../api/index.js'

const domains = ref([])
const objects = ref([])
const loading = ref(false)
const query = reactive({ domain_id: '', q: '' })

const currentObject = ref(null)
const card = ref({})
const cardLoading = ref(false)
const activeTab = ref('basic')

const dialogVisible = ref(false)
const editing = ref(null)
const objectForm = reactive({ code: '', name: '', domain_id: '', owner_dept: '', unique_id_desc: '', definition: '' })

async function loadDomains() {
  const { data } = await listDomainsApi()
  domains.value = Array.isArray(data) ? data : data.items || []
}

async function loadObjects() {
  loading.value = true
  try {
    const params = {}
    if (query.domain_id) params.domain_id = query.domain_id
    if (query.q) params.q = query.q
    const { data } = await listObjectsApi(params)
    objects.value = Array.isArray(data) ? data : data.items || []
  } finally {
    loading.value = false
  }
}

function onDomainClick(node) {
  query.domain_id = node.id
  loadObjects()
}

function onObjectSelect(row) {
  if (!row) return
  currentObject.value = row
  loadCard(row.id)
}

async function loadCard(id) {
  cardLoading.value = true
  try {
    const { data } = await getObjectCardApi(id)
    card.value = data || {}
  } catch (e) {
    ElMessage.error('加载对象卡失败')
  } finally {
    cardLoading.value = false
  }
}

function domainName(id) {
  return domains.value.find((d) => d.id === id)?.name || id || '-'
}

function openObjectDialog(row) {
  editing.value = row || null
  Object.assign(objectForm, {
    code: row?.code || '',
    name: row?.name || '',
    domain_id: row?.domain_id || query.domain_id || '',
    owner_dept: row?.owner_dept || '',
    unique_id_desc: row?.unique_id_desc || '',
    definition: row?.definition || '',
  })
  dialogVisible.value = true
}

async function saveObject() {
  try {
    if (editing.value) {
      await updateObjectApi(editing.value.id, { ...objectForm })
    } else {
      await createObjectApi({ ...objectForm })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadObjects()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

onMounted(async () => {
  await loadDomains()
  await loadObjects()
})
</script>

<style scoped>
.card-title {
  font-weight: 600;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.list-tools {
  display: flex;
  gap: 8px;
}
.object-card {
  margin-top: 16px;
}
.empty-tip {
  color: #909399;
  font-size: 13px;
}
</style>
