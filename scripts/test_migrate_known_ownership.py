import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("ownership", Path(__file__).with_name("migrate_known_ownership.py"))
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_exact_mapping_uses_pk_and_mapped_pk_only():
    records = [
        {"pk": "sir_simpalot", "mapped_pk": "operator", "email": "operator@example.test", "display_name": "Operator"},
        {"pk": "coach-person", "mapped_pk": "coach-athlete", "email": "same@example.test", "display_name": "Operator"},
    ]
    assert MODULE.exact_person_mapping(records) == {"operator": "sir_simpalot", "coach-athlete": "coach-person"}


def test_known_update_is_additive_and_unknown_is_skipped():
    mapping = {"operator": "sir_simpalot"}
    source = {"pk": "template_library", "sk": "template#one", "meta": {"author_pk": "operator"}}
    updated, status = MODULE.template_update(source, mapping)
    assert status == "updated"
    assert updated["meta"]["author_person_pk"] == "sir_simpalot"
    assert source["meta"] == {"author_pk": "operator"}
    unknown, status = MODULE.template_update({"pk": "template_library", "sk": "template#two", "meta": {"author_pk": "someone"}}, mapping)
    assert unknown is None and status == "unknown"


def test_conflicting_existing_person_is_ambiguous():
    item = {"pk": "template_library", "sk": "template#one", "meta": {"author_pk": "operator", "author_person_pk": "another-person"}}
    assert MODULE.template_update(item, {"operator": "sir_simpalot"}) == (None, "ambiguous")


def test_ambiguous_if_user_mapping_is_not_resolved_by_display_fields():
    records = [
        {"pk": "person-a", "mapped_pk": "athlete", "email": "same@example.test", "display_name": "Same"},
        {"pk": "person-b", "mapped_pk": "athlete", "email": "same@example.test", "display_name": "Same"},
        {"pk": "person-c", "mapped_pk": "athlete", "email": "other@example.test", "display_name": "Different"},
    ]
    assert "athlete" not in MODULE.exact_person_mapping(records)


def test_mapping_file_must_match_existing_authoritative_person_mapping():
    records = [{"pk": "person", "mapped_pk": "athlete"}]
    MODULE.validate_supplied_mapping({"athlete": "person"}, records, {"athlete": "person"})
    try:
        MODULE.validate_supplied_mapping({"athlete": "other"}, records, {"athlete": "person"})
    except ValueError as error:
        assert "does not exist" in str(error)
    else:
        raise AssertionError("nonexistent mapping target was accepted")
    try:
        MODULE.validate_supplied_mapping({"different-athlete": "person"}, records, {"athlete": "person"})
    except ValueError as error:
        assert "unambiguous" in str(error)
    else:
        raise AssertionError("unverified mapping key was accepted")


def test_migrated_template_is_repeatable():
    item = {"pk": "template_library", "sk": "template#one", "meta": {"author_pk": "operator"}}
    updated, _ = MODULE.template_update(item, {"operator": "sir_simpalot"})
    assert updated is not None
    assert MODULE.template_update(updated, {"operator": "sir_simpalot"}) == (None, "unchanged")


def test_apply_updates_conditionally_updates_authoritative_owner():
    class Table:
        def __init__(self):
            self.calls = []

        def update_item(self, **kwargs):
            self.calls.append(kwargs)

    source = {"pk": "template_library", "sk": "template#one", "meta": {"author_pk": "operator", "revision": 3}}
    updated, _ = MODULE.template_update(source, {"operator": "sir_simpalot"})
    table = Table()
    assert MODULE.apply_updates(table, [updated]) == (1, 0)
    call = table.calls[0]
    assert "#meta.#author = :old_author" in call["ConditionExpression"]
    assert call["ExpressionAttributeValues"][":old_author"] == "operator"
    assert call["ExpressionAttributeValues"][":revision"] == 3
    assert "#meta.#author = :person" in call["UpdateExpression"]
