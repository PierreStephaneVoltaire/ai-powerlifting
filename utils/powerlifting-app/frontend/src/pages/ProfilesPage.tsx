import { useEffect, useState } from 'react'
import { Avatar, Badge, Button, Group, Paper, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { Search, Users } from 'lucide-react'
import { searchProfiles, type PublicProfile } from '@/api/profiles'
import { useUiStore } from '@/store/uiStore'

export default function ProfilesPage() {
  const { pushToast } = useUiStore()
  const [query, setQuery] = useState('')
  const [profiles, setProfiles] = useState<PublicProfile[]>([])
  const [loading, setLoading] = useState(false)

  const runSearch = async (nextQuery = query) => {
    setLoading(true)
    try {
      setProfiles(await searchProfiles(nextQuery))
    } catch {
      pushToast({ message: 'Profile search failed', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    runSearch('')
    // Run once on mount. Manual searches use the current input value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end">
        <Stack gap={4}>
          <Group gap="xs">
            <Users size={24} />
            <Title order={2}>Profiles</Title>
          </Group>
          <Text c="dimmed" size="sm">
            Search public lifter profiles. Private profiles are hidden unless they are yours.
          </Text>
        </Stack>
      </Group>

      <Group align="flex-end">
        <TextInput
          label="Search"
          placeholder="Nickname, display name, or bio"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') runSearch()
          }}
          style={{ flex: 1 }}
        />
        <Button leftSection={<Search size={16} />} loading={loading} onClick={() => runSearch()}>
          Search
        </Button>
      </Group>

      {profiles.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {profiles.map((profile) => (
            <Paper key={profile.nickname} p="md" radius="md" withBorder>
              <Stack gap="sm">
                <Group gap="sm" align="center">
                  <Avatar src={profile.avatar_url} alt={profile.display_name} radius="xl">
                    {profile.display_name[0]?.toUpperCase()}
                  </Avatar>
                  <Stack gap={0}>
                    <Group gap="xs">
                      <Text fw={600}>{profile.display_name}</Text>
                      {profile.is_self && <Badge size="xs">You</Badge>}
                    </Group>
                    <Text size="xs" c="dimmed">@{profile.nickname}</Text>
                  </Stack>
                </Group>
                {profile.bio ? (
                  <Text size="sm">{profile.bio}</Text>
                ) : (
                  <Text size="sm" c="dimmed">No bio yet.</Text>
                )}
                {profile.public_training_summary_enabled && (
                  <Badge variant="light" color="blue" w="fit-content">
                    Training summary public
                  </Badge>
                )}
              </Stack>
            </Paper>
          ))}
        </SimpleGrid>
      ) : (
        !loading && (
          <Paper p="xl" radius="md" withBorder>
            <Text c="dimmed" ta="center">No public profiles found.</Text>
          </Paper>
        )
      )}
    </Stack>
  )
}
