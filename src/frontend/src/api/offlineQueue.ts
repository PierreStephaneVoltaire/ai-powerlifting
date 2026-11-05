import api from './http'
import { synchronizePendingMutations } from './drafts'
import { requestPartition } from './context'

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
