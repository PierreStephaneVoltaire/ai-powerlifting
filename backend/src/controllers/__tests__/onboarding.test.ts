/**
 * Integration test for the onboarding routes. Boots the express app,
 * stubs the userSettings service via a real HTTP fake-Lambda server
 * (the real one calls AWS, so we point it at us). Exercises the
 * role -> profile -> athlete_basics flow end-to-end.
 *
 * Run with:  npx tsx src/controllers/__tests__/onboarding.test.ts
 */
import express from 'express'
import http from 'http'
import cookieParser from 'cookie-parser'
import { AddressInfo } from 'net'

let failures = 0
function check(name: string, cond: boolean, info?: unknown): void {
  if (cond) {
    console.log(`  PASS  ${name}`)
  } else {
    console.log(`  FAIL  ${name}`, info ?? '')
    failures += 1
  }
}

type Settings = {
  username: string
  display_name: string
  bio: string
  profile_visibility: 'private' | 'public'
  public_training_summary_enabled: boolean
  sex: 'male' | 'female' | null
  country: string | null
  region: string | null
  bodyweight_kg: number | null
  training_maxes: { squat_kg: number; bench_kg: number; deadlift_kg: number } | null
  federations: string[]
  roles: string[]
  active_role: string | null
  profile_complete: boolean
  athlete_basics_complete: boolean
}

const VALID_ROLES = new Set(['athlete', 'coach', 'handler'])
const VALID_SEX = new Set(['male', 'female'])

const store: Record<string, Settings> = {}

function defaultSettings(username: string): Settings {
  return {
    username,
    display_name: '',
    bio: '',
    profile_visibility: 'private',
    public_training_summary_enabled: false,
    sex: null,
    country: null,
    region: null,
    bodyweight_kg: null,
    training_maxes: null,
    federations: [],
    roles: [],
    active_role: null,
    profile_complete: false,
    athlete_basics_complete: false,
  }
}

function validateAthleteBasics(input: any) {
  if (!input || typeof input !== 'object') throw new Error('Body must be a JSON object')
  if (input.sex !== 'male' && input.sex !== 'female') throw new Error('sex must be male or female')
  const country = String(input.country || '').toUpperCase()
  if (!country) throw new Error('country is required')
  const region = input.region == null ? null : String(input.region).trim() || null
  const bw = Number(input.bodyweight_kg)
  if (!Number.isFinite(bw) || bw < 30 || bw > 300) throw new Error('bodyweight_kg must be 30..300')
  const tm = input.training_maxes
  if (!tm || typeof tm !== 'object') throw new Error('training_maxes is required')
  const s = Number(tm.squat_kg), b = Number(tm.bench_kg), d = Number(tm.deadlift_kg)
  if (![s, b, d].every((x) => Number.isFinite(x) && x > 0)) {
    throw new Error('training maxes must all be positive numbers')
  }
  return { sex: input.sex, country, region, bodyweight_kg: bw, training_maxes: { squat_kg: s, bench_kg: b, deadlift_kg: d } }
}

function validateOnboardingProfile(input: any) {
  if (!input || typeof input !== 'object') throw new Error('Body must be a JSON object')
  if (typeof input.display_name !== 'string' || !input.display_name.trim()) {
    throw new Error('display_name is required')
  }
  const display_name = input.display_name.trim().slice(0, 80)
  const bio = typeof input.bio === 'string' ? input.bio.slice(0, 280) : ''
  const profile_visibility: 'private' | 'public' =
    input.profile_visibility === 'public' ? 'public' : 'private'
  const summary = input.public_training_summary_enabled === true
  let federations: string[] = []
  if (input.federations !== undefined) {
    if (!Array.isArray(input.federations)) throw new Error('federations must be an array of strings')
    const seen: string[] = []
    for (const item of input.federations) {
      if (typeof item !== 'string') throw new Error('federations items must be strings')
      const v = item.trim()
      if (v && !seen.includes(v)) seen.push(v)
      if (seen.length >= 20) break
    }
    federations = seen
  }
  return { display_name, bio, profile_visibility, public_training_summary_enabled: summary, federations }
}

function validateRoleInput(input: any) {
  if (!input || typeof input !== 'object') throw new Error('Body must be a JSON object')
  if (!Array.isArray(input.roles) || input.roles.length === 0) {
    throw new Error('roles must be a non-empty array')
  }
  const seen: string[] = []
  for (const item of input.roles) {
    if (typeof item !== 'string' || !VALID_ROLES.has(item)) throw new Error(`Unknown role: ${String(item)}`)
    if (!seen.includes(item)) seen.push(item)
  }
  const active = input.active_role
  if (active !== undefined && active !== null) {
    if (typeof active !== 'string' || !VALID_ROLES.has(active)) throw new Error(`Unknown active_role: ${String(active)}`)
    if (!seen.includes(active)) throw new Error('active_role must be one of the assigned roles')
  }
  return { roles: seen, active_role: active ?? seen[0] }
}

function applyAthleteBasics(settings: Settings, input: any): Settings {
  const v = validateAthleteBasics(input)
  return { ...settings, ...v, athlete_basics_complete: true }
}
function applyOnboardingProfile(settings: Settings, input: any): Settings {
  const v = validateOnboardingProfile(input)
  return { ...settings, ...v, profile_complete: true }
}
function applyRole(settings: Settings, input: any): Settings {
  const v = validateRoleInput(input)
  return { ...settings, roles: v.roles, active_role: v.active_role }
}

function deriveStatus(settings: Settings) {
  const roles = settings.roles || []
  const active = settings.active_role
  const has_athlete_basics =
    settings.bodyweight_kg != null &&
    settings.training_maxes != null &&
    settings.sex != null &&
    VALID_SEX.has(settings.sex)
  let next_step = 'done'
  if (roles.length === 0) next_step = 'role'
  else if (!settings.profile_complete) next_step = 'profile'
  else if (roles.includes('athlete') && !has_athlete_basics) next_step = 'athlete_basics'
  return {
    is_onboarded: next_step === 'done',
    next_step,
    state: {
      roles,
      active_role: active,
      athlete_basics_complete: !!settings.athlete_basics_complete,
      profile_complete: !!settings.profile_complete,
    },
    has_athlete_basics,
  }
}

function startFakeLambda(): Promise<http.Server> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let buf = ''
      req.on('data', (c) => (buf += c))
      req.on('end', () => {
        const body = buf ? JSON.parse(buf) : {}
        const route = (req.url || '').split('?')[0]
        // The fission_server.py wrapper expects each handler to return
        // either a `{ statusCode, body }` dict (which gets jsonified back out)
        // or a plain JSON-serialisable value. The actual lambda handlers
        // return `{statusCode: 200, body: json.dumps(settings_dict)}` and the
        // backend's invokeLambda() unwraps that. So the HTTP body our fake
        // emits is the same wire format the real fission server would emit.
        const respond = (status: number, payload: any) => {
          res.statusCode = status
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ statusCode: status, body: JSON.stringify(payload) }))
        }
        try {
          if (route === '/pod_user') {
            const fn = body.function
            const username = body.username
            if (fn === 'settings_get') {
              if (!store[username]) return respond(200, null)
              return respond(200, { ...store[username] })
            }
            if (fn === 'settings_create') {
              const u = body.username || body.discord_id
              if (!store[u]) store[u] = defaultSettings(u)
              return respond(200, { ...store[u] })
            }
            if (fn === 'settings_update_athlete_basics') {
              if (!store[username]) store[username] = defaultSettings(username)
              store[username] = applyAthleteBasics(store[username], body.input)
              return respond(200, { ...store[username] })
            }
            if (fn === 'settings_update_onboarding_profile') {
              if (!store[username]) store[username] = defaultSettings(username)
              store[username] = applyOnboardingProfile(store[username], body.input)
              return respond(200, { ...store[username] })
            }
            if (fn === 'settings_update_role') {
              if (!store[username]) store[username] = defaultSettings(username)
              store[username] = applyRole(store[username], { roles: body.roles, active_role: body.active_role })
              return respond(200, { ...store[username] })
            }
            return respond(400, { error: `Unknown function: ${fn}` })
          }
          respond(404, { error: `Unknown route: ${route}` })
        } catch (err) {
          respond(400, { error: err instanceof Error ? err.message : 'bad request' })
        }
      })
    })
    server.listen(0, () => resolve(server))
  })
}

function startBackendApp(onboardingRouter: any): Promise<http.Server> {
  const app = express()
  app.use(express.json())
  app.use(cookieParser())
  app.use((req: any, _res, next) => {
    req.user = {
      identity: {
        provider: 'discord',
        sub: 'discord:1',
        username: 'testuser',
        display_name: 'Test User',
        avatar: null,
        groups: [],
        roles: [],
        active_role: null,
        email: null,
      },
      discord_id: '111',
      username: 'testuser',
      mapped_pk: 'testuser',
      readOnly: false,
    }
    next()
  })
  app.use('/api/onboarding', onboardingRouter)
  return new Promise((resolve) => {
    const server = app.listen(0, () => resolve(server))
  })
}

async function jsonReq(
  server: http.Server,
  method: 'GET' | 'POST',
  path: string,
  body?: any,
): Promise<{ status: number; body: any }> {
  const port = (server.address() as AddressInfo).port
  const payload = body !== undefined ? JSON.stringify(body) : undefined
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: '127.0.0.1',
        port,
        method,
        path,
        headers: {
          'Content-Type': 'application/json',
          ...(payload ? { 'Content-Length': Buffer.byteLength(payload) } : {}),
        },
      },
      (res) => {
        let buf = ''
        res.on('data', (c) => (buf += c))
        res.on('end', () => {
          let parsed: any = null
          try { parsed = buf ? JSON.parse(buf) : null } catch { parsed = buf }
          resolve({ status: res.statusCode ?? 0, body: parsed })
        })
      },
    )
    req.on('error', reject)
    if (payload) req.write(payload)
    req.end()
  })
}

async function main() {
  store['testuser'] = defaultSettings('testuser')
  // Start the fake Lambda backend first, then point the real backend at it.
  const lambdaServer = await startFakeLambda()
  const lambdaPort = (lambdaServer.address() as AddressInfo).port
  process.env.POWERLIFTING_LAMBDA_BASE_URL = `http://127.0.0.1:${lambdaPort}`
  process.env.INTERNAL_API_TOKEN = 'test'

  // Dynamic import so the userSettings -> lambda module chain picks up the
  // env vars we just set (the LAMBDA_BASE_URL const is captured at module
  // load time, so we have to set the env before importing the router).
  const { onboardingRouter } = await import('../../routes/onboarding')

  const backendServer = await startBackendApp(onboardingRouter)

  // 1) /status on a brand-new user — should be at the role step.
  const status0 = await jsonReq(backendServer, 'GET', '/api/onboarding/status')
  check('GET /status initial 200', status0.status === 200, status0.body)
  check('GET /status initial next_step=role', status0.body?.data?.next_step === 'role', status0.body)
  check('GET /status initial is_onboarded=false', status0.body?.data?.is_onboarded === false)

  // 2) POST /role
  const roleRes = await jsonReq(backendServer, 'POST', '/api/onboarding/role', {
    roles: ['athlete', 'coach'],
    active_role: 'athlete',
  })
  check('POST /role 200', roleRes.status === 200, roleRes.body)
  check(
    'POST /role persisted roles',
    Array.isArray(roleRes.body?.data?.roles) &&
      roleRes.body.data.roles.includes('athlete') &&
      roleRes.body.data.roles.includes('coach'),
    roleRes.body,
  )
  check('POST /role persisted active_role', roleRes.body?.data?.active_role === 'athlete', roleRes.body)

  // 3) POST /profile
  const profileRes = await jsonReq(backendServer, 'POST', '/api/onboarding/profile', {
    display_name: 'Test User',
    bio: 'Stronger than yesterday',
    profile_visibility: 'public',
    public_training_summary_enabled: true,
    federations: ['ipf', 'usapl'],
  })
  check('POST /profile 200', profileRes.status === 200, profileRes.body)
  check('POST /profile profile_complete=true', profileRes.body?.data?.profile_complete === true, profileRes.body)
  check(
    'POST /profile federations stored',
    JSON.stringify(profileRes.body?.data?.federations) === JSON.stringify(['ipf', 'usapl']),
    profileRes.body,
  )

  // 4) POST /athlete-basics
  const basicsRes = await jsonReq(backendServer, 'POST', '/api/onboarding/athlete-basics', {
    sex: 'male',
    country: 'us',
    region: ' ca ',
    bodyweight_kg: 82.5,
    training_maxes: { squat_kg: 180, bench_kg: 120, deadlift_kg: 220 },
  })
  check('POST /athlete-basics 200', basicsRes.status === 200, basicsRes.body)
  check('POST /athlete-basics athlete_basics_complete=true', basicsRes.body?.data?.athlete_basics_complete === true, basicsRes.body)
  check('POST /athlete-basics bodyweight kept', Number(basicsRes.body?.data?.bodyweight_kg) === 82.5, basicsRes.body)
  check('POST /athlete-basics training_maxes kept', basicsRes.body?.data?.training_maxes?.squat_kg === 180, basicsRes.body)
  check('POST /athlete-basics active_role preserved', basicsRes.body?.data?.active_role === 'athlete', basicsRes.body)

  // 5) /status — done
  const status1 = await jsonReq(backendServer, 'GET', '/api/onboarding/status')
  check('GET /status final 200', status1.status === 200, status1.body)
  check('GET /status final is_onboarded=true', status1.body?.data?.is_onboarded === true, status1.body)
  check('GET /status final next_step=done', status1.body?.data?.next_step === 'done', status1.body)

  // 6) Validation: zero squat rejected
  const bad = await jsonReq(backendServer, 'POST', '/api/onboarding/athlete-basics', {
    sex: 'male',
    country: 'US',
    bodyweight_kg: 80,
    training_maxes: { squat_kg: 0, bench_kg: 100, deadlift_kg: 200 },
  })
  check('POST /athlete-basics rejects zero', bad.status === 400, bad.body)

  // 7) Validation: empty roles rejected
  const badRole = await jsonReq(backendServer, 'POST', '/api/onboarding/role', {
    roles: [],
    active_role: 'athlete',
  })
  check('POST /role rejects empty', badRole.status === 400, badRole.body)

  // 8) Validation: missing display_name rejected
  const badProfile = await jsonReq(backendServer, 'POST', '/api/onboarding/profile', { bio: 'no name' })
  check('POST /profile rejects missing display_name', badProfile.status === 400, badProfile.body)

  // 9) Cross-check: the on-disk store matches the derived status logic.
  const expected = deriveStatus(store['testuser'])
  check('store matches derived status', expected.is_onboarded === true && expected.next_step === 'done', expected)

  backendServer.close()
  lambdaServer.close()

  if (failures === 0) {
    console.log('\nOK')
  } else {
    console.log(`\n${failures} test(s) failed`)
    process.exit(1)
  }
}

main().catch((err) => {
  console.error('Test runner crashed:', err)
  process.exit(1)
})
