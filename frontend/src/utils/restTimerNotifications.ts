const NOTIFICATION_TAG = 'powerlifting-rest-timer'

export async function requestNotificationPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported'
  if (!('serviceWorker' in navigator)) return 'unsupported'
  if (Notification.permission === 'granted' || Notification.permission === 'denied') {
    return Notification.permission
  }
  try {
    return await Notification.requestPermission()
  } catch {
    return 'denied'
  }
}

export async function fireRestCompleteNotification(): Promise<void> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return
  if (typeof window === 'undefined' || !('Notification' in window)) return
  if (Notification.permission !== 'granted') return
  try {
    const registration = await navigator.serviceWorker.ready
    await registration.showNotification('Rest complete', {
      body: 'Time to start your next set.',
      tag: NOTIFICATION_TAG,
    })
  } catch {
  }
}