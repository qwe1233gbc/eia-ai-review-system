<script setup>
import { ref, onMounted, computed } from 'vue'
import { fetchHealth, fetchTopics, auditUpload, auditSample } from './api.js'

const topics = ref([{ key: 'emission_standards', label: '排放标准准确性' }])
const topic = ref('emission_standards')
const mode = ref('')
const model = ref('')

const fileName = ref('')
const dragging = ref(false)
const loading = ref(false)
const error = ref('')

const result = ref(null)

const statusText = computed(() => {
  if (mode.value === 'mock') return 'Mock 模式（离线示例，未调用模型）'
  if (mode.value === 'live') return `Live 模式（模型：${model.value || '—'}）`
  return '检测服务中…'
})

const severityClass = (s) => ({ 高: 'high', 中: 'mid', 低: 'low' }[s] || 'muted')

function onFilePicked(file) {
  if (!file) return
  fileName.value = file.name
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
  const input = document.querySelector('#file-input')
  const f = input && input.files && input.files[0]
  if (!f) {
    error.value = '请先选择或拖入一份报告文件，或点击「加载内置示例」'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await auditUpload(f, topic.value)
  } catch (e) {
    error.value = e.message || '审核失败'
  } finally {
    loading.value = false
  }
}

async function runSample() {
  loading.value = true
  error.value = ''
  result.value = null
  fileName.value = '示例报告.md'
  try {
    result.value = await auditSample()
  } catch (e) {
    error.value = e.message || '审核失败'
  } finally {
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
    const [h, t] = await Promise.all([fetchHealth(), fetchTopics()])
    mode.value = h.mock_mode ? 'mock' : 'live'
    model.value = h.model || ''
    if (t && t.length) topics.value = t
  } catch (e) {
    mode.value = ''
  }
})
</script>

<template>
  <div class="container">
    <header class="header">
      <h1>环评AI知识库智能审查系统</h1>
      <p>上传环评报告，检索法规知识库并调用大模型，生成结构化的排放标准审核结果</p>
    </header>

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
        <button class="btn-ghost" :disabled="loading" @click="runSample">加载内置示例</button>
      </div>
    </div>

    <div v-if="loading" class="card">
      <div class="loading">正在解析报告、检索知识库并生成审核结果…</div>
    </div>

    <div v-if="error" class="card">
      <div class="error">{{ error }}</div>
    </div>

    <div v-if="result" class="card">
      <div class="row" style="margin-top: 0; justify-content: space-between; align-items: flex-start">
        <div>
          <h2 style="margin: 0 0 6px">② 审核结果</h2>
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