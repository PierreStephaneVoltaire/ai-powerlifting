import asyncio
import importlib


def test_program_list_parses_version_prefix_from_suffixed_and_legacy_keys():
    core = importlib.import_module("services.handlers.program.program_list.core")

    assert core._version_from_item({"sk": "program#v034-861d377a"}) == 34
    assert core._version_from_item({"sk": "program#v7"}) == 7
    assert core._version_from_item({"sk": "program#v034-861d377a", "meta": {"version": 12}}) == 12
    for value in (0, "0", False):
        assert core._version_from_item({"sk": "program#v034-861d377a", "meta": {"version": value}}) == 34
    assert core._version_from_item({"sk": "program#current"}) == 0


def test_program_list_handles_normal_suffixed_record_without_metadata_version(monkeypatch):
    core = importlib.import_module("services.handlers.program.program_list.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [{"sk": "program#v034-861d377a", "meta": {"name": "Normal"}}]}

    monkeypatch.setattr(core, "_get_table", lambda: Table())
    result = asyncio.run(core.program_list({"pk": "athlete"}))

    assert result["programs"][0]["sk"] == "program#v034-861d377a"
    assert result["programs"][0]["version"] == 34
