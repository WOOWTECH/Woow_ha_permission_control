# Woow HA Permission Control

The ubiquitous language for this repo: a Home Assistant custom integration that
decides **which Home Assistant resources a non-administrator may see**, and gives
those users a device-control surface limited to what they are permitted.

## Language

**Permission Manager**:
The integration itself, HA domain `ha_permission_manager`. Sole owner of the
permission store and of every panel this repo ships.
_Avoid_: Permission Control, ha_permission_control, the plugin

**Permission Manager panel**:
The admin-only sidebar panel where permissions are assigned. Requires admin.
_Avoid_: admin page, matrix page, permission matrix

**Control Panel**:
The single non-admin-facing sidebar panel. Shows Areas and Labels as tabs and is
the only place an end user controls devices through this integration.
_Avoid_: Area Control, Label Control, area panel, label panel, dashboard

**Resource**:
A thing a permission can be granted on. Exactly three kinds, distinguished by a
prefixed id: `panel_*`, `area_*`, `label_*`.
_Avoid_: object, target, item

**Permission level**:
An integer against a (user, Resource) pair. Only two values exist: `0` Closed and
`1` View.
_Avoid_: role, grant, access level, scope

**Permission store**:
The `Store`-backed map from user id to Resource id to Permission level, persisted
at `.storage/ha_permission_manager`. The single source of truth.
_Avoid_: database, config, settings

**Filter**:
A JS module injected on every HA page that hides what a user has no View
permission for. Three exist: sidebar filter, lovelace filter, access-denied.
_Avoid_: guard, interceptor, middleware

**Panel Gate**:
The backend layer that decides which panels leave Home Assistant. It wraps Home
Assistant's own `get_panels`, drops the panels a non-administrator has no View
permission for, and never touches an administrator's answer. Single owner: the
panel list a browser receives is the whole of what that user may see.
_Avoid_: backend filter, panel filter, sidebar filter, interceptor

**Baseline**:
The unfiltered panel map a Filter applies filtering to: what Home Assistant
offered before this integration touched it. Read once on load and re-read after
a reset, never from a map a Filter produced — a baseline missing a panel cannot
offer it back when a Permission level is granted (ADR-0007).
_Avoid_: original panels, the panel list, the unfiltered state

**Dashboard**:
A Home Assistant Lovelace page, rendered into a `hui-root` element: the default
one Home Assistant serves at `/home`, and any added by hand. Governed by the
Permission on the panel Home Assistant routes to, never by a Permission of its
own. Not a thing this repo ships — the word is Home Assistant's, and the
Control Panel is never one of these.
_Avoid_: overview, lovelace page, view

**Dist repo**:
An auto-generated mirror repository that existed only to satisfy HACS's
one-integration-per-repo rule. Deprecated once this repo ships a single
integration.
_Avoid_: release repo, published repo
