<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { fetchHealth, fetchTopics, fetchKnowledge, auditUploadStream, auditSampleStream } from './api.js'
import { SAMPLES, KNOWLEDGE } from './samples.js'

const topics = ref([{ key: 'emission_standards', label: '排放标准准确性' }])
const topic = ref('emission_standards')
const mode = ref('')
const model = ref('')
const kb = ref(null)

const fileName = ref('')
const selectedFile = ref(null)
const dragging = ref(false)
const loading = ref(false)
const error = ref('')

const result = ref(null)
const activeSample = ref('')

// 审核进度：当前环节 + 进度百分比 + 预计剩余秒数
const STEPS = [
  { key: 'parse', label: '解析报告' },
  { key: 'retrieve', label: '检索知识库' },
  { key: 'llm', label: '大模型审核' },
  { key: 'format', label: '生成结果' }
]
const progress = ref(0)
const stageLabel = ref('')
const currentStage = ref('')
const eta = ref(null)
const elapsed = ref(0)
let ticker = null

const stepIndex = computed(() => STEPS.findIndex((s) => s.key === currentStage.value))
function stepState(i) {
  const cur = stepIndex.value
  if (cur < 0) return ''
  if (i < cur) return 'done'
  return i === cur ? 'active' : ''
}

function handleStage(p) {
  if (typeof p.progress === 'number') progress.value = p.progress
  if (p.label) stageLabel.value = p.label
  if (p.stage) currentStage.value = p.stage
  if (typeof p.eta === 'number') eta.value = p.eta
}

function startProgress() {
  stopProgress()
  progress.value = 0
  stageLabel.value = '正在准备…'
  currentStage.value = 'parse'
  eta.value = null
  elapsed.value = 0
  ticker = setInterval(() => {
    elapsed.value += 1
    if (eta.value !== null && eta.value > 0) eta.value -= 1
    // 长耗时的「大模型审核」阶段缓慢推进，避免进度条长时间静止
    if (currentStage.value === 'llm' && progress.value < 92) progress.value += 1
  }, 1000)
}

function stopProgress() {
  if (ticker) {
    clearInterval(ticker)
    ticker = null
  }
}

const statusText = computed(() => {
  if (mode.value === 'mock') return 'Mock 模式（离线示例，未调用模型）'
  if (mode.value === 'live') return `Live 模式（模型：${model.value || '—'}）`
  return '检测服务中…'
})

const severityClass = (s) => ({ 高: 'high', 中: 'mid', 低: 'low' }[s] || 'muted')

function onFilePicked(file) {
  if (!file) return
  selectedFile.value = file
  fileName.value = file.name
  activeSample.value = ''
  result.value = null
  error.value = ''
}

function handleFileInput(e) {
  const f = e.target.files && e.target.files[0]
  if (f) onFilePicked(f)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer.files && e.dataTransfer.files[0]
  if (f) onFilePicked(f)
}

async function run() {
  const f = selectedFile.value
  if (!f) {
    error.value = '请先选择或拖入一份报告文件，或点击下方「内置示例报告」'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  startProgress()
  try {
    result.value = await auditUploadStream(f, topic.value, handleStage)
  } catch (e) {
    error.value = e.message || '审核失败'
  } finally {
    stopProgress()
    loading.value = false
  }
}

async function runSample(sample) {
  loading.value = true
  error.value = ''
  result.value = null
  fileName.value = sample.title
  activeSample.value = sample.id
  startProgress()
  try {
    result.value = await auditSampleStream(sample.text, handleStage)
  } catch (e) {
    error.value = e.message || '审核失败'
  } finally {
    stopProgress()
    loading.value = false
  }
}

function basisText(b) {
  if (!b) return '—'
  const parts = []
  if (b.standard_name) parts.push(b.standard_name + (b.standard_no ? `（${b.standard_no}）` : ''))
  if (b.clause) parts.push(b.clause)
  if (b.pollutant || b.limit) {
    parts.push([b.pollutant, b.limit, b.unit].filter(Boolean).join(' '))
  }
  if (b.control_location) parts.push('控制位置：' + b.control_location)
  return parts.join(' · ') || '—'
}

onMounted(async () => {
  try {
    const [h, t, k] = await Promise.all([fetchHealth(), fetchTopics(), fetchKnowledge()])
    mode.value = h.mock_mode ? 'mock' : 'live'
    model.value = h.model || ''
    if (t && t.length) topics.value = t
    kb.value = k
  } catch (e) {
    mode.value = ''
  }
})

onUnmounted(() => stopProgress())
</script>

<template>
  <div class="container">
    <header class="header">
      <h1>环评AI知识库智能审查系统</h1>
      <p>内置法规标准知识库，上传报告或点选示例，一键生成结构化的排放标准审核结果</p>
    </header>

    <div class="card">
      <div class="row" style="margin-top: 0; justify-content: space-between">
        <h2 style="margin: 0">内置法规知识库</h2>
        <span class="meta-line">覆盖 {{ kb ? kb.total_documents : '—' }} 条条款 · {{ kb ? kb.total_sources : '—' }} 个来源</span>
      </div>
      <div v-for="g in KNOWLEDGE" :key="g.group" class="kb-group">
        <h3>{{ g.group }}</h3>
        <div class="kb-items">
          <span v-for="it in g.items" :key="it.no + it.name" class="kb-item">
            <strong>{{ it.no }}</strong><span v-if="it.name"> · {{ it.name }}</span>
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="row" style="margin-top: 0; justify-content: space-between">
        <h2 style="margin: 0">① 上传报告</h2>
        <span class="meta-line">{{ statusText }}</span>
      </div>

      <div
        class="dropzone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        @click="$refs.fileInput.click()"
      >
        <div class="filename">{{ fileName || '点击选择，或将文件拖拽到此处' }}</div>
        <div class="hint">支持 TXT / Markdown / DOCX / PDF 格式</div>
        <input
          id="file-input"
          ref="fileInput"
          type="file"
          accept=".txt,.md,.markdown,.docx,.pdf"
          style="display: none"
          @change="handleFileInput"
        />
      </div>

      <div class="row">
        <label>审核主题</label>
        <select v-model="topic">
          <option v-for="t in topics" :key="t.key" :value="t.key">{{ t.label }}</option>
        </select>
        <button :disabled="loading || !fileName" @click="run">
          {{ loading ? '审核中…' : '开始审核' }}
        </button>
      </div>
    </div>

    <div class="card">
      <div class="row" style="margin-top: 0; justify-content: space-between">
        <h2 style="margin: 0">② 或点选一份内置示例报告</h2>
        <span class="meta-line">无需上传，一键演示</span>
      </div>
      <div class="samples">
        <div
          v-for="s in SAMPLES"
          :key="s.id"
          class="sample-card"
          :class="{ active: activeSample === s.id }"
        >
          <div class="sample-head">
            <span class="sample-title">{{ s.title }}</span>
            <span class="sample-tag">{{ s.tag }}</span>
          </div>
          <div class="sample-desc">{{ s.desc }}</div>
          <button class="btn-ghost sample-btn" :disabled="loading" @click="runSample(s)">
            {{ loading && activeSample === s.id ? '审核中…' : '审核这份报告' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="card">
      <div class="progress-head">
        <span class="progress-label">{{ stageLabel }}</span>
        <span class="progress-eta">
          {{ eta !== null && eta > 0 ? `预计还需约 ${eta} 秒` : '即将完成…' }} · 已用 {{ elapsed }}s
        </span>
      </div>
      <div class="progress-track">
        <div class="progress-bar" :style="{ width: progress + '%' }"></div>
      </div>
      <div class="progress-steps">
        <span v-for="(s, i) in STEPS" :key="s.key" class="step" :class="stepState(i)">
          <span class="step-dot">{{ stepState(i) === 'done' ? '✓' : i + 1 }}</span>{{ s.label }}
        </span>
      </div>
    </div>

    <div v-if="error" class="card">
      <div class="error">{{ error }}</div>
    </div>

    <div v-if="result" class="card">
      <div class="row" style="margin-top: 0; justify-content: space-between; align-items: flex-start">
        <div>
          <h2 style="margin: 0 0 6px">③ 审核结果</h2>
          <div class="issue-title">{{ result.summary }}</div>
        </div>
        <div style="text-align: right">
          <span class="tag" :class="severityClass(result.risk_level)">整体风险 {{ result.risk_level }}</span>
          <div class="meta-line" style="margin-top: 6px">
            发现 {{ result.issues.length }} 个问题 · 用时 {{ result.elapsed_seconds }}s
          </div>
        </div>
      </div>

      <div style="margin-top: 16px">
        <div v-if="!result.issues.length" class="meta-line">未发现明显问题</div>
        <div v-for="issue in result.issues" :key="issue.id" class="issue">
          <div class="issue-head">
            <span class="issue-title">{{ issue.id }}</span>
            <span class="tag muted">{{ issue.category }}</span>
            <span class="tag" :class="severityClass(issue.severity)">风险 {{ issue.severity }}</span>
          </div>
          <div class="issue-desc">{{ issue.description }}</div>

          <div class="compare">
            <div class="box reported">
              <div class="lbl">报告中填写 / 声称</div>
              <div>{{ issue.reported || '（未明确）' }}</div>
            </div>
            <div class="box correct">
              <div class="lbl">正确依据（知识库）</div>
              <div>{{ basisText(issue.correct_basis) }}</div>
            </div>
          </div>

          <div v-if="issue.suggestion" class="suggestion">
            <strong>修改建议：</strong>{{ issue.suggestion }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="result && result.retrieved_sources && result.retrieved_sources.length" class="card">
      <h2>检索证据来源</h2>
      <div v-for="s in result.retrieved_sources" :key="s.rank" class="src-item">
        <span class="src-title">#{{ s.rank }} {{ s.title }}</span>
        <span class="tag muted" style="margin-left: 6px">{{ s.score }}</span>
        <div class="src-snippet">{{ s.source_id }} · {{ s.snippet }}</div>
      </div>
    </div>
  </div>
</template>