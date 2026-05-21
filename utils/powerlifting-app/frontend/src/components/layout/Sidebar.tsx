import { useLocation, NavLink as RouterNavLink } from 'react-router-dom'
import {
  NavLink,
  Menu,
  Stack,
  Group,
  ScrollArea,
  Badge,
  Box,
  Text,
  UnstyledButton,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import {
  LayoutDashboard,
  Calendar,
  Wrench,
  Activity,
  Info,
  MoreHorizontal,
  ClipboardList,
  BookOpen,
  User,
} from 'lucide-react'

interface SidebarProps {
  mobile?: boolean
}

interface NavItem {
  to: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  label: string
  activePaths?: string[]
}

const DESKTOP_NAV_ITEMS: NavItem[] = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: Calendar, label: 'Sessions' },
  { to: '/designer', icon: ClipboardList, label: 'Designer' },
  { to: '/analysis', icon: Activity, label: 'Analysis' },
  { to: '/log', icon: BookOpen, label: 'Log', activePaths: ['/log', '/notes', '/supplements', '/biometrics', '/diet'] },
  { to: '/tools', icon: Wrench, label: 'Tools', activePaths: ['/tools', '/rankings'] },
  { to: '/profile', icon: User, label: 'Profile' },
  { to: '/about', icon: Info, label: 'About' },
]

const MOBILE_MAIN_ITEMS: NavItem[] = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: Calendar, label: 'Sessions' },
  { to: '/analysis', icon: Activity, label: 'Analysis' },
  { to: '/log', icon: BookOpen, label: 'Log', activePaths: ['/log', '/notes', '/supplements', '/biometrics', '/diet'] },
]

const MOBILE_MORE_ITEMS: NavItem[] = [
  { to: '/designer', icon: ClipboardList, label: 'Designer' },
  { to: '/tools', icon: Wrench, label: 'Tools', activePaths: ['/tools', '/rankings'] },
  { to: '/profile', icon: User, label: 'Profile' },
  { to: '/about', icon: Info, label: 'About' },
]

function isActiveItem(item: NavItem, pathname: string): boolean {
  const paths = item.activePaths ?? [item.to]
  return paths.some((path) => (
    path === '/'
      ? pathname === '/'
      : pathname === path || pathname.startsWith(`${path}/`)
  ))
}

function DesktopSidebar() {
  const location = useLocation()
  const { version, program } = useProgramStore()
  const versionLabel = program?.meta?.version_label || version || 'current'

  return (
    <Box
      h="calc(var(--app-viewport-height, 100dvh) - 60px)"
      style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}
    >
      <ScrollArea offsetScrollbars style={{ minHeight: 0, flex: 1 }}>
        <Stack gap={4} p={12}>
          {DESKTOP_NAV_ITEMS.map((item) => {
            const { to, icon: Icon, label } = item
            const isActive = isActiveItem(item, location.pathname)

            return (
              <NavLink
                key={to}
                component={RouterNavLink}
                to={to}
                end={to === '/'}
                label={label}
                leftSection={<Icon size={16} />}
                active={isActive}
                variant="subtle"
                className="if-sidebar-link"
                data-testid={`desktop-nav-${label.toLowerCase()}`}
                styles={{
                  label: {
                    fontSize: 13,
                    fontWeight: 500,
                  },
                }}
              />
            )
          })}
        </Stack>
      </ScrollArea>
      <Box p={12} style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <Badge
          variant="outline"
          size="xs"
          color="gray"
          style={{
            borderColor: 'var(--border-default)',
            color: 'var(--text-muted)',
            fontSize: 10,
            letterSpacing: '0.08em',
          }}
        >
          Version {versionLabel}
        </Badge>
      </Box>
    </Box>
  )
}

function MobileMoreMenu() {
  const location = useLocation()
  const isMoreActive = MOBILE_MORE_ITEMS.some((item) => isActiveItem(item, location.pathname))

  return (
    <Menu shadow="md" position="top-end" withArrow offset={8}>
      <Menu.Target>
        <UnstyledButton
          aria-label="More"
          data-active={isMoreActive || undefined}
          data-testid="mobile-nav-more"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 3,
            minHeight: 48,
            minWidth: 56,
            padding: '6px 4px',
            borderRadius: 8,
            color: isMoreActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: isMoreActive ? 'var(--accent-blue-dim)' : 'transparent',
          }}
        >
          <MoreHorizontal size={22} />
          <Text fz={10} fw={600} lh={1}>More</Text>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        {MOBILE_MORE_ITEMS.map((item) => {
          const { to, icon: Icon, label } = item
          const isActive = isActiveItem(item, location.pathname)

          return (
            <Menu.Item
              key={to}
              component={RouterNavLink}
              to={to}
              leftSection={<Icon size={16} />}
              color={isActive ? 'blue' : undefined}
            >
              {label}
            </Menu.Item>
          )
        })}
      </Menu.Dropdown>
    </Menu>
  )
}

function MobileSidebar() {
  const location = useLocation()

  return (
    <Group justify="space-around" wrap="nowrap" p={6}>
      {MOBILE_MAIN_ITEMS.map((item) => {
        const { to, icon: Icon, label } = item
        const isActive = isActiveItem(item, location.pathname)

        return (
          <UnstyledButton
            key={to}
            component={RouterNavLink}
            to={to}
            end={to === '/'}
            aria-label={label}
            data-active={isActive || undefined}
            data-testid={`mobile-nav-${label.toLowerCase()}`}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 3,
              minHeight: 48,
              minWidth: 56,
              padding: '6px 4px',
              borderRadius: 8,
              color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-blue-dim)' : 'transparent',
            }}
          >
            <Icon size={22} />
            <Text fz={10} fw={600} lh={1}>{label}</Text>
          </UnstyledButton>
        )
      })}
      <MobileMoreMenu />
    </Group>
  )
}

export default function Sidebar({ mobile = false }: SidebarProps) {
  return mobile ? <MobileSidebar /> : <DesktopSidebar />
}
