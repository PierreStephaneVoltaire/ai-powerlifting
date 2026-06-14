import { ReactNode, useEffect } from 'react'
import { AppShell as MantineAppShell } from '@mantine/core'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import SettingsDrawer from './SettingsDrawer'
import ReadOnlyBanner from '@/components/shared/ReadOnlyBanner'
import RestTimerManager from '@/components/sessions/RestTimerManager'

interface AppShellProps {
  children: ReactNode
}

export default function AppShell({ children }: AppShellProps) {
  useEffect(() => {
    const handleViewportChange = () => {
      const visualViewport = window.visualViewport
      const viewportHeight = visualViewport?.height ?? window.innerHeight
      const viewportOffsetTop = visualViewport?.offsetTop ?? 0
      const bottomOverlap = Math.max(
        0,
        window.innerHeight - viewportHeight - viewportOffsetTop
      )

      document.documentElement.style.setProperty('--app-viewport-height', `${viewportHeight}px`)
      document.documentElement.style.setProperty('--app-browser-bottom-overlap', `${bottomOverlap}px`)
    }

    handleViewportChange()
    window.addEventListener('resize', handleViewportChange)
    window.addEventListener('orientationchange', handleViewportChange)
    window.visualViewport?.addEventListener('resize', handleViewportChange)
    window.visualViewport?.addEventListener('scroll', handleViewportChange)

    return () => {
      window.removeEventListener('resize', handleViewportChange)
      window.removeEventListener('orientationchange', handleViewportChange)
      window.visualViewport?.removeEventListener('resize', handleViewportChange)
      window.visualViewport?.removeEventListener('scroll', handleViewportChange)
    }
  }, [])

  return (
    <MantineAppShell
      header={{ height: 60 }}
      navbar={{
        width: 200,
        breakpoint: 'md',
        collapsed: { mobile: true },
      }}
      footer={{
        height: 'calc(60px + env(safe-area-inset-bottom, 0px))',
        offset: false,
      }}
      padding="md"
      style={{ 
        minHeight: 'var(--app-viewport-height, 100dvh)',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-base)',
        color: 'var(--text-primary)',
      }}
    >
      <MantineAppShell.Header
        style={{
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <TopBar />
      </MantineAppShell.Header>

      <MantineAppShell.Navbar
        style={{
          height: 'calc(var(--app-viewport-height, 100dvh) - 60px)',
          maxHeight: 'calc(var(--app-viewport-height, 100dvh) - 60px)',
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        <Sidebar />
      </MantineAppShell.Navbar>

      <MantineAppShell.Main
        pb={{
          base: 'calc(180px + env(safe-area-inset-bottom, 0px) + var(--app-browser-bottom-overlap, 0px))',
          md: 140
        }}
        style={{ flex: 1 }}
      >
        <ReadOnlyBanner />
        {children}
      </MantineAppShell.Main>

      {/* Mobile bottom navigation */}
      <MantineAppShell.Footer 
        hiddenFrom="md" 
        style={{ 
          position: 'fixed', 
          bottom: 0, 
          left: 0, 
          right: 0, 
          height: 'calc(60px + env(safe-area-inset-bottom, 0px))',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
          backgroundColor: 'var(--bg-surface)',
          borderTop: '1px solid var(--border-subtle)',
          zIndex: 100
        }}
      >
        <Sidebar mobile />
      </MantineAppShell.Footer>

      <SettingsDrawer />
      <RestTimerManager />
    </MantineAppShell>
  )
}
