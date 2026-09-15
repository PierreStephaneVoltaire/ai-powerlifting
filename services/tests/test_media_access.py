from types import SimpleNamespace

import pytest

from services.authorization import check_context
from services.dispatch import OperationError
from services import media_access


def test_form_media_checks_current_allocation_and_permissions(monkeypatch):
    allocations = {
        ('athlete', 'Media#form'): {'media_id': 'form', 'lift': 'squat'},
        ('athlete', 'Media#session'): {'media_id': 'session'},
    }
    def get_item(**kwargs):
        assert kwargs['ConsistentRead'] is True
        key = kwargs['Key']
        return {'Item': allocations.get((key['pk'], key['sk']))}
    monkeypatch.setattr(media_access, 'database', lambda: SimpleNamespace(Table=lambda _: SimpleNamespace(get_item=get_item)))
    claims = {'iss': 'powerlifting-gateway', 'athlete': 'athlete'}
    videos_only = {'permissions': ['videos:read', 'videos:write']}
    authorized = {'permissions': [*videos_only['permissions'], 'lift-profiles:read', 'lift-profiles:write']}
    assert check_context('video_upload_presign', {'lift': 'squat'}, claims, authorized) is authorized
    for operation, args in [
        ('video_upload_confirm', {'video_id': 'form'}),
        ('video_media_resolve', {'s3_key': 'athlete/form/revision.mp4'}),
        ('video_media_resolve', {'s3_key': 'athlete/form.jpg'}),
        ('video_remove', {'video_id': 'form'}),
        ('video_update_metadata', {'video_id': 'form'}),
    ]:
        assert check_context(operation, args, claims, authorized) is authorized
        with pytest.raises(OperationError, match='lift-profiles'):
            check_context(operation, args, claims, videos_only)
        with pytest.raises(OperationError):
            check_context(operation, args, {**claims, 'athlete': 'other'}, authorized)
    assert check_context('video_upload_confirm', {'video_id': 'session', 'lift': 'squat'}, claims, videos_only) is videos_only
    with pytest.raises(OperationError):
        check_context('video_media_resolve', {'s3_key': 'athlete/form.jpg'}, claims, {'permissions': ['lift-profiles:read']})
