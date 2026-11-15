# Bugs

- AssistantDrawer: pending proposals from earlier turns do not reappear after
  the drawer is reopened — the history endpoint returns no proposals, only the
  just-sent turn's job view carries them. Needs a proposals listing (e.g.
  include pending proposals in `GET /v1/conversations/{id}/history` or a
  `GET /v1/conversations/{id}/proposals`) and a frontend fetch on open.
