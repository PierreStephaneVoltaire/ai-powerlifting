import { useEffect, useRef } from 'react'
import {
  computeRemainingMs,
  useRestTimerStore,
} from '@/store/restTimerStore'
import {
  fireRestCompleteNotification,
  requestNotificationPermission,
} from '@/utils/restTimerNotifications'
import RestTimerBar from './RestTimerBar'
import RestTimerDialog from './RestTimerDialog'

const TICK_MS = 250

export default function RestTimerManager() {
  const status = useRestTimerStore((s) => s.status)
  const setRemainingMs = useRestTimerStore((s) => s.setRemainingMs)
  const markFinished = useRestTimerStore((s) => s.markFinished)
  const permissionRequestedRef = useRef(false)

  useEffect(() => {
    if (status !== 'running') return
    if (permissionRequestedRef.current) return
    permissionRequestedRef.current = true
    void requestNotificationPermission()
  }, [status])

  useEffect(() => {
    if (status !== 'running') return
    const interval = window.setInterval(() => {
      const state = useRestTimerStore.getState()
      const remaining = computeRemainingMs(state)
      setRemainingMs(remaining)
      if (remaining <= 0) {
        markFinished()
      }
    }, TICK_MS)
    return () => window.clearInterval(interval)
  }, [status, setRemainingMs, markFinished])

  useEffect(() => {
    if (status !== 'finished') return
    void fireRestCompleteNotification()
  }, [status])

  return (
    <>
      <RestTimerBar />
      <RestTimerDialog />
    </>
  )
}