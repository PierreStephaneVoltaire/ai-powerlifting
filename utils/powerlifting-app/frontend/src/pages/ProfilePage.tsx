import { useEffect, useState } from 'react'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Group,
  Paper,
  SegmentedControl,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { AlertCircle, LogIn, Save, User } from 'lucide-react'
import { getSettings, updateNickname, updateProfile, type UserSettings } from '@/api/settings'
import { useAuth } from '@/auth/AuthProvider'
import { useUiStore } from '@/store/uiStore'

type ProfileVisibility = UserSettings['profile_visibility']

export default function ProfilePage() {
  const { user, loading: authLoading, readOnly, signIn } = useAuth()
  const { pushToast } = useUiStore()
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nickname, setNickname] = useState('')
  const [profileVisibility, setProfileVisibility] = useState<ProfileVisibility>('private')
  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [publicSummary, setPublicSummary] = useState(false)

  useEffect(() => {
    if (authLoading || !user) return

    let cancelled = false
    setLoading(true)
    setError(null)
    getSettings()
      .then((nextSettings) => {
        if (cancelled) return
        setSettings(nextSettings)
        setNickname(nextSettings.nickname)
        setProfileVisibility(nextSettings.profile_visibility)
        setDisplayName(nextSettings.display_name)
        setBio(nextSettings.bio)
        setPublicSummary(nextSettings.public_training_summary_enabled)
      })
      .catch(() => {
        if (!cancelled) setError('Profile settings are unavailable for this account.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [authLoading, user])

  async function saveProfile() {
    if (!settings || saving) return
    setSaving(true)
    setError(null)
    try {
      let nextSettings = settings
      const nextNickname = nickname.trim()
      if (nextNickname && nextNickname !== settings.nickname) {
        nextSettings = await updateNickname(nextNickname)
      }

      nextSettings = await updateProfile({
        profile_visibility: profileVisibility,
        display_name: displayName,
        bio,
        public_training_summary_enabled: publicSummary,
      })

      setSettings(nextSettings)
      setNickname(nextSettings.nickname)
      setProfileVisibility(nextSettings.profile_visibility)
      setDisplayName(nextSettings.display_name)
      setBio(nextSettings.bio)
      setPublicSummary(nextSettings.public_training_summary_enabled)
      pushToast({ message: 'Profile updated', type: 'success' })
    } catch {
      setError('Profile update failed.')
      pushToast({ message: 'Profile update failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  if (authLoading) {
    return <Text c="dimmed">Loading profile...</Text>
  }

  if (!user) {
    return (
      <Stack gap="lg" data-testid="profile-page">
        <Group gap="xs">
          <User size={24} />
          <Title order={2}>Profile</Title>
        </Group>
        <Paper withBorder p="lg" radius="md">
          <Stack gap="md">
            <Text c="dimmed">Sign in to manage your profile.</Text>
            <Button leftSection={<LogIn size={16} />} onClick={signIn} w="fit-content">
              Sign in with Discord
            </Button>
          </Stack>
        </Paper>
      </Stack>
    )
  }

  return (
    <Stack gap="lg" data-testid="profile-page">
      <Group justify="space-between" align="flex-start">
        <Group gap="sm">
          <Avatar src={settings?.avatar_url ?? user.avatar} alt={settings?.display_name ?? user.username} radius="xl">
            {(settings?.display_name ?? user.username)[0]?.toUpperCase()}
          </Avatar>
          <Stack gap={2}>
            <Group gap="xs">
              <Title order={2}>Profile</Title>
              {settings && <Badge variant="light">{settings.profile_visibility}</Badge>}
            </Group>
            <Text size="sm" c="dimmed">
              {settings?.discord_username ?? user.username}
            </Text>
          </Stack>
        </Group>
        <Button
          leftSection={<Save size={16} />}
          onClick={saveProfile}
          loading={saving}
          disabled={readOnly || loading || !settings}
          data-testid="profile-save"
        >
          Save Profile
        </Button>
      </Group>

      {error && (
        <Alert color="red" title="Profile unavailable" icon={<AlertCircle size={16} />}>
          {error}
        </Alert>
      )}

      <Paper withBorder p="lg" radius="md" pos="relative">
        <Stack gap="md">
          <TextInput
            label="Nickname"
            description="Lowercase letters, numbers, hyphens, and underscores."
            value={nickname}
            onChange={(event) => setNickname(event.currentTarget.value)}
            disabled={readOnly || loading || !settings}
            maxLength={32}
            data-testid="profile-nickname"
          />
          <SegmentedControl
            value={profileVisibility}
            onChange={(value) => setProfileVisibility(value as ProfileVisibility)}
            data={[
              { label: 'Private', value: 'private' },
              { label: 'Public', value: 'public' },
            ]}
            className="if-segmented"
            disabled={readOnly || loading || !settings}
          />
          <TextInput
            label="Display name"
            value={displayName}
            onChange={(event) => setDisplayName(event.currentTarget.value)}
            disabled={readOnly || loading || !settings}
            maxLength={80}
            data-testid="profile-display-name"
          />
          <Textarea
            label="Bio"
            value={bio}
            onChange={(event) => setBio(event.currentTarget.value)}
            disabled={readOnly || loading || !settings}
            maxLength={280}
            minRows={3}
            data-testid="profile-bio"
          />
          <Switch
            label="Show training summary when public"
            checked={publicSummary}
            onChange={(event) => setPublicSummary(event.currentTarget.checked)}
            disabled={readOnly || loading || !settings || profileVisibility !== 'public'}
          />
        </Stack>
      </Paper>
    </Stack>
  )
}
