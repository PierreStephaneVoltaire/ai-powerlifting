
- `src/services/export/tests/test_exports.py::test_export_defaults_to_active_block_only` fails: an unstamped current supplement is scoped to the completed block, so the active-block export omits it. Observed while testing the performance service rewrite.
