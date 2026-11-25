from services.runtime.dispatch import owner_aliases


def test_owner_aliases_come_from_verified_access():
    arguments = {"_person_pk": "sir_simpalot", "_access": {"person_pk": "sir_simpalot", "settings_pk": "sir_simpalot", "own_athlete_pk": "operator"}}
    assert owner_aliases(arguments) == {"sir_simpalot", "operator"}
    assert owner_aliases({"_access": {"own_athlete_pk": "operator"}}) == frozenset()
