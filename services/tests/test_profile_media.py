import pytest

from services import profile_media
from services.access import evaluate_facts
from services.dispatch import OperationError


def test_avatar_resolution_uses_canonical_owner_and_current_visibility(monkeypatch):
    key = 'profiles/username/avatars/ready.jpg'
    owner = {'pk': 'username', 'mapped_pk': 'athlete-a', 'avatar_url': key}
    monkeypatch.setattr(profile_media, 'person_record', lambda pk: owner if pk == 'username' else None)
    def current(person, athlete):
        assert athlete == 'athlete-a'
        return evaluate_facts(person, athlete, owner, owner if person == 'username' else None, [], {})
    monkeypatch.setattr(profile_media, 'current_context', current)
    args = {'pk': 'username', 's3_key': key, '_person_pk': 'username'}
    assert profile_media.handler(args, None) == {'s3_key': key}
    with pytest.raises(OperationError, match='not found'):
        profile_media.handler({**args, '_person_pk': ''}, None)
    owner['profile_visibility'] = 'public'
    assert profile_media.handler({**args, '_person_pk': ''}, None) == {'s3_key': key}
    with pytest.raises(OperationError, match='not found'):
        profile_media.handler({**args, 's3_key': 'profiles/other/avatars/private.jpg'}, None)
    with pytest.raises(OperationError, match='not found'):
        profile_media.handler({**args, 'pk': 'other'}, None)
