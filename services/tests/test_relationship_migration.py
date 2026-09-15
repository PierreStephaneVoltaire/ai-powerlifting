from scripts.migrate_legacy_relationship_grants import canonical, request_record


def test_migration_request_indexes_delegate_roster_and_preserves_consent(monkeypatch):
    monkeypatch.setattr("scripts.migrate_legacy_relationship_grants.person_record", lambda identifier: {"pk": "owner-person"} if identifier == "athlete" else {"pk": "delegate-person"})
    legacy = {"pk": "Grant#athlete", "sk": "Grantee#delegate#2026-09-01T00:00:00+00:00#coach", "athlete_mapped_pk": "athlete", "grantee_mapped_pk": "delegate", "grant_type": "coach", "scope": "write", "permissions": ["sessions:read", "sessions:write"], "tied_competition_ids": ["meet"], "tied_competition_dates": {"meet": "2026-09-01"}, "expires_at": "2026-09-08T23:59:59+00:00", "note": "consented", "created_at": "2026-09-01T00:00:00+00:00"}
    grant = canonical(legacy)
    request = request_record(legacy, grant)
    assert request["recipient_person_pk"] == "delegate-person"
    assert request["inbox_pk"] == "Inbox#delegate-person"
    assert request["sent_pk"] == "Sent#owner-person"
    assert request["roster_pk"] == "Roster#delegate-person"
    assert request["permissions"] == legacy["permissions"]
    assert request["tied_competition_ids"] == ["meet"]
    assert request["note"] == "consented"
