import { Request, Response } from 'express'
import { signToken, signState, verifyState, type AuthToken } from '../middleware/auth'
import { getSettings, getSettingsByMappedPk } from '../services/userSettings'
import { invalidateAllForUser } from '../utils/cache'

const DISCORD_API = 'https://discord.com/api/v10'
const CLIENT_ID = process.env.DISCORD_CLIENT_ID || ''
const CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET || ''
const REDIRECT_URI = process.env.DISCORD_REDIRECT_URI || ''
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'
const COOKIE_DOMAIN = process.env.COOKIE_DOMAIN || ''
const COOKIE_SECURE = process.env.COOKIE_SECURE === 'true'

// Authentik OIDC configuration (FEAT-4.1)
const AUTHENTIK_CLIENT_ID = process.env.AUTHENTIK_CLIENT_ID || ''
const AUTHENTIK_CLIENT_SECRET = process.env.AUTHENTIK_CLIENT_SECRET || ''
const AUTHENTIK_ISSUER_URL = (process.env.AUTHENTIK_ISSUER_URL || '').replace(/\/$/, '')
const AUTHENTIK_REDIRECT_URI = process.env.AUTHENTIK_REDIRECT_URI || ''

export function isAuthentikEnabled(): boolean {
  return Boolean(AUTHENTIK_CLIENT_ID && AUTHENTIK_CLIENT_SECRET && AUTHENTIK_ISSUER_URL && AUTHENTIK_REDIRECT_URI)
}

interface DiscordTokenResponse {
  access_token: string
  token_type: string
  scope?: string
}

interface DiscordUser {
  id: string
  username: string
  global_name?: string | null
  avatar: string | null
}

async function exchangeCode(code: string): Promise<DiscordTokenResponse> {
  const res = await fetch(`${DISCORD_API}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      grant_type: 'authorization_code',
      code,
      redirect_uri: REDIRECT_URI,
    }),
  })
  if (!res.ok) throw new Error(`Discord token exchange failed: ${res.status}`)
  return res.json() as Promise<DiscordTokenResponse>
}

async function fetchDiscordUser(accessToken: string): Promise<DiscordUser> {
  const res = await fetch(`${DISCORD_API}/users/@me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) throw new Error(`Discord user fetch failed: ${res.status}`)
  return res.json() as Promise<DiscordUser>
}

function setAuthCookie(res: Response, token: string): void {
  res.cookie('pl_auth', token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: COOKIE_SECURE,
    path: '/',
    domain: COOKIE_DOMAIN || undefined,
    maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days
  })
}

function clearAuthCookie(res: Response): void {
  res.clearCookie('pl_auth', {
    httpOnly: true,
    sameSite: 'lax',
    secure: COOKIE_SECURE,
    path: '/',
    domain: COOKIE_DOMAIN || undefined,
  })
}

export function discordLogin(_req: Request, res: Response): void {
  const state = signState()
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: 'identify',
    state,
  })
  res.redirect(`https://discord.com/api/oauth2/authorize?${params}`)
}

export async function discordCallback(req: Request, res: Response): Promise<void> {
  const { code, state } = req.query
  if (!code || typeof code !== 'string') {
    res.redirect(`${FRONTEND_URL}/login?error=no_code`)
    return
  }
  if (!state || typeof state !== 'string' || !verifyState(state)) {
    res.redirect(`${FRONTEND_URL}/login?error=invalid_state`)
    return
  }

  try {
    const tokens = await exchangeCode(code)
    const discordUser = await fetchDiscordUser(tokens.access_token)
    const avatar = discordUser.avatar
      ? `https://cdn.discordapp.com/avatars/${discordUser.id}/${discordUser.avatar}.png`
      : null

    const tokenPayload: AuthToken = {
      provider: 'discord',
      sub: discordUser.id,
      username: discordUser.username,
      display_name: discordUser.global_name || discordUser.username,
      avatar,
      groups: [],
      roles: [],
      email: null,
      discord_id: discordUser.id,
    }

    const jwt = signToken(tokenPayload)
    setAuthCookie(res, jwt)
    try {
      const existingSettings = await getSettings(discordUser.username)
      if (existingSettings?.mapped_pk) {
        await invalidateAllForUser(existingSettings.mapped_pk)
      }
    } catch (err) {
      console.warn('Failed to invalidate user cache on new login:', err)
    }
    res.redirect(FRONTEND_URL)
  } catch (err) {
    console.error('Discord OAuth callback error:', err)
    res.redirect(`${FRONTEND_URL}/login?error=auth_failed`)
  }
}

interface AuthentikTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  id_token: string
  refresh_token?: string
  scope?: string
}

interface AuthentikClaims {
  sub: string
  preferred_username?: string
  email?: string
  name?: string
  groups?: string[]
  roles?: string[]
  picture?: string
}

async function exchangeAuthentikCode(code: string): Promise<AuthentikTokenResponse> {
  if (!isAuthentikEnabled()) throw new Error('Authentik is not configured')
  const tokenUrl = `${AUTHENTIK_ISSUER_URL}/token/`
  const res = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: AUTHENTIK_CLIENT_ID,
      client_secret: AUTHENTIK_CLIENT_SECRET,
      grant_type: 'authorization_code',
      code,
      redirect_uri: AUTHENTIK_REDIRECT_URI,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Authentik token exchange failed: ${res.status} ${body}`)
  }
  return res.json() as Promise<AuthentikTokenResponse>
}

async function fetchAuthentikClaims(accessToken: string): Promise<AuthentikClaims> {
  if (!isAuthentikEnabled()) throw new Error('Authentik is not configured')
  const userinfoUrl = `${AUTHENTIK_ISSUER_URL}/userinfo/`
  const res = await fetch(userinfoUrl, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) throw new Error(`Authentik userinfo failed: ${res.status}`)
  return res.json() as Promise<AuthentikClaims>
}

export function authentikLogin(_req: Request, res: Response): void {
  if (!isAuthentikEnabled()) {
    res.redirect(`${FRONTEND_URL}/login?error=authentik_disabled`)
    return
  }
  const state = signState()
  const nonce = signState()
  const params = new URLSearchParams({
    client_id: AUTHENTIK_CLIENT_ID,
    redirect_uri: AUTHENTIK_REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email groups roles',
    state,
    nonce,
  })
  const authUrl = `${AUTHENTIK_ISSUER_URL}/authorize/?${params.toString()}`
  res.redirect(authUrl)
}

export async function authentikCallback(req: Request, res: Response): Promise<void> {
  const { code, state } = req.query
  if (!code || typeof code !== 'string') {
    res.redirect(`${FRONTEND_URL}/login?error=no_code`)
    return
  }
  if (!state || typeof state !== 'string' || !verifyState(state)) {
    res.redirect(`${FRONTEND_URL}/login?error=invalid_state`)
    return
  }
  if (!isAuthentikEnabled()) {
    res.redirect(`${FRONTEND_URL}/login?error=authentik_disabled`)
    return
  }

  try {
    const tokens = await exchangeAuthentikCode(code)
    const claims = await fetchAuthentikClaims(tokens.access_token)
    const raw = String(claims.preferred_username || claims.email || `authentik_${claims.sub}`).toLowerCase()
    const username = raw.replace(/[^a-z0-9_-]/g, '_').slice(0, 32) || `authentik_${claims.sub}`

    const tokenPayload: AuthToken = {
      provider: 'authentik',
      sub: claims.sub,
      username,
      display_name: claims.name || claims.preferred_username || username,
      avatar: claims.picture ?? null,
      groups: Array.isArray(claims.groups) ? claims.groups : [],
      roles: Array.isArray(claims.roles) ? claims.roles : [],
      email: claims.email ?? null,
      discord_id: '',
    }

    const jwt = signToken(tokenPayload)
    setAuthCookie(res, jwt)
    try {
      const existingSettings = await getSettings(username)
      if (existingSettings?.mapped_pk) {
        await invalidateAllForUser(existingSettings.mapped_pk)
      }
    } catch (err) {
      console.warn('Failed to invalidate user cache on new login:', err)
    }
    res.redirect(FRONTEND_URL)
  } catch (err) {
    console.error('Authentik OAuth callback error:', err)
    res.redirect(`${FRONTEND_URL}/login?error=authentik_failed`)
  }
}

export function listProviders(_req: Request, res: Response): void {
  res.json({
    discord: { enabled: Boolean(CLIENT_ID && CLIENT_SECRET && REDIRECT_URI) },
    authentik: { enabled: isAuthentikEnabled() },
  })
}

export async function getMe(req: Request, res: Response): Promise<void> {
  let ranking_country: string | null = null
  let ranking_region: string | null = null
  let age_class: string = 'open'
  try {
    let settings = null
    if (req.user?.username) {
      settings = await getSettings(req.user.username)
    }
    if (!settings && req.mapped_pk) {
      settings = await getSettingsByMappedPk(req.mapped_pk)
    }
    if (settings) {
      ranking_country = settings.ranking_country
      ranking_region = settings.ranking_region
      age_class = settings.age_class
    }
  } catch {}
  res.json({
    user: req.user
      ? {
          provider: req.user.identity.provider,
          sub: req.user.identity.sub,
          username: req.user.identity.username,
          display_name: req.user.identity.display_name,
          avatar: req.user.identity.avatar,
          groups: req.user.identity.groups,
          roles: req.user.identity.roles,
          email: req.user.identity.email,
          discord_id: req.user.discord_id,
        }
      : null,
    mapped_pk: req.mapped_pk ?? 'operator',
    readOnly: req.readOnly ?? true,
    ranking_country,
    ranking_region,
    age_class,
  })
}

export function logout(_req: Request, res: Response): void {
  clearAuthCookie(res)
  res.json({ ok: true })
}
