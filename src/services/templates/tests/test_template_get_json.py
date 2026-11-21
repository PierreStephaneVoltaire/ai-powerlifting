import json
from decimal import Decimal


def test_template_get_serializes_dynamodb_numbers(monkeypatch):
    from services.templates.template_get import handler as module

    async def get(sk, actor):
        assert (sk, actor) == ("template#1", "person")
        return {
            "meta": {"estimated_weeks": Decimal("17")},
            "sessions": [{"week_number": Decimal("1"), "exercises": [
                {"sets": Decimal("2"), "duration_minutes": Decimal("15"), "load_value": Decimal("82.5")},
            ]}],
            "is_owner": True,
        }

    monkeypatch.setattr(module, "template_get", get)
    result = json.loads(module.handler({"sk": "template#1", "actor_pk": "person"}, None)["body"])
    assert result["meta"]["estimated_weeks"] == 17
    exercise = result["sessions"][0]["exercises"][0]
    assert exercise == {"sets": 2, "duration_minutes": 15, "load_value": 82.5}
    assert type(exercise["sets"]) is int and type(exercise["load_value"]) is float
