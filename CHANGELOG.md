# Changelog

## v2.0.0 — 2026-08-24

The three integrations in this repo are now one.

### Breaking

- **`ha_area_control` and `ha_label_control` no longer exist.** Both shipped panels
  that `ha_permission_manager`'s Control Panel already replaced. Remove them from
  `custom_components/` and delete their config entries.
- **The `/area-control` and `/label-control` panel URLs are gone.** Everything lives
  in Control Panel (`/ha-control-panel`), which has Areas and Labels as tabs.
  Bookmarks to the old URLs break; no redirect shim is registered.
- **HACS users must re-add this repository.** The domain is deliberately unchanged
  (`ha_permission_manager`), so if you keep `WOOWTECH/hacs-ha_permission_manager`
  as a custom repository HACS will go on serving you v1.0.3. Remove all three
  `WOOWTECH/hacs-*` custom repositories and add
  `WOOWTECH/Woow_ha_permission_control` instead.
- **Frontend assets moved off `/local/`.** They are served from
  `/ha_permission_manager_frontend/` now. This only matters if you referenced those
  URLs yourself.

### Unchanged on purpose

- The domain, the permission store at `.storage/ha_permission_manager`, the config
  entry, and all 14 services. Existing permissions survive the upgrade untouched.
- The WebSocket command names `area_control/*` and `label_control/*`, despite the
  domains being gone. Renaming them is a separate breaking change with its own
  deprecation window — see ADR-0004.

### Changed

- Repo is laid out as a standard HACS integration: `custom_components/ha_permission_manager/`
  plus a root `hacs.json`. The dist-repo mirroring (`hacs-dist.json` and its workflow)
  is deleted — it only existed to satisfy HACS's one-integration-per-repo rule.
- `www/` renamed to `frontend/`; static files are mounted from the package directory
  rather than a hardcoded `config/custom_components/...` path, so the integration
  works wherever it is installed.
- Added `zh-Hans` translations.
- Removed permission levels 2 and 3 from the translations. Only Closed (0) and
  View (1) have ever existed in code.
- Removed the `WS_GET_*` constants, which named WebSocket commands that were never
  registered, and the `AREA_PANEL_*` / `LABEL_PANEL_*` constants.

### Upgrading

1. Delete the **Area Control** and **Label Control** integrations in
   Settings → Devices & Services.
2. Remove `custom_components/ha_area_control/` and `custom_components/ha_label_control/`.
3. Update **Permission Manager** to v2.0.0.
4. Restart Home Assistant. Your permissions are preserved.

## v1.0.3 / v1.0.4 / v2.0.1 — 2026-04

Last release of the three-integration layout. See git history.
