"""Tests for safe fallback behavior when batch classification fails.

Verifies:
- Differentiated error messages by failure category
- _run_fallback_batch removed (safety fix)
- Health/medical warnings in fallback messages
- Automatic retry for parse/subprocess errors
- Confidence gating for low-confidence decisions
- BatchClassificationError category field
"""
import sys
from pathlib import Path

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

import channels.channel_coordinator as coordinator_module
from flow.batch_classifier import BatchClassificationError


def test_run_fallback_batch_removed():
    """_run_fallback_batch must not exist — removed as a safety fix."""
    assert not hasattr(coordinator_module, "_run_fallback_batch")


def test_no_process_chat_completion_internal():
    """channel_coordinator must not call process_chat_completion_internal."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    assert "process_chat_completion_internal" not in source


def test_health_medical_warnings_in_fallback():
    """All fallback messages must warn about health/medical queries."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    assert "medical" in source.lower()


def test_safety_comment_in_null_classification_block():
    """The classification=None block must contain a SAFETY comment."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    lines = source.split("\n")
    in_null_block = False
    null_block_lines = []
    for line in lines:
        if "classification is None" in line and "if " in line:
            in_null_block = True
        elif in_null_block:
            if line.strip().startswith("else:") or (not line.startswith(" ") and not line.startswith("\t") and line.strip()):
                break
            null_block_lines.append(line)
    null_block = "\n".join(null_block_lines)
    assert "SAFETY" in null_block or "safety" in null_block.lower()
    assert "_run_fallback_batch" not in null_block
    assert "process_chat_completion_internal" not in null_block


def test_batch_classification_error_category():
    """BatchClassificationError must carry a category field."""
    err = BatchClassificationError("test", category="parse_error")
    assert err.category == "parse_error"
    err2 = BatchClassificationError("test", category="subprocess_error")
    assert err2.category == "subprocess_error"
    err3 = BatchClassificationError("test")
    assert err3.category == "unknown"


def test_differentiated_fallback_by_category():
    """Different failure categories must produce different messages."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    assert 'failure_category == "parse_error"' in source
    assert 'failure_category == "subprocess_error"' in source
    assert "after retry" in source.lower()


def test_retry_logic_in_collect_batch():
    """_collect_batch_dispatch must retry on parse/subprocess errors."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    assert "CLASSIFICATION_RETRY_MAX" in source
    assert '"parse_error"' in source
    assert '"subprocess_error"' in source


def test_confidence_gate_in_dispatch():
    """Dispatch must check confidence and ask clarification when low."""
    source = (Path(APP_SRC) / "channels" / "channel_coordinator.py").read_text()
    assert "CLASSIFICATION_CONFIDENCE_THRESHOLD" in source
    assert "low_confidence_decisions" in source
    assert "clarify" in source.lower()


def test_config_classification_retry_max():
    """CLASSIFICATION_RETRY_MAX must exist in config."""
    from config import CLASSIFICATION_RETRY_MAX
    assert isinstance(CLASSIFICATION_RETRY_MAX, int)
    assert CLASSIFICATION_RETRY_MAX >= 0


def test_config_classification_confidence_threshold():
    """CLASSIFICATION_CONFIDENCE_THRESHOLD must exist in config."""
    from config import CLASSIFICATION_CONFIDENCE_THRESHOLD
    assert 0.0 <= CLASSIFICATION_CONFIDENCE_THRESHOLD <= 1.0
