import { useEffect, useState } from 'react'
import { Paper, SegmentedControl, Stack, Text, Title } from '@mantine/core'
import ProfileTags from '@/components/settings/ProfileTags'
import PublicationSettings from '@/components/settings/PublicationSettings'
import { RelationshipInbox } from '@/components/settings/RelationshipInbox'
import { RelationshipRoster } from '@/components/settings/RelationshipRoster'
import { GrantsPanel } from '@/components/settings/GrantsPanel'
import { getSettings, updateProfile, type UserSettings } from '@/api/settings'
import { useAuth, type ActiveRole } from '@/auth/AuthProvider'

export default function SettingsPage() {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [section, setSection] = useState('profile')
  const { user, person_pk, mapped_pk, selectRole } = useAuth('settings')
  useEffect(() => {
    let current = true
    setSettings(null)
    void getSettings().then(value => { if (current) setSettings(value) }).catch(() => { if (current) setSettings(null) })
    return () => { current = false }
  }, [person_pk, mapped_pk])
  return <Stack maw={720} mx="auto">
      <Title order={2}>Settings</Title>
    {user && user.roles.length > 1 && <SelectRole user={user} personPk={person_pk} onChange={selectRole} />}
    <SegmentedControl value={section} onChange={setSection} fullWidth data={[{ value: 'profile', label: 'Profile' }, { value: 'relationships', label: 'Roster' }, { value: 'inbox', label: 'Inbox' }]} />
    {section === 'profile' && <Paper withBorder p="md"><Stack>
      <Title order={3}>Profile and privacy</Title>
      {settings && <SegmentedControl value={settings.profile_visibility} onChange={async value => { const next = await updateProfile({ profile_visibility: value as 'private' | 'public', display_name: settings.display_name, bio: settings.bio }); setSettings(next) }} data={[{ value: 'private', label: 'Private' }, { value: 'public', label: 'Public' }]} fullWidth />}
      <ProfileTags settings={settings} onChange={setSettings} />
      <PublicationSettings />
    </Stack></Paper>}
    {section === 'relationships' && <Paper withBorder p="md"><Stack><Title order={3}>Relationships and roster</Title>{user?.active_role === 'athlete' && <GrantsPanel />}<RelationshipRoster /></Stack></Paper>}
    {section === 'inbox' && <Paper withBorder p="md"><Stack><Title order={3}>Inbox</Title><RelationshipInbox /></Stack></Paper>}
    {!settings && section === 'profile' && <Text c="dimmed">Profile settings are unavailable.</Text>}
  </Stack>
}

function SelectRole({ user, personPk, onChange }: { user: { roles: string[]; active_role: ActiveRole | null }; personPk: string; onChange: (role: ActiveRole) => void }) {
  return <SegmentedControl value={user.active_role || ''} onChange={value => { sessionStorage.setItem(`nolift-role-view:${personPk}`, value); onChange(value as ActiveRole) }} data={user.roles.map(role => ({ value: role, label: role[0].toUpperCase() + role.slice(1) }))} fullWidth />
}
