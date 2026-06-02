"""Seed the if-models DynamoDB table from the OpenRouter API.

Usage:
    python scripts/seed_models.py [--models-file models/model_ids.txt]
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3

def main():
    models_file = sys.argv[1] if len(sys.argv) > 1 else "models/model_ids.txt"
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    table_name = os.environ.get("IF_MODELS_TABLE_NAME", "if-models")
    region = os.environ.get("AWS_REGION", "ca-central-1")

    if not api_key:
        sys.exit("OPENROUTER_API_KEY env var required")

    models_path = Path(models_file)
    if not models_path.exists():
        sys.exit(f"File not found: {models_path}")

    wanted = {
        line.strip()
        for line in models_path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req) as resp:
        all_models = json.loads(resp.read()).get("data", [])

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for m in all_models:
        mid = m.get("id", "")
        if mid not in wanted:
            continue

        pricing = m.get("pricing", {})
        params = m.get("supported_parameters", [])
        arch = m.get("architecture", {})
        top_provider = m.get("top_provider", {})

        if isinstance(pricing, str):
            in_price = out_price = pricing
        elif isinstance(pricing, dict):
            in_price = str(pricing.get("prompt", "0"))
            out_price = str(pricing.get("completion", "0"))
        else:
            in_price = out_price = "0"

        if "tools" not in params and "tool_choice" not in params:
            print(f"  SKIP {mid}: no tool support")
            wanted.discard(mid)
            continue

        modality = arch.get("modality", "")
        modalities = [mm.strip() for mm in modality.split("+") if mm.strip()] if modality else ["text"]

        context_length = m.get("context_length", 4096)

        best_latency = None
        best_throughput = None
        max_out = None
        try:
            ep_req = urllib.request.Request(
                f"https://openrouter.ai/api/v1/models/{mid}/endpoints",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(ep_req) as ep_resp:
                endpoints = json.loads(ep_resp.read()).get("data", {}).get("endpoints", [])
            latencies = []
            throughputs = []
            ep_max_outs = []
            for ep in endpoints:
                lat = ep.get("latency_last_30m", {})
                thr = ep.get("throughput_last_30m", {})
                if isinstance(lat, dict) and lat.get("p50"):
                    latencies.append(lat["p50"])
                if isinstance(thr, dict) and thr.get("p50"):
                    throughputs.append(thr["p50"])
                ep_max = ep.get("max_completion_tokens") or 0
                if ep_max > 0:
                    ep_max_outs.append(ep_max)
            if latencies:
                best_latency = min(latencies)
            if throughputs:
                best_throughput = max(throughputs)
            if ep_max_outs:
                max_out = min(ep_max_outs)
        except Exception:
            pass

        if not max_out:
            max_out = 4096

        table.put_item(Item={
            "pk": "MODEL",
            "sk": mid,
            "model_id": mid,
            "context_size": context_length,
            "max_output_tokens": max_out,
            "input_pricing": [{"provider": "openrouter", "price": in_price}],
            "output_pricing": [{"provider": "openrouter", "price": out_price}],
            "input_modalities": modalities,
            "output_modalities": list(modalities),
            "tool_support": "tools" in params or "tool_choice" in params,
            "caching_support": "prompt_caching" in params or "caching" in params,
            "zero_data_retention": m.get("data_controls", []) == [],
            "throughput": Decimal(str(best_throughput)) if best_throughput is not None else None,
            "latency": Decimal(str(best_latency)) if best_latency is not None else None,
            "updated_at": now,
        })
        lat_str = f"{best_latency}ms" if best_latency is not None else "N/A"
        thr_str = f"{best_throughput} tok/s" if best_throughput is not None else "N/A"
        print(f"  {mid}: latency={lat_str}, throughput={thr_str}")
        count += 1
        wanted.discard(mid)

    if wanted:
        print(f"WARNING: not found on OpenRouter: {wanted}")

    print(f"Done: {count} models upserted to {table_name}")

if __name__ == "__main__":
    main()
