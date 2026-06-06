#!/usr/bin/env python3
"""
Read all directives from the if-core DynamoDB table and generate a standalone
bash seed script that recreates them exactly.
Usage:
    python3 scripts/generate_seed_directives.py > scripts/seed_directives_generated.sh
    bash scripts/seed_directives_generated.sh
Environment variables (all optional -- defaults match the live deployment):
    AWS_REGION           AWS region           (default: ca-central-1)
    IF_CORE_TABLE_NAME   DynamoDB table name  (default: if-core)
    IF_USER_PK           Source/target PK     (default: operator)
"""
import boto3
import os
import sys
from collections import defaultdict
REGION = os.getenv("AWS_REGION", "ca-central-1")
TABLE  = os.getenv("IF_CORE_TABLE_NAME", "if-core")
PK     = os.getenv("IF_USER_PK", "operator")
TIER_LABELS = {
    0: "Core Identity",
    1: "Behavioral Rules",
    2: "Style & Tone",
    3: "Domain Knowledge",
    4: "Situational",
    5: "Temporary",
}
def fetch_all_items():
    client = boto3.client("dynamodb", region_name=REGION)
    items = []
    kwargs = {
        "TableName": TABLE,
        "FilterExpression": "pk = :pk",
        "ExpressionAttributeValues": {":pk": {"S": PK}},
    }
    while True:
        resp = client.scan(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items
def dval(attr):
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        n = attr["N"]
        return int(n) if "." not in n else float(n)
    if "BOOL" in attr:
        return attr["BOOL"]
    if "SS" in attr:
        return sorted(attr["SS"])
    return None
def single_quote(s):
    return s.replace("'", "'\"'\"'")

def generate_put_calls(item):
    alpha      = dval(item["alpha"])
    beta       = dval(item["beta"])
    label      = dval(item["label"])
    content    = dval(item["content"])
    active     = dval(item.get("active", {"BOOL": True}))
    dtype_list = dval(item["dtype"])
    superseded = dval(item["superseded_at"]) if "superseded_at" in item else None
    dtype_args = " ".join(dtype_list)
    lines = []
    lines.append("C='{}'".format(single_quote(content)))
    lines.append('put {} {} "{}" "$C" {}'.format(alpha, beta, label, dtype_args))
    if active is False:
        lines.append("mark_inactive {} {}".format(alpha, beta))
    if superseded:
        lines.append("mark_superseded {} {} '{}'".format(alpha, beta, superseded))
    lines.append("")
    return lines
def bash_header(count):
    L = []
    L.append("#!/usr/bin/env bash")
    L.append("# Auto-generated directive seed script.")
    L.append("# Source: table={}  region={}  pk={}  items={}".format(TABLE, REGION, PK, count))
    L.append("# Regenerate: python3 scripts/generate_seed_directives.py > scripts/seed_directives_generated.sh")
    L.append("")
    L.append("set -euo pipefail")
    L.append("")
    L.append('REGION="${AWS_REGION:-' + REGION + '}"')
    L.append('TABLE="${IF_CORE_TABLE_NAME:-' + TABLE + '}"')
    L.append('NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")')
    L.append("")
    L.append("# ---------------------------------------------------------------------------")
    L.append("# put ALPHA BETA LABEL CONTENT DTYPE...")
    L.append("#   Writes one directive. DTYPE = one or more space-separated type tokens.")
    L.append("# ---------------------------------------------------------------------------")
    L.append("put() {")
    L.append("  local alpha=$1 beta=$2 label=$3 content=$4")
    L.append("  shift 4")
    L.append('  local types=("$@")')
    L.append("  local sk")
    L.append('  sk=$(printf "%02d#%02d#v001" "$alpha" "$beta")')
    L.append("")
    L.append("  local dtype_json")
    L.append("  dtype_json=$(printf '%s\\n' \"${types[@]}\" | jq -R . | jq -s '{SS: .}')")
    L.append("")
    L.append("  aws dynamodb put-item \\")
    L.append('    --region "$REGION" \\')
    L.append('    --table-name "$TABLE" \\')
    L.append('    --item "$(jq -n \\')
    L.append('      --arg sk      "$sk" \\')
    L.append('      --argjson alpha "$alpha" \\')
    L.append('      --argjson beta  "$beta" \\')
    L.append('      --arg label   "$label" \\')
    L.append('      --arg content "$content" \\')
    L.append('      --arg now     "$NOW" \\')
    L.append('      --argjson dtype "$dtype_json" \\')
    L.append("      '{")
    L.append('        pk:         {S: "operator"},')
    L.append("        sk:         {S: $sk},")
    L.append("        alpha:      {N: ($alpha|tostring)},")
    L.append("        beta:       {N: ($beta|tostring)},")
    L.append('        version:    {N: "1"},')
    L.append("        label:      {S: $label},")
    L.append("        content:    {S: $content},")
    L.append("        dtype:      $dtype,")
    L.append("        active:     {BOOL: true},")
    L.append('        created_by: {S: "operator"},')
    L.append("        created_at: {S: $now}")
    L.append("      }')\" \\")
    L.append("    --no-cli-pager \\")
    L.append("    --output json > /dev/null")
    L.append("")
    L.append('  echo "  PUT operator ${sk} ${label} [${types[*]}]"')
    L.append("}")
    L.append("")
    L.append("# ---------------------------------------------------------------------------")
    L.append("# mark_inactive ALPHA BETA  --  sets active=false after the put")
    L.append("# ---------------------------------------------------------------------------")
    L.append("mark_inactive() {")
    L.append("  local alpha=$1 beta=$2")
    L.append("  local sk")
    L.append('  sk=$(printf "%02d#%02d#v001" "$alpha" "$beta")')
    L.append("  aws dynamodb update-item \\")
    L.append('    --region "$REGION" \\')
    L.append('    --table-name "$TABLE" \\')
    L.append("    --key '{\"pk\":{\"S\":\"operator\"},\"sk\":{\"S\":\"'$sk'\"}}' \\")
    L.append("    --update-expression 'SET active = :v' \\")
    L.append("    --expression-attribute-values '{\":v\":{\"BOOL\":false}}' \\")
    L.append("    --no-cli-pager --output json > /dev/null")
    L.append('  echo "  INACTIVE operator ${sk}"')
    L.append("}")
    L.append("")
    L.append("# ---------------------------------------------------------------------------")
    L.append("# mark_superseded ALPHA BETA TIMESTAMP")
    L.append("# ---------------------------------------------------------------------------")
    L.append("mark_superseded() {")
    L.append("  local alpha=$1 beta=$2 ts=$3")
    L.append("  local sk")
    L.append('  sk=$(printf "%02d#%02d#v001" "$alpha" "$beta")')
    L.append("  aws dynamodb update-item \\")
    L.append('    --region "$REGION" \\')
    L.append('    --table-name "$TABLE" \\')
    L.append("    --key '{\"pk\":{\"S\":\"operator\"},\"sk\":{\"S\":\"'$sk'\"}}' \\")
    L.append("    --update-expression 'SET superseded_at = :v' \\")
    L.append('    --expression-attribute-values "{\":v\":{\"S\":\"$ts\"}}" \\')
    L.append("    --no-cli-pager --output json > /dev/null")
    L.append('  echo "  SUPERSEDED operator ${sk} @ ${ts}"')
    L.append("}")
    L.append("")
    L.append('echo "[*] Seeding directives -> $TABLE ($REGION)"')
    L.append("")
    return "\n".join(L)
def build_script(items):
    count = len(items)
    parts = [bash_header(count)]
    by_tier = defaultdict(list)
    for item in items:
              by_tier[dval(item["alpha"])].append(item)
    sep = "=" * 79
    for tier in sorted(by_tier):
        tier_items = sorted(by_tier[tier], key=lambda x: dval(x["beta"]))
        label = TIER_LABELS.get(tier, "Tier {}".format(tier))
        parts.append("# " + sep)
        parts.append("# TIER {} -- {}".format(tier, label.upper()))
        parts.append("# " + sep)
        parts.append("")
        for item in tier_items:
            for call_line in generate_put_calls(item):
                parts.append(call_line)
        parts.append("")
    parts.append('echo "[*] Done -- {} directives written."'.format(count))
    parts.append("")
    return "\n".join(parts)

def main():
    print("Fetching: table={} region={} pk={}".format(TABLE, REGION, PK), file=sys.stderr)
    try:
        items = fetch_all_items()
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)

    print("Fetched {} items.".format(len(items)), file=sys.stderr)
    if not items:
        print("ERROR: 0 items. Check TABLE / REGION / PK.", file=sys.stderr)
        sys.exit(1)

    by_tier = defaultdict(int)
    for item in items:
        by_tier[dval(item["alpha"])] += 1
    for tier in sorted(by_tier):
        print("  Tier {} ({}): {}".format(tier, TIER_LABELS.get(tier, "?"), by_tier[tier]), file=sys.stderr)

    script = build_script(items)
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "seed_directives_generated.sh")
    with open(out_path, "w") as f:
        f.write(script)
    print("Written to {}".format(out_path), file=sys.stderr)


if __name__ == "__main__":
    main()
