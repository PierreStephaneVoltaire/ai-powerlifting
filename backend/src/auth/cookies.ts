import type { Response } from 'express'

const COOKIE_SECURE = process.env.COOKIE_SECURE === 'true'
const COOKIE_DOMAIN = process.env.COOKIE_DOMAIN ?? ''

export function setAuthCookie(res: Response, token: string): void {
  res.cookie('pl_auth', token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: COOKIE_SECURE,
    path: '/',
    domain: COOKIE_DOMAIN || undefined,
    maxAge: 7 * 24 * 60 * 60 * 1000,
  })
}

export function clearAuthCookie(res: Response): void {
  res.clearCookie('pl_auth', {
    httpOnly: true,
    sameSite: 'lax',
    secure: COOKIE_SECURE,
    path: '/',
    domain: COOKIE_DOMAIN || undefined,
  })
}
