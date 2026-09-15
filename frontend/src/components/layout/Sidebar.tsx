import { useAuth } from '@/auth/AuthProvider'
import { routePermission } from '@/auth/routes'
import { useLocation, NavLink as RouterNavLink } from 'react-router-dom'
import {
  NavLink,
  Menu,
  Stack,
  Group,
  ScrollArea,
  Box,
  Text,
  UnstyledButton,
} from '@mantine/core'
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
  Wallet,
  Search,
  Users,
  Trophy,
  Inbox,
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
  { to: '/budget', icon: Wallet, label: 'Budget' },
  { to: '/analysis', icon: Activity, label: 'Analysis' },
  { to: '/log', icon: BookOpen, label: 'Log', activePaths: ['/log', '/notes', '/supplements', '/biometrics', '/diet'] },
  { to: '/tools', icon: Wrench, label: 'Tools', activePaths: ['/tools', '/rankings'] },
  { to: '/profile', icon: User, label: 'Profile' },
  { to: '/profiles', icon: Search, label: 'Search' },
  { to: '/roster', icon: Users, label: 'Roster' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/my-notes', icon: Inbox, label: 'My notes' },
  { to: '/designer/competitions', icon: Trophy, label: 'Competitions' },
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
  { to: '/budget', icon: Wallet, label: 'Budget' },
  { to: '/tools', icon: Wrench, label: 'Tools', activePaths: ['/tools', '/rankings'] },
  { to: '/profile', icon: User, label: 'Profile' },
  { to: '/profiles', icon: Search, label: 'Search' },
  { to: '/roster', icon: Users, label: 'Roster' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/my-notes', icon: Inbox, label: 'My notes' },
  { to: '/designer/competitions', icon: Trophy, label: 'Competitions' },
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
  const { permissions } = useAuth()
  const visible = (item: NavItem) => !routePermission(item.to) || permissions.includes(routePermission(item.to)!)

  return (
    <Box
      h="calc(var(--app-viewport-height, 100dvh) - 60px)"
      style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}
    >
      <ScrollArea offsetScrollbars style={{ minHeight: 0, flex: 1 }}>
        <Stack gap={4} p={12}>
          {DESKTOP_NAV_ITEMS.filter(visible).map((item) => {
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
    </Box>
  )
}

function MobileMoreMenu() {
  const location = useLocation()
  const { permissions } = useAuth()
  const visible = (item: NavItem) => !routePermission(item.to) || permissions.includes(routePermission(item.to)!)
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
            flex: '1 1 0',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 3,
            minHeight: 48,
            minWidth: 0,
            padding: '6px 4px',
            borderRadius: 8,
            color: isMoreActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: isMoreActive ? 'var(--accent-blue-dim)' : 'transparent',
          }}
        >
          <MoreHorizontal size={22} strokeWidth={2} style={{ display: 'block' }} />
          <Text fz={10} fw={600} lh={1} ta="center" style={{ width: '100%' }}>More</Text>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown style={{ maxHeight: 'calc(var(--app-viewport-height, 100dvh) - 96px)', overflowY: 'auto' }}>
        {MOBILE_MORE_ITEMS.filter(visible).map((item) => {
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
  const { permissions } = useAuth()
  const visible = (item: NavItem) => !routePermission(item.to) || permissions.includes(routePermission(item.to)!)

  return (
    <Group justify="space-around" wrap="nowrap" p={6} style={{ height: '100%' }}>
      {MOBILE_MAIN_ITEMS.filter(visible).map((item) => {
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
              flex: '1 1 0',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 3,
              minHeight: 48,
              minWidth: 0,
              padding: '6px 4px',
              borderRadius: 8,
              color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-blue-dim)' : 'transparent',
            }}
          >
            <Icon size={22} strokeWidth={2} style={{ display: 'block' }} />
            <Text fz={10} fw={600} lh={1} ta="center" style={{ width: '100%' }}>{label}</Text>
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
