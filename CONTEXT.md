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

**Announcement**:
What a write to the Permission store says about itself: the
`permission_manager_updated` event, fired from the one place the store can be
written from. It means "the store has been written to, re-read it" and nothing
more — every consumer re-fetches, none reads the payload, and the payload is
diagnostic detail for whoever is reading a trace (ADR-0010). Every write path
makes one, whether or not the store ended up different.
_Avoid_: notification, permission change event, delta, the payload as a contract

**Filter**:
A JS module injected on every HA page that hides what a user has no View
permission for. Three exist: sidebar filter, lovelace filter, access-denied.
_Avoid_: guard, interceptor, middleware

**Access Denied page**:
The page the Access Denied Filter puts in place of a panel a user has no View
permission for. A panel element of its own, with its own header and a sticky
toolbar: it replaces the content rather than covering it, which is what keeps
it apart from the Loading overlay below.
_Avoid_: Access Denied overlay, access denied screen, 403 page

**Loading overlay**:
An opaque cover over a Home Assistant page, raised before anything is known
about the user, so that no panel is visible until the Permission store has
been applied. One owner: the sidebar Filter raises it and the lovelace Filter
defers to it. It lifts itself for an administrator as soon as Home Assistant
says who the user is, without waiting for anything a Filter imports (ADR-0009).
For anyone else only the Filter that raised it lifts it, when that Filter
finishes — so a Filter that never finishes leaves it up. The Access Denied
Filter's page is not one of these. Expected to go with the Filters when the
Panel Gate lands.
_Avoid_: Access Denied overlay, loading screen, splash, spinner

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
