import { Request, Response } from 'express'
import { signToken, signState, verifyState } from '../middleware/auth'
import { getSettings, getSettingsByMappedPk } from '../services/userSettings'

const DISCORD_API = 'https://discord.com/api/v10'
const CLIENT_ID = process.env.DISCORD_CLIENT_ID || ''
const CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET || ''
const REDIRECT_URI = process.env.DISCORD_REDIRECT_URI || ''
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'
const COOKIE_DOMAIN = process.env.COOKIE_DOMAIN || ''
const COOKIE_SECURE = process.env.COOKIE_SECURE === 'true'

interface DiscordTokenResponse {
  access_token: string
  token_type: string
}

interface DiscordUser {
  id: string
  username: string
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

    const jwt = signToken({
      discord_id: discordUser.id,
      username: discordUser.username,
      avatar,
    })

    setAuthCookie(res, jwt)
    res.redirect(FRONTEND_URL)
  } catch (err) {
    console.error('Discord OAuth callback error:', err)
    res.redirect(`${FRONTEND_URL}/login?error=auth_failed`)
  }
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
    user: req.user ?? null,
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
