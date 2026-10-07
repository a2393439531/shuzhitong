<template>
  <div class="qa-layout">
    <!-- 左侧：历史 / 收藏 -->
    <el-card class="left-panel">
      <el-tabs v-model="historyTab" @tab-change="loadHistory">
        <el-tab-pane label="历史" name="history" />
        <el-tab-pane label="收藏" name="favorite" />
      </el-tabs>
      <div class="hist-list" v-loading="historyLoading">
        <div
          v-for="h in history"
          :key="h.id"
          class="hist-item"
          @click="loadHistItem(h)"
        >
          <div class="hist-q">{{ h.question }}</div>
          <div class="hist-meta">
            <el-tag :type="qaStatusType(h.status)" size="small">{{ qaStatusLabel(h.status) }}</el-tag>
            <span class="hist-time">{{ h.created_at || h.asked_at || '' }}</span>
          </div>
          <div class="hist-actions">
            <el-button link type="primary" size="small" @click.stop="rerunItem(h)">重跑</el-button>
            <el-button link type="danger" size="small" @click.stop="deleteItem(h)">删除</el-button>
          </div>
        </div>
        <el-empty v-if="!history.length" :description="historyTab === 'favorite' ? '暂无收藏' : '暂无历史'" />
      </div>
    </el-card>

    <!-- 右侧：对话区 -->
    <el-card class="right-panel">
      <!-- 示例问题 -->
      <div class="example-bar">
        <el-select v-model="baseCode" placeholder="基地：集团共性" clearable size="small" style="width: 170px">
          <el-option label="集团共性口径" value="" />
          <el-option v-for="b in bases" :key="b.code" :label="b.name + '（' + b.code + '）'" :value="b.code" />
        </el-select>
        <span class="example-label">试试问：</span>
        <el-button
          v-for="q in exampleQuestions"
          :key="q"
          size="small"
          round
          @click="sendQuestion(q)"
        >{{ q }}</el-button>
      </div>

      <!-- 消息流 -->
      <div ref="msgBoxRef" class="msg-box">
        <template v-for="msg in messages" :key="msg._uid">
          <!-- 提问气泡 -->
          <div v-if="msg.kind === 'question'" class="bubble-row right">
            <div class="bubble question-bubble">{{ msg.text }}</div>
          </div>

          <!-- 回答卡片 -->
          <div v-else class="bubble-row left">
            <el-card class="answer-card" shadow="hover">
              <div class="answer-head">
                <span class="answer-title">回答</span>
                <div>
                  <el-tag :type="qaStatusType(msg.status)" size="small">{{ qaStatusLabel(msg.status) }}</el-tag>
                  <el-button
                    link
                    :type="msg.is_favorite ? 'warning' : 'info'"
                    @click="toggleFavorite(msg)"
                    :title="msg.is_favorite ? '取消收藏' : '收藏'"
                  >
                    <el-icon :size="18"><Star :style="{ color: msg.is_favorite ? '#e6a23c' : '#c0c4cc' }" /></el-icon>
                  </el-button>
                </div>
              </div>

              <!-- refused / error -->
              <el-alert
                v-if="msg.status === 'refused' || msg.status === 'error'"
                :type="msg.status === 'refused' ? 'warning' : 'error'"
                :title="msg.status === 'refused' ? '无法回答' : '查询出错'"
                :description="msg.error || msg.interpretation || '未知原因'"
                show-icon
                style="margin-bottom: 12px"
              />

              <!-- need_clarify -->
              <div v-if="msg.status === 'need_clarify'" class="sec">
                <div class="sec-title">需要补充信息</div>
                <div class="chip-row">
                  <el-button
                    v-for="(c, i) in msg.clarify_questions || []"
                    :key="i"
                    size="small"
                    round
                    type="primary"
                    plain
                    @click="sendQuestion(fmtClarify(c))"
                  >{{ fmtClarify(c) }}</el-button>
                </div>
              </div>

              <!-- 五要素 -->
              <template v-if="msg.status === 'success'">
                <!-- ① 问题理解 -->
                <div class="sec">
                  <div class="sec-title">① 问题理解</div>
                  <el-tag v-if="msg.understanding?.intent" size="small">{{ msg.understanding.intent }}</el-tag>
                  <div class="chip-row" v-if="entityChips(msg).length">
                    <el-tag v-for="(e, i) in entityChips(msg)" :key="i" size="small" type="info" class="chip">{{ e }}</el-tag>
                  </div>
                  <div class="sec-text">{{ msg.understanding?.text || '-' }}</div>
                </div>

                <!-- ② 口径与范围 -->
                <div class="sec">
                  <div class="sec-title">② 口径与范围</div>
                  <el-descriptions :column="3" border size="small">
                    <el-descriptions-item label="口径">{{ msg.scope?.caliber || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="时间">{{ msg.scope?.time || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="组织">{{ msg.scope?.org || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="基地口径">{{ msg.scope?.base?.note || '集团共性口径' }}</el-descriptions-item>
                  </el-descriptions>
                </div>

                <!-- ③ 结论与图表 -->
                <div class="sec">
                  <div class="sec-title">③ 结论与图表</div>
                  <div class="interpretation">{{ msg.interpretation }}</div>
                  <div v-if="msg.chart?.chart_type === 'stat'" class="stat-value">{{ statValue(msg) }}</div>
                  <div v-if="hasChart(msg)" :ref="(el) => setChartEl(msg._uid, el)" class="qa-chart"></div>
                  <el-table v-if="msg.columns?.length" :data="msg.rows || []" size="small" max-height="280" style="margin-top: 8px">
                    <el-table-column
                      v-for="c in msg.columns"
                      :key="typeof c === 'string' ? c : c.key || c.prop"
                      :prop="typeof c === 'string' ? c : c.key || c.prop"
                      :label="typeof c === 'string' ? c : c.label || c.title || c.key"
                      show-overflow-tooltip
                    />
                  </el-table>
                  <div v-if="msg.row_count != null" class="row-count">共 {{ msg.row_count }} 行</div>
                </div>

                <!-- ④ 来源与质量 -->
                <div class="sec">
                  <div class="sec-title">④ 来源与质量</div>
                  <div v-for="(s, i) in msg.sources || []" :key="i" class="source-item">
                    <el-icon :size="14"><Document /></el-icon>
                    <span>{{ typeof s === 'string' ? s : s.name }}</span>
                    <span v-if="typeof s === 'object' && s.updated_at" class="source-time">更新于 {{ s.updated_at }}</span>
                  </div>
                  <div v-if="msg.quality_note" class="quality-note">{{ msg.quality_note }}</div>
                </div>

                <!-- ⑤ 追问方向 -->
                <div class="sec" v-if="(msg.follow_ups || []).length">
                  <div class="sec-title">⑤ 追问方向</div>
                  <div class="chip-row">
                    <el-button
                      v-for="(f, i) in msg.follow_ups"
                      :key="i"
                      size="small"
                      round
                      @click="fillInput(f)"
                    >{{ f }}</el-button>
                  </div>
                </div>
              </template>

              <!-- follow_ups（非 success 状态也展示） -->
              <div class="sec" v-if="msg.status !== 'success' && (msg.follow_ups || []).length">
                <div class="sec-title">换个问法</div>
                <div class="chip-row">
                  <el-button v-for="(f, i) in msg.follow_ups" :key="i" size="small" round @click="fillInput(f)">{{ f }}</el-button>
                </div>
              </div>

              <div class="answer-foot">
                <span v-if="msg.elapsed_ms != null">耗时 {{ msg.elapsed_ms }} ms</span>
                <span v-if="msg.via"> · via {{ msg.via }}</span>
              </div>
            </el-card>
          </div>
        </template>

        <el-empty v-if="!messages.length" description="在下方输入问题开始智能问数" />
      </div>

      <!-- 输入区 -->
      <div class="input-bar">
        <el-input
          v-model="input"
          placeholder="输入问题，如：近一年维修工单按期完成率是多少？"
          @keyup.enter="sendQuestion(input)"
          clearable
        />
        <el-button type="primary" @click="sendQuestion(input)" :loading="asking">发送</el-button>
        <el-button @click="clearChat">新对话</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Star, Document } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  askQaApi, listQaHistoryApi, favoriteQaApi, rerunQaApi, deleteQaApi,
  listBasesApi,
} from '../api/index.js'

const exampleQuestions = [
  '近一年维修工单按期完成率是多少？',
  'AFW-1000 备件消耗金额',
  'L-AFW-001 的三码关系',
  '今天天气怎么样',
]

function qaStatusType(s) {
  const map = { success: 'success', need_clarify: 'warning', refused: 'danger', error: 'danger' }
  return map[s] || 'info'
}
function qaStatusLabel(s) {
  const map = { success: '已回答', need_clarify: '需澄清', refused: '已拒绝', error: '出错' }
  return map[s] || s || '-'
}
function fmtClarify(c) {
  return typeof c === 'string' ? c : c?.question || c?.text || JSON.stringify(c)
}

let uidSeq = 0
function newMsg(partial) {
  return { _uid: `m${++uidSeq}`, ...partial }
}

// ---------- 图表 ----------
const chartEls = reactive({})
const chartInstances = {}

function setChartEl(key, el) {
  if (el) chartEls[key] = el
  else delete chartEls[key]
}

function hasChart(msg) {
  const t = msg.chart?.chart_type
  return ['bar', 'line', 'pie'].includes(t)
}

function seriesData(s) {
  if (Array.isArray(s)) return s
  if (s && typeof s === 'object') return s.data || []
  return []
}

function buildChartOption(msg) {
  const chart = msg.chart
  const x = chart.x || chart.categories || []
  const series = Array.isArray(chart.series) ? chart.series : [chart.series].filter(Boolean)
  if (chart.chart_type === 'pie') {
    const values = seriesData(series[0])
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie',
        radius: '60%',
        data: x.map((name, i) => ({ name, value: values[i] })),
      }],
    }
  }
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: x },
    yAxis: { type: 'value' },
    series: series.map((s) => ({
      name: typeof s === 'object' ? s.name : undefined,
      type: chart.chart_type === 'line' ? 'line' : 'bar',
      smooth: true,
      data: seriesData(s),
    })),
  }
}

function renderCharts() {
  for (const key of Object.keys(chartEls)) {
    const msg = messages.value.find((m) => m._uid === key)
    if (!msg || !hasChart(msg)) continue
    const el = chartEls[key]
    if (!el || chartInstances[key]) continue
    const inst = echarts.init(el)
    inst.setOption(buildChartOption(msg))
    chartInstances[key] = inst
  }
}

function disposeCharts() {
  for (const key of Object.keys(chartInstances)) {
    chartInstances[key]?.dispose()
    delete chartInstances[key]
  }
}

// ---------- 对话 ----------
const messages = ref([])
const input = ref('')
const asking = ref(false)
const msgBoxRef = ref(null)

function fillInput(text) {
  input.value = text
}

function clearChat() {
  messages.value = []
  disposeCharts()
}

function entityChips(msg) {
  const e = msg.understanding?.entities
  if (Array.isArray(e)) return e.map((x) => (typeof x === 'string' ? x : JSON.stringify(x)))
  if (e && typeof e === 'object') return Object.entries(e).map(([k, v]) => `${k}: ${v}`)
  return []
}

function statValue(msg) {
  if (msg.value != null) return msg.value
  const row = (msg.rows || [])[0]
  if (row) {
    if (typeof row === 'object') {
      const vals = Object.values(row)
      if (vals.length) return vals[0]
    }
    return row
  }
  return msg.interpretation || '-'
}

function scrollToBottom() {
  nextTick(() => {
    const el = msgBoxRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function pushAnswer(data) {
  const msg = newMsg({ kind: 'answer', ...(data || {}) })
  messages.value.push(msg)
  nextTick(renderCharts)
  scrollToBottom()
  return msg
}

async function sendQuestion(text) {
  const question = (text || '').trim()
  if (!question || asking.value) return
  messages.value.push(newMsg({ kind: 'question', text: question }))
  input.value = ''
  scrollToBottom()
  asking.value = true
  try {
    const { data } = await askQaApi({ question, base_code: baseCode.value || undefined })
    pushAnswer(data)
    if (historyTab.value === 'history') loadHistory()
  } catch (e) {
    pushAnswer({ status: 'error', question, error: e?.response?.data?.detail || e?.response?.data?.message || '请求失败' })
  } finally {
    asking.value = false
  }
}

// ---------- 收藏 ----------
async function toggleFavorite(msg) {
  if (!msg.id) {
    ElMessage.warning('该回答尚未落库，无法收藏')
    return
  }
  try {
    const next = !msg.is_favorite
    await favoriteQaApi(msg.id, { is_favorite: next })
    msg.is_favorite = next
    ElMessage.success(next ? '已收藏' : '已取消收藏')
    if (historyTab.value === 'favorite') loadHistory()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

// ---------- 历史 / 收藏 ----------
const historyTab = ref('history')
const history = ref([])
const historyLoading = ref(false)

function asList(data) {
  return Array.isArray(data) ? data : data?.items || []
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const params = {}
    if (historyTab.value === 'favorite') params.favorite_only = true
    const { data } = await listQaHistoryApi(params)
    history.value = asList(data)
  } catch (e) {
    ElMessage.error('历史记录加载失败')
  } finally {
    historyLoading.value = false
  }
}

function loadHistItem(h) {
  messages.value.push(newMsg({ kind: 'question', text: h.question }))
  pushAnswer({ ...h })
}

async function rerunItem(h) {
  try {
    const { data } = await rerunQaApi(h.id)
    messages.value.push(newMsg({ kind: 'question', text: data?.question || h.question }))
    pushAnswer(data)
  } catch (e) {
    ElMessage.error('重跑失败')
  }
}

async function deleteItem(h) {
  try {
    await ElMessageBox.confirm('确定删除这条问答记录吗？', '提示', { type: 'warning' })
    await deleteQaApi(h.id)
    ElMessage.success('已删除')
    loadHistory()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

function onResize() {
  Object.values(chartInstances).forEach((c) => c?.resize())
}

const bases = ref([])
const baseCode = ref('')

async function loadBases() {
  try {
    const { data } = await listBasesApi()
    bases.value = Array.isArray(data) ? data : []
  } catch (_) { /* 忽略 */ }
}

onMounted(() => {
  loadHistory()
  loadBases()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.qa-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  height: calc(100vh - 140px);
  min-height: 520px;
}
.left-panel {
  width: 290px;
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.right-panel {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.hist-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 2px;
}
.hist-item {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
}
.hist-item:hover {
  border-color: #a0cfff;
}
.hist-q {
  font-size: 13px;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.hist-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.hist-time {
  font-size: 11px;
  color: #c0c4cc;
}
.hist-actions {
  text-align: right;
}
.example-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 12px;
}
.example-label {
  font-size: 13px;
  color: #909399;
}
.msg-box {
  flex: 1;
  overflow-y: auto;
  padding: 4px 2px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bubble-row {
  display: flex;
}
.bubble-row.right {
  justify-content: flex-end;
}
.bubble-row.left {
  justify-content: flex-start;
}
.question-bubble {
  background: #409eff;
  color: #fff;
  border-radius: 12px 12px 2px 12px;
  padding: 10px 14px;
  max-width: 70%;
  font-size: 14px;
  line-height: 1.6;
}
.answer-card {
  width: 100%;
  max-width: 100%;
}
.answer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.answer-title {
  font-weight: 600;
  font-size: 15px;
}
.sec {
  margin-bottom: 16px;
}
.sec-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.sec-text {
  font-size: 13px;
  color: #606266;
  margin-top: 6px;
  line-height: 1.6;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.chip {
  margin: 0;
}
.interpretation {
  font-size: 14px;
  color: #303133;
  line-height: 1.7;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 36px;
  font-weight: bold;
  color: #409eff;
  margin: 8px 0;
}
.qa-chart {
  width: 100%;
  height: 300px;
  margin-top: 8px;
}
.row-count {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
.source-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}
.source-time {
  font-size: 12px;
  color: #c0c4cc;
}
.quality-note {
  font-size: 12px;
  color: #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 6px 10px;
  margin-top: 6px;
}
.answer-foot {
  font-size: 12px;
  color: #c0c4cc;
  text-align: right;
}
.input-bar {
  display: flex;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}
</style>
