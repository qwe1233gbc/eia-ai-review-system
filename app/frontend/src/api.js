import { DEMO, sleep } from './demo-data.js'
import { KB_FALLBACK } from './samples.js'

// 探测到的运行模式：'live' = 已连后端；'demo' = 无后端（如 GitHub Pages）回退内置示例
let mode = null

async function tryJson(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) throw new Error('bad status ' + res.status)
  return res.json()
}

export async function fetchHealth() {
  try {
    const d = await tryJson('/api/health')
    if (d && d.status === 'ok') {
      mode = 'live'
      return d
    }
  } catch (e) {
    /* 无后端，走演示 */
  }
  mode = 'demo'
  return { ...DEMO.health }
}

export async function fetchTopics() {
  try {
    const t = await tryJson('/api/topics')
    if (t && t.length) return t
  } catch (e) {
    /* ignore */
  }
  return DEMO.topics
}

export async function fetchKnowledge() {
  try {
    const d = await tryJson('/api/knowledge')
    if (d && d.total_sources) return d
  } catch (e) {
    /* ignore */
  }
  return { ...KB_FALLBACK }
}

export function isDemo() {
  return mode !== 'live'
}

async function demoResult() {
  await sleep(800)
  return { ...DEMO.result }
}

export async function auditText(text, topic) {
  try {
    return await tryJson('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, topic })
    })
  } catch (e) {
    return demoResult()
  }
}

export async function auditUpload(file, topic) {
  if (!file) return demoResult()
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('topic', topic)
    return await tryJson('/api/audit/upload', { method: 'POST', body: form })
  } catch (e) {
    return demoResult()
  }
}

export async function auditSample(text) {
  // 无后端时直接返回内置示例；有后端则用给定文本走真实审核
  if (isDemo()) return demoResult()
  try {
    return await auditText(text || DEMO.sampleText, 'emission_standards')
  } catch (e) {
    return demoResult()
  }
}

// ============ 流式审核（SSE）：实时回传「当前环节 + 进度 + 预计剩余秒数」 ============

async function streamJson(url, options, onStage) {
  const res = await fetch(url, options)
  if (!res.ok || !res.body) throw new Error('bad status ' + res.status)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let result = null
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const chunks = buf.split('\n\n')
    buf = chunks.pop()
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      let payload
      try {
        payload = JSON.parse(line.slice(5).trim())
      } catch (e) {
        continue
      }
      if (payload.stage === 'done') {
        result = payload.result
      } else if (payload.stage === 'error') {
        throw new Error(payload.message || '审核失败')
      } else if (onStage) {
        onStage(payload)
      }
    }
  }
  if (!result) throw new Error('未收到审核结果')
  return result
}

async function demoStream(onStage) {
  const stages = [
    { stage: 'parse', label: '解析报告文本', progress: 20, eta: 3 },
    { stage: 'retrieve', label: '检索法规知识库', progress: 55, eta: 2 },
    { stage: 'llm', label: '调用大模型审核', progress: 80, eta: 1 },
    { stage: 'format', label: '生成结构化结果', progress: 95, eta: 0 }
  ]
  for (const s of stages) {
    if (onStage) onStage(s)
    await sleep(450)
  }
  return { ...DEMO.result }
}

export async function auditUploadStream(file, topic, onStage) {
  if (!file || isDemo()) return demoStream(onStage)
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('topic', topic)
    return await streamJson('/api/audit/upload/stream', { method: 'POST', body: form }, onStage)
  } catch (e) {
    return demoStream(onStage)
  }
}

export async function auditSampleStream(text, onStage) {
  if (isDemo()) return demoStream(onStage)
  try {
    return await streamJson(
      '/api/audit/stream',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text || DEMO.sampleText, topic: 'emission_standards' })
      },
      onStage
    )
  } catch (e) {
    return demoStream(onStage)
  }
}