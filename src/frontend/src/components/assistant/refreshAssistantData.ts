import { clearContextCache } from '@/api/cache'
import { requestPartition } from '@/api/context'
import { fetchProgram } from '@/api/client'
import { useProgramStore } from '@/store/programStore'

export async function refreshAssistantData(): Promise<void> {
  const partition = requestPartition()
  await clearContextCache(partition)
  if (partition !== requestPartition()) return
  const { program, isDirty } = useProgramStore.getState()
  if (program) {
    if (isDirty) throw new Error('Save or discard your local program edits before refreshing.')
    const refreshed = await fetchProgram()
    if (partition !== requestPartition()) return
    const current = useProgramStore.getState()
    if (current.program === program) {
      useProgramStore.setState({ program: refreshed, error: null })
    }
  }
}
