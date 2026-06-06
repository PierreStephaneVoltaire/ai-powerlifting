#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-ca-central-1}"
TABLE="${IF_CORE_TABLE_NAME:-if-core}"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

put() {
  local alpha=$1 beta=$2 label=$3 content=$4
  shift 4
  local types=("$@")
  local sk
  sk=$(printf "%02d#%02d#v001" "$alpha" "$beta")

  # Build dtype as DynamoDB StringSet JSON
  local dtype_json
  dtype_json=$(printf '%s\n' "${types[@]}" | jq -R . | jq -s '{SS: .}')

  aws dynamodb put-item \
    --region "$REGION" \
    --table-name "$TABLE" \
    --item "$(jq -n \
      --arg sk      "$sk" \
      --argjson alpha "$alpha" \
      --argjson beta  "$beta" \
      --arg label   "$label" \
      --arg content "$content" \
      --arg now     "$NOW" \
      --argjson dtype "$dtype_json" \
      '{
        pk:         {S: "operator"},
        sk:         {S: $sk},
        alpha:      {N: ($alpha|tostring)},
        beta:       {N: ($beta|tostring)},
        version:    {N: "1"},
        label:      {S: $label},
        content:    {S: $content},
        dtype:      $dtype,
        active:     {BOOL: true},
        created_by: {S: "operator"},
        created_at: {S: $now}
      }')" \
    --no-cli-pager \
    --output json > /dev/null

  echo "  PUT operator ${sk} ${label} [${types[*]}]"
}

echo "[*] Seeding code delivery directives -> ${TABLE} (${REGION})"

# ═══════════════════════════════════════════════════════════════════════════════
# TIER 1 — CRITICAL. Only bypass with explicit operator request.
# ═══════════════════════════════════════════════════════════════════════════════

C='IF delivers responses through Discord, which has a 4000-character
message limit. Code blocks longer than 10 lines are unreadable on
mobile and cause chunking problems. Follow these rules strictly:

SHORT CODE (≤10 lines): Use an inline fenced code block in your
response text. This is the only case where code appears directly
in the message.

LONG CODE (>10 lines): Write the code to a file using write_file,
then list it in a FILES: line at the very end of your response.
IF will strip the FILES: line, upload the file as a Discord
attachment, and deliver it alongside the response. Do NOT paste
long code inline — it breaks chunking and is unreadable on Discord.

USER REQUESTS FOR A FILE: When the operator asks to see, get, or
send a file, write or copy it to the session directory and list it
in a FILES: line. Do NOT read and dump the file contents into your
response. The user receives the file as a downloadable attachment.

DESCRIBE DONT DUMP: In your response text, describe what you built
or changed in one or two sentences. The attachment carries the full
content. Repeating file contents in both the response text and an
attachment is wasteful and causes chunking failures.'
put 1 24 "CODE_DELIVERY_DISCORD" "$C" code communication

echo "[✓] Code delivery directives seeded."
