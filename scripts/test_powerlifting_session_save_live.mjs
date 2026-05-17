#!/usr/bin/env node
/**
 * Live regression test for powerlifting session save persistence.
 *
 * Defaults to the private Kubernetes test backend via a local port-forward.
 * It writes only to the test-mapped pk used by if-portals-test, verifies reload
 * persistence, then restores the original session payload.
 */

import { spawn } from 'node:child_process'

const namespace = process.env.POWERLIFTING_TEST_NAMESPACE || 'if-portals-test'
const localPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || 13005)
const defaultOrigin = `http://127.0.0.1:${localPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${defaultOrigin}/api`).replace(/\/$/, '')
const healthUrl = `${apiBase.replace(/\/api$/, '')}/health`
const runId = `session-save-${Date.now()}`

let portForward = null

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function canReach(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1500) })
    return response.ok
  } catch {
    return false
  }
}

async function ensurePortForward() {
  if (await canReach(healthUrl)) return
  if (process.env.POWERLIFTING_TEST_API_BASE_URL) {
    throw new Error(`Cannot reach configured POWERLIFTING_TEST_API_BASE_URL health endpoint: ${healthUrl}`)
  }

  portForward = spawn(
    'kubectl',
    ['-n', namespace, 'port-forward', 'svc/powerlifting-app-backend', `${localPort}:3005`],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  )

  let stderr = ''
  portForward.stderr.on('data', (chunk) => {
    stderr += String(chunk)
  })

  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await canReach(healthUrl)) return
    if (portForward.exitCode !== null) {
      throw new Error(`kubectl port-forward exited early: ${stderr.trim()}`)
    }
    await sleep(250)
  }

  throw new Error(`Timed out waiting for test backend port-forward: ${healthUrl}`)
}

async function request(path, init = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  })
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) {
    throw new Error(`${init.method || 'GET'} ${path} failed ${response.status}: ${JSON.stringify(body)}`)
  }
  return body
}

async function putSession(date, index, session) {
  await request(`/sessions/current/${encodeURIComponent(date)}/${index}`, {
    method: 'PUT',
    body: JSON.stringify(session),
  })
}

async function loadProgram() {
  return (await request('/programs/current')).data
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

async function main() {
  await ensurePortForward()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const program = await loadProgram()
  if (!Array.isArray(program.sessions) || program.sessions.length === 0) {
    throw new Error('Current test program has no sessions')
  }

  const index = 0
  const original = clone(program.sessions[index])
  const date = original.date

  try {
    const manualMarker = `${runId}-manual`
    const manual = { ...clone(original), session_notes: manualMarker }
    await putSession(date, index, manual)

    const afterManual = (await loadProgram()).sessions[index]
    if (afterManual.session_notes !== manualMarker) {
      throw new Error(`Manual save did not persist after reload. Expected ${manualMarker}, got ${afterManual.session_notes}`)
    }

    const staleMarker = `${runId}-autosave-stale`
    const latestMarker = `${runId}-autosave-latest`
    await putSession(date, index, { ...clone(afterManual), session_notes: staleMarker })
    await sleep(75)
    await putSession(date, index, { ...clone(afterManual), session_notes: latestMarker })

    const afterLatest = (await loadProgram()).sessions[index]
    if (afterLatest.session_notes !== latestMarker) {
      throw new Error(`Latest autosave payload did not win after reload. Expected ${latestMarker}, got ${afterLatest.session_notes}`)
    }

    console.log('[session-save-live] PASS')
    console.log(`  API base: ${apiBase}`)
    console.log(`  Session:  ${date} index ${index}`)
    console.log(`  Checked:  manual save persisted; latest autosave payload persisted`)
  } finally {
    await putSession(date, index, original)
    if (portForward) {
      portForward.kill('SIGTERM')
    }
  }
}

main().catch((error) => {
  if (portForward) {
    portForward.kill('SIGTERM')
  }
  console.error('[session-save-live] FAIL')
  console.error(error)
  process.exit(1)
})
