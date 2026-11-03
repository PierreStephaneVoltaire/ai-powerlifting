import pytest

from services.dispatch import owner_aliases

from services.lib.storage_scope import current_owner_aliases
from services.lib.template_store import TemplatePermissionError, TemplateStore


INDEX = [
    {"sk": "template#legacy", "name": "legacy", "author_pk": "operator", "published": False, "archived": False},
    {"sk": "template#person", "name": "person", "author_pk": "sir_simpalot", "published": False, "archived": False},
    {"sk": "template#other", "name": "other", "author_pk": "someone-else", "published": False, "archived": False},
    {"sk": "template#public", "name": "public", "author_pk": "someone-else", "published": True, "archived": False},
]


@pytest.fixture
def store():
    instance = TemplateStore("if-health-templates")
    instance._read_index_sync = lambda: [dict(item) for item in INDEX]
    return instance


def as_person(aliases):
    return current_owner_aliases.set(frozenset(aliases))


def test_owner_aliases_come_from_verified_access():
    arguments = {"_person_pk": "sir_simpalot", "_access": {"person_pk": "sir_simpalot", "settings_pk": "sir_simpalot", "own_athlete_pk": "operator"}}
    assert owner_aliases(arguments) == {"sir_simpalot", "operator"}
    assert owner_aliases({"_access": {"own_athlete_pk": "operator"}}) == frozenset()


def test_mapped_athlete_owned_templates_belong_to_person(store):
    token = as_person({"sir_simpalot", "operator"})
    try:
        listed = {item["sk"]: item["is_owner"] for item in store.list_templates_sync(actor_pk="sir_simpalot")}
        assert listed == {"template#legacy": True, "template#person": True, "template#public": False}
        store._assert_owner({"meta": {"author_pk": "operator"}}, "sir_simpalot")
        with pytest.raises(TemplatePermissionError):
            store._assert_owner({"meta": {"author_pk": "someone-else"}}, "sir_simpalot")
    finally:
        current_owner_aliases.reset(token)


def test_aliases_only_apply_to_the_authenticated_actor(store):
    token = as_person({"sir_simpalot", "operator"})
    try:
        assert not store._owns({"author_pk": "operator"}, "someone-else")
    finally:
        current_owner_aliases.reset(token)
    assert not store._owns({"author_pk": "operator"}, "sir_simpalot")
    assert store._owns({"author_pk": "sir_simpalot"}, "sir_simpalot")
