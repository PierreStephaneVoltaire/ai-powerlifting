import { callOperation } from '../utils/lambda'

export async function seedMasterCopiesForNewUser(userPk: string): Promise<void> {
  await callOperation('master_copy_seed_user', { pk: userPk })
}
