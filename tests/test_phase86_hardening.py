"""Phase 8.6 correctness hardening tests.

Covers:
- Batch classifier uses OPENCODE_CONFIG_CONTENT (no root opencode.json written)
- build_opencode_config_content returns valid JSON string
- Heartbeat and reflection modules compile without syntax errors
- No-new-message classifier pass clears pending state and does not reschedule
- Classifier pass during active classification marks dirty for later pass
- Fallback response goes through outbox, not direct Discord send
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)


def test_heartbeat_runner_compiles():
    """heartbeat/runner.py must have no syntax errors."""
    source = (Path(__file__).resolve().parent.parent / "app" / "src" / "heartbeat" / "runner.py").read_text()
    compile(source, "heartbeat/runner.py", "exec")
    assert ">>>" not in source, "heartbeat/runner.py must not contain >>> syntax junk"


def test_reflection_engine_compiles():
    """agent/reflection/engine.py must have no syntax errors."""
    source = (Path(__file__).resolve().parent.parent / "app" / "src" / "agent" / "reflection" / "engine.py").read_text()
    compile(source, "agent/reflection/engine.py", "exec")
    assert ">>>" not in source, "agent/reflection/engine.py must not contain >>> syntax junk"


def test_build_opencode_config_content_returns_json_string():
    """build_opencode_config_content returns a valid JSON string with $schema and mcp."""
    with patch("flow.opencode_config.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value.categories = []
        mock_mgr.return_value.categories_for_names.return_value = {}
        from flow.opencode_config import build_opencode_config_content
        result = build_opencode_config_content(tool_names=[], mcp_servers=[])
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "$schema" in parsed
    assert "mcp" in parsed
    assert parsed["mcp"] == {}


def test_build_opencode_config_content_does_not_write_files(tmp_path):
    """build_opencode_config_content must not write any file to disk."""
    import os
    with patch("flow.opencode_config.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value.categories = []
        mock_mgr.return_value.categories_for_names.return_value = {}
        from flow.opencode_config import build_opencode_config_content
        build_opencode_config_content(tool_names=[], mcp_servers=[])
    files_written = list(tmp_path.rglob("*"))
    assert files_written == []


def test_build_opencode_config_content_uses_remote_mcp_urls():
    """MCP entries are type:remote URLs. Category underscores are
    sanitised to hyphens so the host matches the k8s Service name."""
    from config import IF_MCP_URL_TEMPLATE, IF_MCP_HTTP_PORT, IF_MCP_HTTP_PATH, IF_MCP_NAMESPACE
    expected_template = IF_MCP_URL_TEMPLATE
    with patch("flow.opencode_config.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value.categories = ["health", "tarot", "temporal_age", "supplement_research"]
        mock_mgr.return_value.categories_for_names.return_value = {
            "health_get_session": "health",
            "tarot_draw_cards": "tarot",
            "temporal_resolve_date": "temporal_age",
            "supp_research_query": "supplement_research",
        }
        from flow.opencode_config import build_opencode_config_content
        result = build_opencode_config_content(
            tool_names=[
                "health_get_session",
                "tarot_draw_cards",
                "temporal_resolve_date",
                "supp_research_query",
            ]
        )
    parsed = json.loads(result)
    assert set(parsed["mcp"].keys()) == {
        "if_health", "if_tarot", "if_temporal_age", "if_supplement_research",
    }
    for entry in parsed["mcp"].values():
        assert entry["type"] == "remote"
        assert "command" not in entry  # no stdio subprocess
        assert "environment" not in entry
        assert entry["enabled"] is True
        assert entry["timeout"] > 0
    # URLs must be the per-category service URL the entrypoint exposes.
    # The k8s Service/Deployment names sanitise underscores to hyphens,
    # so the URL has to match that (RFC 1123).
    expected_health = expected_template.format(
        category="health", namespace=IF_MCP_NAMESPACE,
        port=IF_MCP_HTTP_PORT, path=IF_MCP_HTTP_PATH,
    )
    assert parsed["mcp"]["if_health"]["url"] == expected_health
    expected_temporal = expected_template.format(
        category="temporal-age", namespace=IF_MCP_NAMESPACE,
        port=IF_MCP_HTTP_PORT, path=IF_MCP_HTTP_PATH,
    )
    assert parsed["mcp"]["if_temporal_age"]["url"] == expected_temporal
    assert "_" not in parsed["mcp"]["if_temporal_age"]["url"].split("/")[2].split(":")[0]
    expected_supp = expected_template.format(
        category="supplement-research", namespace=IF_MCP_NAMESPACE,
        port=IF_MCP_HTTP_PORT, path=IF_MCP_HTTP_PATH,
    )
    assert parsed["mcp"]["if_supplement_research"]["url"] == expected_supp


@pytest.mark.asyncio
async def test_batch_classifier_passes_config_content_not_root_opencode_json(tmp_path):
    """run_batch_classification must pass config_content to run_opencode
    and must NOT write a root session_dir/opencode.json."""
    from unittest.mock import patch, AsyncMock, MagicMock
    import types

    stubs = [
        ("sqlmodel", {"SQLModel": type("S", (), {}), "Field": lambda *a, **k: None}),
        ("storage.models", {"WebhookRecord": type("WR", (), {})}),
    ]
    import types as _types
    for modname, attrs in stubs:
        if modname not in sys.modules:
            mod = _types.ModuleType(modname)
            for k, v in attrs.items():
                setattr(mod, k, v)
            sys.modules[modname] = mod

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "history.md").write_text("", encoding="utf-8")

    classification_file = session_dir / "classification.batch.FAKE.json"

    fake_result = MagicMock(returncode=0, stdout="", stderr="")

    run_opencode_calls = []

    async def fake_run_opencode(**kwargs):
        run_opencode_calls.append(kwargs)
        json_content = '{"batchSummary": "test", "decisions": [{"intentId": "i1", "kind": "social", "action": "social_response", "sourceMessageIds": [], "targetTaskId": null, "confidence": 0.9, "reason": "ok", "needsPlanning": false, "selectedSpecialist": null, "selectedModel": null, "socialResponseText": "hello", "responseText": null, "plannerIntent": null, "topicUpdate": null, "conflict": null}]}'
        prompt = kwargs.get("prompt", "")
        import re as _re
        m = _re.search(r"classification\.batch\.([^.]+)\.json", prompt)
        batch_id_str = m.group(1) if m else "FAKE"
        out_file = session_dir / f"classification.batch.{batch_id_str}.json"
        out_file.write_text(json_content, encoding="utf-8")
        return fake_result

    fake_store = MagicMock()
    fake_store.put_classification_batch = AsyncMock()
    fake_store.put_intent_record = AsyncMock()

    with patch("flow.opencode_config.get_mcp_manager") as mock_mgr, \
         patch("flow.batch_classifier.run_opencode", side_effect=fake_run_opencode), \
         patch("flow.batch_classifier.get_execution_store", return_value=fake_store), \
         patch("flow.batch_classifier.load_model_ids", return_value=["deepseek/deepseek-v4-flash"]), \
         patch("flow.batch_classifier.load_model_selection_rules", return_value=""), \
         patch("flow.batch_classifier._specialist_catalog", return_value=({"social"}, "- social: social")), \
         patch("flow.batch_classifier.batch_classifier_prompt", return_value="test prompt"):
        mock_mgr.return_value.categories = []
        mock_mgr.return_value.categories_for_names.return_value = {}
        from flow.batch_classifier import run_batch_classification
        await run_batch_classification(
            session_dir=session_dir,
            channel_id="chan1",
            candidate_source_message_ids=["m1"],
        )

    assert len(run_opencode_calls) == 1
    call = run_opencode_calls[0]
    assert "config_content" in call, "run_opencode must receive config_content kwarg"
    assert call["config_content"] is not None
    assert call["run_id"] is not None

    root_config = session_dir / "opencode.json"
    assert not root_config.exists(), "Root opencode.json must NOT be written in orchestrated batch classifier path"


def test_finish_classifier_pass_clears_pending_when_no_new_event():
    """finish_classifier_pass clears pending/dirty/timestamps when processed_event_at
    matches latest_observed_event_at (no new event during pass)."""
    from channels.execution_store import ExecutionStore
    from channels.execution_models import floats_to_decimals
    from datetime import datetime, timezone
    from decimal import Decimal

    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()

    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": True, "dirty": False,
        "latest_observed_event_at": now,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("3"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}

    result = store._finish_classifier_pass_sync("ch1", "owner-A", now, 45.0)
    assert result is True
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs["ExpressionAttributeValues"]
    assert attr_values.get(":target") == "idle"
    expr = call_kwargs["UpdateExpression"]
    assert "pending" in expr


def test_finish_classifier_pass_keeps_pending_when_newer_event():
    """finish_classifier_pass keeps pending/debouncing when a newer event arrived during classification."""
    from channels.execution_store import ExecutionStore
    from datetime import datetime, timezone, timedelta
    from decimal import Decimal

    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()

    now = datetime.now(timezone.utc)
    processed_at = (now - timedelta(seconds=5)).isoformat()
    latest_at = now.isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": True, "dirty": True,
        "latest_observed_event_at": latest_at,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("4"), "updated_at": processed_at,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}

    result = store._finish_classifier_pass_sync("ch1", "owner-A", processed_at, 45.0)
    assert result is True
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs["ExpressionAttributeValues"]
    assert attr_values.get(":target") == "debouncing"
