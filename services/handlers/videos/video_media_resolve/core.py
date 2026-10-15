from __future__ import annotations

import asyncio

from .._video_store import get_health_table, get_media, get_session_store, lift_profile_slot, load_phases, resolve_pk


async def video_media_resolve(args: dict) -> str:
    def resolve():
        pk = resolve_pk(args)
        key = str(args.get("s3_key") or "")
        health_table = get_health_table()
        store = get_session_store(args)
        filename = key.rsplit("/", 1)[-1]
        video_id = filename.rsplit(".", 1)[0]
        media = get_media(health_table, pk, video_id)
        if not media and "/" in key:
            video_id = key.rsplit("/", 2)[-2]
            media = get_media(health_table, pk, video_id)
        if not media or media.get("status") not in {"ready", "confirmed", "legacy"}:
            raise ValueError("Media key is not attached to this athlete")
        program_sk = str(media.get("program_sk") or "")
        phases = load_phases(health_table, pk, program_sk)
        allowed_keys = {media.get("processed_s3_key"), media.get("thumbnail_s3_key")}
        if media.get("legacy"):
            allowed_keys.add(media.get("s3_key"))
        if key not in allowed_keys:
            raise ValueError("Media key is not attached to this athlete")
        if media.get("lift"):
            pointer = health_table.get_item(Key={"pk": pk, "sk": "program#current"}, ConsistentRead=True).get("Item") or {}
            program_keys = [program_sk]
            if pointer.get("ref_sk") and pointer["ref_sk"] not in program_keys:
                program_keys.append(pointer["ref_sk"])
            if not any(
                (slot := lift_profile_slot(health_table, pk, candidate, str(media["lift"]), str(media["angle"])))
                and slot.get("video_id") == video_id
                and key in {slot.get("s3_key"), slot.get("thumbnail_s3_key")}
                for candidate in program_keys
            ):
                raise ValueError("Media key is not attached to this lift profile")
            return key
        for session in store.list_sessions_on_date_sync(program_sk, str(media.get("session_date") or ""), phases):
            if str(session.get("id") or session.get("session_id") or "") != str(media.get("session_id")):
                continue
            for video in session.get("videos") or []:
                if video.get("video_id") == video_id and key in {video.get("s3_key"), video.get("processed_s3_key"), video.get("thumbnail_s3_key")}:
                    return key
        raise ValueError("Media key is not attached to this athlete")

    return await asyncio.to_thread(resolve)
