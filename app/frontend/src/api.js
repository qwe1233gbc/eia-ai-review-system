import { DEMO, sleep } from './demo-data.js'

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

export async function auditSample() {
  // 无后端时直接返回内置示例；有后端则用示例文本走真实审核
  if (isDemo()) return demoResult()
  try {
    return await auditText(DEMO.sampleText, 'emission_standards')
  } catch (e) {
    return demoResult()
  }
}