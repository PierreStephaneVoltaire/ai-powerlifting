import { ScanCommand, BatchWriteCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_MASTER_COMPETITIONS_TABLE, POWERLIFTING_USER_COMPETITIONS_TABLE } from '../db/dynamo'

export async function seedMasterCopiesForNewUser(userPk: string): Promise<void> {
  try {
    await seedCompetitionCopies(userPk)
  } catch (err) {
    console.error('[masterCopy] Failed to seed competition copies for', userPk, err)
  }
}

async function seedCompetitionCopies(userPk: string): Promise<void> {
  // Paginated scan of master competitions
  const masters: Record<string, unknown>[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new ScanCommand({
      TableName: POWERLIFTING_MASTER_COMPETITIONS_TABLE,
      ExclusiveStartKey: lastKey,
    }))
    for (const item of resp.Items ?? []) masters.push(item)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)

  // Batch write user copies (25 at a time)
  const now = new Date().toISOString()
  const batches: Record<string, unknown>[][] = []
  for (let i = 0; i < masters.length; i += 25) {
    batches.push(masters.slice(i, i + 25))
  }

  for (const batch of batches) {
    const writeRequests = batch.map((master) => {
      const masterId = String(master.pk?.toString()?.replace('COMP#', '') || '')
      const userCopy: Record<string, unknown> = {
        pk: userPk,
        sk: `COMP#${masterId}`,
        master_id: masterId,
        // Master-controlled fields (copied from master)
        name: master.name ?? '',
        start_date: master.start_date ?? '',
        end_date: master.end_date ?? null,
        federation_label: master.federation_label ?? '',
        federation_slug: master.federation_slug ?? null,
        federation_website_url: master.federation_website_url ?? null,
        venue_name: master.venue_name ?? null,
        venue_address: master.venue_address ?? null,
        venue_city: master.venue_city ?? null,
        venue_state: master.venue_state ?? null,
        venue_country: master.venue_country ?? null,
        venue_postal_code: master.venue_postal_code ?? null,
        website_url: master.website_url ?? null,
        testing_status: master.testing_status ?? 'unknown',
        registration_status: master.registration_status ?? 'unknown',
        registration_url: master.registration_url ?? null,
        registration_end_date: master.registration_end_date ?? null,
        source_url: master.source_url ?? null,
        source_name: master.source_name ?? null,
        event_type: master.event_type ?? null,
        last_verified_at: master.last_verified_at ?? null,
        cancelled: master.cancelled ?? false,
        // User-owned fields (defaults)
        user_status: 'available',
        weight_class_kg: null,
        body_weight_kg: null,
        targets: null,
        results: null,
        post_meet_report: null,
        hotel_required: false,
        counts_toward_federation_ids: [],
        between_comp_plan: null,
        comp_day_protocol: null,
        decision_date: null,
        attempt_selection: null,
        attempt_strategy_mode: null,
        qualifying_standard_id: null,
        qualifying_total_kg: null,
        projected_at_t_minus_1w: null,
        projection_snapshot_date: null,
        notes: '',
        created_at: now,
        updated_at: now,
      }
      return { PutRequest: { Item: userCopy } }
    })

    await docClient.send(new BatchWriteCommand({
      RequestItems: { [POWERLIFTING_USER_COMPETITIONS_TABLE]: writeRequests },
    }))
  }
}

