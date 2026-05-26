#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_config(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    text = p.read_text()
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
        except ImportError:
            print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
            sys.exit(1)
    else:
        data = json.loads(text)
    channels = data.get("channels", [])
    if not isinstance(channels, list):
        print("ERROR: Config must have a top-level 'channels' list.", file=sys.stderr)
        sys.exit(1)
    return channels


def _register(
    api_url: str,
    token: str,
    channel_id: str,
    label: str,
    specialist: Optional[str] = None,
) -> Dict[str, Any]:
    import urllib.request
    url = api_url.rstrip("/") + "/v1/webhooks/register"
    discord_config: Dict[str, Any] = {"bot_token": token, "channel_id": str(channel_id)}
    if specialist:
        discord_config["pinned_specialist"] = specialist
    payload = json.dumps({
        "platform": "discord",
        "label": label,
        "discord": discord_config,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def _list_active(api_url: str) -> None:
    import urllib.request
    url = api_url.rstrip("/") + "/v1/webhooks/active"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return
    webhooks = data.get("webhooks", [])
    if not webhooks:
        print("No active webhooks.")
        return
    print(f"\n{'Label':<25} {'Conv ID':<25} {'Specialist':<25} Webhook ID")
    print("-" * 95)
    for wh in webhooks:
        label = wh.get("label", "")
        specialist = wh.get("pinned_specialist") or "- (planner)"
        webhook_id = wh.get("webhook_id", "")
        conv_id = wh.get("conversation_id", "")
        print(f"{label:<25} {conv_id:<25} {specialist:<25} {webhook_id}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register Discord channels with the IF agent API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="IF agent API base URL (default: http://localhost:8000)")
    parser.add_argument("--token", help="Discord bot token (include 'Bot ' prefix)")
    parser.add_argument("--channel-id", dest="channel_id",
                        help="Discord channel ID to register")
    parser.add_argument("--label", help="Human-readable label for this channel")
    parser.add_argument(
        "--specialist", default="",
        help="Specialist slug to lock channel to (e.g. powerlifting_coach, architect). "
             "Omit for normal planner routing.",
    )
    parser.add_argument("--config",
                        help="Path to YAML/JSON file for batch registration")
    parser.add_argument("--list", action="store_true",
                        help="List all currently active webhooks and exit")
    args = parser.parse_args()

    if args.list:
        _list_active(args.api_url)
        return 0

    if args.config:
        channels = _load_config(args.config)
    elif args.token and args.channel_id and args.label:
        channels = [{
            "token": args.token,
            "channel_id": args.channel_id,
            "label": args.label,
            "specialist": args.specialist or None,
        }]
    else:
        parser.error("Provide either --config or all of --token, --channel-id, --label")
        return 1

    failures = 0
    for ch in channels:
        token = ch.get("token", "")
        channel_id = str(ch.get("channel_id", ""))
        label = ch.get("label", channel_id)
        specialist = ch.get("specialist") or None

        if not token or not channel_id:
            print(f"SKIP [{label}] - missing token or channel_id", file=sys.stderr)
            failures += 1
            continue

        note = f" -> specialist={specialist!r}" if specialist else " -> planner routing"
        print(f"Registering [{label}] {channel_id}{note} ... ", end="", flush=True)
        try:
            r = _register(api_url=args.api_url, token=token,
                          channel_id=channel_id, label=label, specialist=specialist)
            pinned = r.get("pinned_specialist", "")
            pinned_note = f"  locked={pinned!r}" if pinned else ""
            print(f"OK  {r.get('webhook_id', '?')}  status={r.get('status', '?')}{pinned_note}")
        except Exception as e:
            print("FAILED")
            print(f"  ERROR: {e}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} channel(s) failed to register.", file=sys.stderr)
        return 1
    print(f"\nAll {len(channels)} channel(s) registered successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
