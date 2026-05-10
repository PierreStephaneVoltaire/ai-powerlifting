import { useState, useEffect } from 'react'
import { Menu, Button, Group, Badge } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { Copy, Settings, ChevronDown, Check, Archive, BookOpen, RotateCcw } from 'lucide-react'
import * as api from '@/api/client'

export default function TopBar() {
  const { program, version, versions, isLoading, forkVersion, loadVersions, loadProgram, archiveProgram, unarchiveProgram } = useProgramStore()
  const { unit, toggleUnit } = useSettingsStore()
  const { openDrawer, pushToast } = useUiStore()
  const [forking, setForking] = useState(false)
  const [archiving, setArchiving] = useState(false)

  useEffect(() => {
    loadVersions()
  }, [loadVersions])

  const handleFork = async () => {
    if (forking) return
    setForking(true)
    try {
      await forkVersion()
      pushToast({ message: 'Version forked', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Fork failed', type: 'error' })
    } finally {
      setForking(false)
    }
  }

  const handleArchiveToggle = async () => {
    setArchiving(true)
    try {
      if (program?.meta?.archived) {
        await unarchiveProgram()
        pushToast({ message: 'Version unarchived', type: 'success' })
      } else {
        await archiveProgram()
        pushToast({ message: 'Version archived', type: 'success' })
      }
    } catch (err) {
      pushToast({ message: 'Action failed', type: 'error' })
    } finally {
      setArchiving(false)
    }
  }

  const handleConvertToTemplate = async () => {
    const name = prompt('Enter template name:', program?.meta?.version_label || 'New Template')
    if (!name) return
    try {
      await api.createTemplateFromBlock(name, program?.sk)
      pushToast({ message: 'Template created', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to create template', type: 'error' })
    }
  }

  const handleSelectVersion = async (newVersion: string) => {
    if (newVersion === version) return
    await loadProgram(newVersion)
  }

  const visibleVersions = versions.filter(v => !v.archived || v.version === version)

  return (
    <Group justify="space-between" h="100%" px="md">
      {/* Left: Version selector */}
      <Menu shadow="md" width={240} position="bottom-start">
        <Menu.Target>
          <Button
            variant="subtle"
            rightSection={<ChevronDown size={16} />}
            loading={isLoading}
            color={program?.meta?.archived ? 'gray' : 'blue'}
          >
            {program?.meta?.version_label || version}
            {program?.meta?.archived && <Badge ml="xs" size="xs" color="gray">Archived</Badge>}
          </Button>
        </Menu.Target>

        <Menu.Dropdown>
          {visibleVersions.map((v) => (
            <Menu.Item
              key={v.version}
              onClick={() => handleSelectVersion(v.version)}
              fw={v.version === 'current' ? 600 : 400}
              rightSection={
                v.version === version ? <Check size={16} /> : null
              }
            >
              {v.version_label || v.version}
            </Menu.Item>
          ))}

          {visibleVersions.length === 0 && (
            <Menu.Item disabled>No versions found</Menu.Item>
          )}

          <Menu.Divider />

          <Menu.Item
            onClick={handleFork}
            disabled={forking}
            leftSection={<Copy size={16} />}
          >
            {forking ? 'Forking...' : 'Fork this version'}
          </Menu.Item>

          <Menu.Item
            onClick={handleArchiveToggle}
            disabled={archiving}
            leftSection={program?.meta?.archived ? <RotateCcw size={16} /> : <Archive size={16} />}
            color={program?.meta?.archived ? 'blue' : 'red'}
          >
            {program?.meta?.archived ? 'Unarchive version' : 'Archive version'}
          </Menu.Item>

          <Menu.Item
            onClick={handleConvertToTemplate}
            leftSection={<BookOpen size={16} />}
          >
            Convert to Template
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      {/* Right: Unit toggle + Settings */}
      <Group gap="xs">
        <Button variant="subtle" size="sm" onClick={toggleUnit}>
          {unit.toUpperCase()}
        </Button>

        <Button
          variant="subtle"
          size="sm"
          onClick={() => openDrawer('settings')}
        >
          <Settings size={20} />
        </Button>
      </Group>
    </Group>
  )
}
