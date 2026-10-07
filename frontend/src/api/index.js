import http from './http.js'

// ---------- 认证 ----------
export const loginApi = (username, password) =>
  http.post('/auth/login', { username, password })
export const meApi = () => http.get('/auth/me')

// ---------- 领域 / 业务对象 ----------
export const listDomainsApi = () => http.get('/domains')
export const listObjectsApi = (params) => http.get('/objects', { params })
export const createObjectApi = (data) => http.post('/objects', data)
export const getObjectApi = (id) => http.get(`/objects/${id}`)
export const updateObjectApi = (id, data) => http.put(`/objects/${id}`, data)
export const getObjectCardApi = (id) => http.get(`/objects/${id}/card`)

// ---------- 业务流程 ----------
export const listProcessesApi = () => http.get('/processes')
export const getProcessApi = (id) => http.get(`/processes/${id}`)

// ---------- 标准 ----------
export const listStandardsApi = (params) => http.get('/standards', { params })
export const getStandardApi = (id) => http.get(`/standards/${id}`)
export const submitStandardApi = (id) => http.post(`/standards/${id}/submit`)
export const getStandardAdoptionApi = (id) =>
  http.get(`/standards/${id}/adoption`)

// ---------- 数据目录 / 资源 ----------
export const listResourcesApi = (params) => http.get('/resources', { params })
export const getResourceApi = (id) => http.get(`/resources/${id}`)
export const submitResourceApi = (id) => http.post(`/resources/${id}/submit`)
export const offlineResourceApi = (id) => http.post(`/resources/${id}/offline`)

// ---------- 字段认责 ----------
export const listResponsibilitiesApi = (params) =>
  http.get('/responsibilities', { params })

// ---------- 数据质量 ----------
export const listQualityApi = (params) => http.get('/quality', { params })
export const createQualityApi = (data) => http.post('/quality', data)
export const updateQualityApi = (id, data) => http.put(`/quality/${id}`, data)

// ---------- 审批 ----------
export const listApprovalsApi = (params) => http.get('/approvals', { params })
export const getApprovalApi = (id) => http.get(`/approvals/${id}`)
export const decideApprovalApi = (id, decision, comment) =>
  http.post(`/approvals/${id}/decide`, { decision, comment })

// ---------- 审计 ----------
export const listAuditApi = (params) => http.get('/audit', { params })

// ---------- 仪表盘 ----------
export const dashboardApi = () => http.get('/dashboard')

// ---------- 系统配置（只读，admin） ----------
export const getSystemConfigApi = () => http.get('/system/config')

// ---------- 大模型辅助 ----------
export const llmStatusApi = () => http.get('/llm/status')
export const llmExplainApi = (data) => http.post('/llm/explain', data)

// ---------- 二期：主数据 ----------
export const listMdModelsApi = (params) => http.get('/masterdata/models', { params })
export const createMdModelApi = (data) => http.post('/masterdata/models', data)
export const getMdModelApi = (id) => http.get(`/masterdata/models/${id}`)
export const applyMdModelApi = (id, data) => http.post(`/masterdata/models/${id}/apply`, data)
export const listMdApplicationsApi = (params) => http.get('/masterdata/applications', { params })
export const reviewMdApplicationApi = (id, data) => http.post(`/masterdata/applications/${id}/review`, data)
export const listMdRecordsApi = (params) => http.get('/masterdata/records', { params })
export const getMdRecordApi = (id) => http.get(`/masterdata/records/${id}`)
export const updateMdRecordApi = (id, data) => http.put(`/masterdata/records/${id}`, data)
export const distributeMdRecordApi = (id, data) => http.post(`/masterdata/records/${id}/distribute`, data)
export const createCodeMapApi = (data) => http.post('/masterdata/code-map', data)
export const listCodeMapsApi = (params) => http.get('/masterdata/code-map', { params })
export const createDeviceLinkApi = (data) => http.post('/masterdata/device-links', data)
export const listDeviceLinksApi = (params) => http.get('/masterdata/device-links', { params })

// ---------- 二期：字段映射 ----------
export const listFieldMappingsApi = (params) => http.get('/field-mappings', { params })
export const createFieldMappingApi = (data) => http.post('/field-mappings', data)
export const updateFieldMappingApi = (id, data) => http.put(`/field-mappings/${id}`, data)
export const deleteFieldMappingApi = (id) => http.delete(`/field-mappings/${id}`)

// ---------- 二期：质量规则 ----------
export const listQualityRulesApi = (params) => http.get('/quality/rules', { params })
export const createQualityRuleApi = (data) => http.post('/quality/rules', data)
export const updateQualityRuleApi = (id, data) => http.put(`/quality/rules/${id}`, data)
export const deleteQualityRuleApi = (id) => http.delete(`/quality/rules/${id}`)
export const toggleQualityRuleApi = (id) => http.patch(`/quality/rules/${id}/toggle`)
export const runQualityRuleApi = (id) => http.post(`/quality/rules/${id}/run`)
export const runAllQualityRulesApi = () => http.post('/quality/rules/run-all')
export const listQualityRunsApi = (params) => http.get('/quality/runs', { params })
export const getQualityRunApi = (id) => http.get(`/quality/runs/${id}`)
export const listQualitySchedulesApi = (params) => http.get('/quality/schedule', { params })
export const createQualityScheduleApi = (data) => http.post('/quality/schedule', data)
export const triggerDueSchedulesApi = () => http.post('/quality/schedule/trigger-due')
// 问题整改（复用既有 listQualityApi 列表接口）
export const confirmIssueApi = (id, data) => http.post(`/quality/issues/${id}/confirm`, data)
export const fixIssueApi = (id, data) => http.post(`/quality/issues/${id}/fix`, data)
export const recheckIssueApi = (id) => http.post(`/quality/issues/${id}/recheck`)
export const closeIssueApi = (id, data) => http.post(`/quality/issues/${id}/close`, data)

// ---------- 二期：落标检查 ----------
export const runComplianceApi = (data) => http.post('/compliance/run', data)
export const listComplianceChecksApi = (params) => http.get('/compliance/checks', { params })
export const getComplianceCheckApi = (id) => http.get(`/compliance/checks/${id}`)
export const getSystemStatusApi = (params) => http.get('/compliance/system-status', { params })

// ---------- 三期：服务中心 ----------
export const listServicesApi = () => http.get('/services')
export const getServiceApi = (id) => http.get(`/services/${id}`)
export const createServiceApi = (data) => http.post('/services', data)
export const updateServiceApi = (id, data) => http.put(`/services/${id}`, data)
export const publishServiceApi = (id) => http.post(`/services/${id}/publish`)
export const offlineServiceApi = (id) => http.post(`/services/${id}/offline`)
export const subscribeServiceApi = (id) => http.post(`/services/${id}/subscribe`)
export const listMySubscriptionsApi = () => http.get('/services/subscriptions/mine')
export const reviewSubscriptionApi = (subId, data) => http.post(`/services/subscriptions/${subId}/review`, data)
export const invokeServiceApi = (code, data) => http.post(`/services/${code}/invoke`, data)
export const getServiceStatsApi = (id) => http.get(`/services/${id}/stats`)
export const listServiceNoticesApi = () => http.get('/services/notices')

// ---------- 三期：指标中心 ----------
export const listMetricsApi = () => http.get('/metrics')
export const getMetricApi = (code) => http.get(`/metrics/${code}`)
export const createMetricApi = (data) => http.post('/metrics', data)
export const updateMetricApi = (code, data) => http.put(`/metrics/${code}`, data)
export const computeMetricApi = (code, data) => http.post(`/metrics/${code}/compute`, data)
export const getMetricTrendApi = (code, params) => http.get(`/metrics/${code}/trend`, { params })
export const listMetricVersionsApi = (code) => http.get(`/metrics/${code}/versions`)
export const compareMetricVersionsApi = (code, params) => http.get(`/metrics/${code}/compare`, { params })

// ---------- 三期：智能问数 ----------
export const askQaApi = (data) => http.post('/qa/ask', data)
export const listQaHistoryApi = (params) => http.get('/qa/history', { params })
export const favoriteQaApi = (id, data) => http.patch(`/qa/history/${id}/favorite`, data)
export const rerunQaApi = (id) => http.post(`/qa/history/${id}/rerun`)
export const deleteQaApi = (id) => http.delete(`/qa/history/${id}`)

// ---------- 四期：多基地配置 ----------
export const listBasesApi = () => http.get('/bases')
export const createBaseApi = (data) => http.post('/bases', data)
export const getBaseApi = (code) => http.get(`/bases/${code}`)
export const listStdDiffsApi = (params) => http.get('/bases/diffs/standards', { params })
export const createStdDiffApi = (standardId, data) => http.post(`/bases/diffs/standards?standard_id=${standardId}`, data)
export const publishStdDiffApi = (id) => http.post(`/bases/diffs/standards/${id}/publish`)
export const listIndDiffsApi = (params) => http.get('/bases/diffs/indicators', { params })
export const createIndDiffApi = (indicatorId, data) => http.post(`/bases/diffs/indicators?indicator_id=${indicatorId}`, data)
export const publishIndDiffApi = (id) => http.post(`/bases/diffs/indicators/${id}/publish`)
export const effectiveStandardApi = (id, baseCode) => http.get(`/bases/effective/standard/${id}`, { params: { base_code: baseCode } })
export const effectiveIndicatorApi = (code, baseCode) => http.get(`/bases/effective/indicator/${code}`, { params: { base_code: baseCode } })

// ---------- 四期：变更中心 ----------
export const listChangesApi = (params) => http.get('/changes', { params })
export const createChangeApi = (data) => http.post('/changes', data)
export const getChangeApi = (id) => http.get(`/changes/${id}`)
export const submitChangeApi = (id) => http.post(`/changes/${id}/submit`)
export const confirmChangeApi = (id, data) => http.post(`/changes/${id}/confirm`, data)
export const effectChangeApi = (id) => http.post(`/changes/${id}/effect`)
export const rejectChangeApi = (id, data) => http.post(`/changes/${id}/reject`, data)
export const rollbackChangeApi = (id) => http.post(`/changes/${id}/rollback`)

// ---------- 四期：运营大盘 ----------
export const opsOverviewApi = () => http.get('/ops/overview')
export const auditTrendApi = (params) => http.get('/ops/audit-trend', { params })
