from services.runtime.contract import load_operations
from services.runtime.dispatch import authorize, OperationError
import pytest


def test_trusted_scope_overrides_empty_pk_and_rejects_other_athlete():
    operation = load_operations("program")["program_get"]
    assert authorize(operation, {"pk": ""}, "athlete-a", "person-a")["pk"] == "athlete-a"
    with pytest.raises(OperationError):
        authorize(operation, {"pk": "athlete-b"}, "athlete-a", "person-a")


def test_template_actor_is_person_separate_from_selected_athlete():
    operation = load_operations('templates')['template_copy']
    payload = {'sk': 'template#source', 'new_name': 'Copy', 'actor_pk': 'person-a'}
    scoped = authorize(operation, payload, 'athlete-a', 'person-a')
    operation.validate_input(scoped)
    assert scoped['actor_pk'] == 'person-a' and scoped['pk'] == 'athlete-a'
    with pytest.raises(OperationError):
        authorize(operation, {**payload, 'actor_pk': 'athlete-a'}, 'athlete-a', 'person-a')
