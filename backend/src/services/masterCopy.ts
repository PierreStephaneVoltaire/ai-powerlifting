import { invokeLambda } from '../utils/lambda'

export async function seedMasterCopiesForNewUser(userPk: string): Promise<void> {
  await invokeLambda('master_copy_seed_user', { pk: userPk })
}
