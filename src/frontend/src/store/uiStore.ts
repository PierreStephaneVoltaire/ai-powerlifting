import { create } from 'zustand'
import { notifications } from '@mantine/notifications'

type DrawerType = 'session' | 'maxManager' | 'exercise' | 'settings' | null

interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'warning'
}

interface UiState {
  drawerOpen: boolean
  drawerType: DrawerType
  toasts: Toast[]
  sidebarCollapsed: boolean

  // Actions
  openDrawer: (type: DrawerType) => void
  closeDrawer: () => void
  pushToast: (toast: Omit<Toast, 'id'>) => void
  dismissToast: (id: string) => void
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
}

// Fallback for browsers that don't support crypto.randomUUID
const generateId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

export const useUiStore = create<UiState>()((set) => ({
  drawerOpen: false,
  drawerType: null,
  toasts: [],
  sidebarCollapsed: false,

  openDrawer: (type) => set({ drawerOpen: true, drawerType: type }),

  closeDrawer: () => set({ drawerOpen: false, drawerType: null }),

  pushToast: (toast) => {
    const id = generateId()
    const color = toast.type === 'success' ? 'green' : toast.type === 'warning' ? 'yellow' : 'red'
    notifications.show({ id, message: toast.message, color })
    set((s) => ({
      toasts: [...s.toasts, { ...toast, id }],
    }))
  },

  dismissToast: (id) =>
    set((s) => ({
      toasts: s.toasts.filter((t) => t.id !== id),
    })),

  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}))
