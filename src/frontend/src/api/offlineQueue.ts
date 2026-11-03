import api from './http'
import { listMutations, pendingMutationCount, synchronizePendingMutations, type PendingMutation } from './drafts'
import { requestPartition } from './context'

export { listMutations, pendingMutationCount, type PendingMutation }

export async function synchronizeOfflineQueue(): Promise<void> {
  await synchronizePendingMutations(async (record) => {
    const response = await api.request({
      method: record.method,
      url: record.url,
      data: record.data,
      powerliftingReplay: true,
      powerliftingPartition: record.partition,
    })
    return { status: response.status, data: response.data }
  }, requestPartition())
}
