import { useLocation, NavLink as RouterNavLink } from 'react-router-dom'
import {
  NavLink,
  Menu,
  Stack,
  Group,
  ScrollArea,
  ActionIcon,
} from '@mantine/core'
import {
  LayoutDashboard,
  Calendar,
  BarChart3,
  Wrench,
  Pill,
  Utensils,
  Trophy,
  TrendingUp,
  Activity,
  Film,
  Info,
  MoreHorizontal,
  ClipboardList,
} from 'lucide-react'

interface SidebarProps {
  mobile?: boolean
}

interface NavItem {
  to: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  label: string
}

const PRIMARY_NAV_ITEMS: NavItem[] = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: Calendar, label: 'Sessions' },
  { to: '/designer', icon: ClipboardList, label: 'Designer' },
  { to: '/charts', icon: BarChart3, label: 'Charts' },
  { to: '/analysis', icon: Activity, label: 'Analysis' },
  { to: '/rankings', icon: Trophy, label: 'Rankings' },
  { to: '/tools', icon: Wrench, label: 'Tools' },
]

const SECONDARY_NAV_ITEMS: NavItem[] = [
  { to: '/supplements', icon: Pill, label: 'Supplements' },
  { to: '/biometrics', icon: Utensils, label: 'Biometrics' },
  { to: '/maxes', icon: TrendingUp, label: 'Maxes' },
  { to: '/videos', icon: Film, label: 'Videos' },
]

const ALL_NAV_ITEMS: NavItem[] = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: Calendar, label: 'Sessions' },
  { to: '/designer', icon: ClipboardList, label: 'Designer' },
  { to: '/analysis', icon: Activity, label: 'Analysis' },
  { to: '/rankings', icon: Trophy, label: 'Rankings' },
  { to: '/supplements', icon: Pill, label: 'Supplements' },
  { to: '/biometrics', icon: Utensils, label: 'Biometrics' },
  { to: '/maxes', icon: TrendingUp, label: 'Maxes' },
  { to: '/tools', icon: Wrench, label: 'Tools' },
  { to: '/videos', icon: Film, label: 'Videos' },
  { to: '/about', icon: Info, label: 'About' },
]

function DesktopSidebar() {
  const location = useLocation()

  return (
    <ScrollArea
      h="calc(var(--app-viewport-height, 100dvh) - 60px)"
      offsetScrollbars
      style={{ minHeight: 0 }}
    >
      <Stack gap={4} p="md">
        {ALL_NAV_ITEMS.map(({ to, icon: Icon, label }) => {
          const isActive =
            to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(to)

          return (
            <NavLink
              key={to}
              component={RouterNavLink}
              to={to}
              end={to === '/'}
              label={label}
              leftSection={<Icon size={20} />}
              active={isActive}
              variant="light"
              color="blue"
              style={{ borderRadius: 'var(--mantine-radius-md)' }}
            />
          )
        })}
      </Stack>
    </ScrollArea>
  )
}

function MobileMoreMenu() {
  const location = useLocation()

  return (
    <Menu shadow="md" position="top-end" withArrow offset={8}>
      <Menu.Target>
        <ActionIcon
          variant="subtle"
          size="lg"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 2,
            height: 'auto',
            width: 'auto',
            padding: '8px',
          }}
        >
          <MoreHorizontal size={24} />
        </ActionIcon>
      </Menu.Target>

      <Menu.Dropdown>
        {ALL_NAV_ITEMS.filter(item => !['/', '/designer', '/sessions', '/analysis'].includes(item.to)).map(({ to, icon: Icon, label }) => {
          const isActive =
            to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(to)

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
  
  const MOBILE_MAIN_ITEMS = ALL_NAV_ITEMS.filter(item => ['/', '/designer', '/sessions', '/analysis'].includes(item.to))

  return (
    <Group justify="space-around" wrap="nowrap" p="xs">
      {MOBILE_MAIN_ITEMS.map(({ to, icon: Icon }) => {
        const isActive =
          to === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(to)

        return (
          <ActionIcon
            key={to}
            component={RouterNavLink}
            to={to}
            end={to === '/'}
            variant={isActive ? 'filled' : 'subtle'}
            color={isActive ? 'blue' : 'gray'}
            size="lg"
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              height: 'auto',
              width: 'auto',
              padding: '8px',
              minHeight: 44,
            }}
          >
            <Icon size={24} />
          </ActionIcon>
        )
      })}
      <MobileMoreMenu />
    </Group>
  )
}

export default function Sidebar({ mobile = false }: SidebarProps) {
  return mobile ? <MobileSidebar /> : <DesktopSidebar />
}
