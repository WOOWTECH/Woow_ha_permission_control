# WebSocket command names are frozen across the merge

The merged integration still serves `area_control/get_permitted_areas`,
`area_control/get_area_entities`, `label_control/get_permitted_labels`, and
`label_control/get_label_entities` — command names belonging to two domains that
no longer exist.

This looks like an oversight and is not. The merge deliberately changed no API
contract: these commands are reachable by any WebSocket client, and this
deployment has an MCP server and user automations that may call them. Renaming
them to `ha_permission_manager/*` is a breaking change that deserves its own
release and its own deprecation window, not a free ride on a packaging change.

The four `WS_GET_*` constants in `const.py` were removed. They named
`ha_permission_manager/*` commands that were never registered and never
referenced — dead code that would have misled exactly this discussion.
