from __future__ import annotations

import logging
import re



logger = logging.getLogger(__name__)

MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")
NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
EXPIRY_TAIL_DAYS = 7  # Grant expires max(tied competition dates) + this many days.


async def grant_create(args: dict) -> dict:
    """Issue a new grant from an athlete to a coach or handler.

    The athlete (or a delegated coach/handler with grants:write on grants) is
    identified by `athlete_mapped_pk`. The grantee is `grantee_mapped_pk`.

    Returns the persisted grant. Raises ValueError on validation failure or on
    GRANT_LIMIT_REACHED when an active grant of the same type already exists.
    """
    raise ValueError("direct_grant_creation_retired_use_relationship_request")
