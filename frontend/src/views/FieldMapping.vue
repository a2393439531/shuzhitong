<template>
  <div>
    <el-card>
      <div class="filter-bar">
        <el-input v-model="query.source_system" placeholder="来源系统" clearable style="width: 180px" />
        <el-select v-model="query.object_id" placeholder="业务对象" clearable style="width: 200px">
          <el-option v-for="o in objects" :key="o.id" :label="`${o.code || ''} ${o.name || ''}`" :value="o.id" />
        </el-select>
        <el-button type="primary" @click="loadMappings">搜索</el-button>
        <el-button @click="openDialog()">新增映射</el-button>
      </div>
      <el-table :data="mappings" v-loading="loading">
        <el-table-column prop="source_system" label="来源系统" width="140" />
        <el-table-column prop="source_table" label="来源表" width="160" show-overflow-tooltip />
        <el-table-column prop="source_field" label="来源字段" width="160" show-overflow-tooltip />
        <el-table-column prop="standard_code" label="标准编号" width="130" />
        <el-table-column prop="model_code" label="主数据模型" width="140" />
        <el-table-column prop="md_attr" label="主数据属性" width="140" show-overflow-tooltip />
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑字段映射' : '新增字段映射'" width="600px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="来源系统"><el-input v-model="form.source_system" placeholder="如 设备管理系统" /></el-form-item>
        <el-form-item label="来源表"><el-input v-model="form.source_table" placeholder="如 EQ_EQUIPMENT" /></el-form-item>
        <el-form-item label="来源字段"><el-input v-model="form.source_field" placeholder="如 EQ_NAME" /></el-form-item>
        <el-form-item label="业务对象">
          <el-select v-model="form.object_id" clearable placeholder="请选择" style="width: 100%">
            <el-option v-for="o in objects" :key="o.id" :label="`${o.code || ''} ${o.name || ''}`" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="对应标准">
          <el-select v-model="form.standard_id" clearable filterable placeholder="请选择数据标准" style="width: 100%">
            <el-option v-for="s in standards" :key="s.id" :label="`${s.standard_code || s.code || ''} ${s.standard_name || s.name || ''}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="主数据模型">
          <el-select v-model="form.md_model_id" clearable filterable placeholder="请选择主数据模型" style="width: 100%">
            <el-option v-for="m in mdModels" :key="m.id" :label="`${m.code} ${m.name}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="主数据属性"><el-input v-model="form.md_attr" placeholder="如 设备名称" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listFieldMappingsApi,
  createFieldMappingApi,
  updateFieldMappingApi,
  deleteFieldMappingApi,
  listObjectsApi,
  listStandardsApi,
  listMdModelsApi,
} from '../api/index.js'

const mappings = ref([])
const loading = ref(false)
const query = reactive({ source_system: '', object_id: null })

const objects = ref([])
const standards = ref([])
const mdModels = ref([])

const dialogVisible = ref(false)
const editing = ref(null)
const submitting = ref(false)
const form = reactive({
  source_system: '',
  source_table: '',
  source_field: '',
  object_id: null,
  standard_id: null,
  md_model_id: null,
  md_attr: '',
  remark: '',
})

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}

async function loadMappings() {
  loading.value = true
  try {
    const params = {}
    if (query.source_system) params.source_system = query.source_system
    if (query.object_id) params.object_id = query.object_id
    const { data } = await listFieldMappingsApi(params)
    mappings.value = asList(data)
  } catch (e) {
    ElMessage.error('字段映射加载失败')
  } finally {
    loading.value = false
  }
}

async function loadDicts() {
  try {
    const [{ data: o }, { data: s }, { data: m }] = await Promise.all([
      listObjectsApi(),
      listStandardsApi(),
      listMdModelsApi(),
    ])
    objects.value = asList(o)
    standards.value = asList(s)
    mdModels.value = asList(m)
  } catch (_) {}
}

function openDialog(row) {
  editing.value = row || null
  Object.assign(form, {
    source_system: row?.source_system || '',
    source_table: row?.source_table || '',
    source_field: row?.source_field || '',
    object_id: row?.object_id || null,
    standard_id: row?.standard_id || null,
    md_model_id: row?.md_model_id || null,
    md_attr: row?.md_attr || '',
    remark: row?.remark || '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.source_system || !form.source_field) {
    ElMessage.warning('请填写来源系统和来源字段')
    return
  }
  const body = { ...form }
  Object.keys(body).forEach((k) => {
    if (body[k] === '' || body[k] === null) delete body[k]
  })
  submitting.value = true
  try {
    if (editing.value) {
      await updateFieldMappingApi(editing.value.id, body)
      ElMessage.success('映射已更新')
    } else {
      await createFieldMappingApi(body)
      ElMessage.success('映射已创建')
    }
    dialogVisible.value = false
    loadMappings()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    submitting.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除该字段映射吗？`, '提示', { type: 'warning' })
    await deleteFieldMappingApi(row.id)
    ElMessage.success('已删除')
    loadMappings()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(() => {
  loadMappings()
  loadDicts()
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
