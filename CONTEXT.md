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
makes one, whether or not the store ended up different. Only an administrator
may receive one — Home Assistant refuses the subscription to anyone else (#13),
which is why the Panels broadcast below exists and is not the same thing.
_Avoid_: notification, permission change event, delta, the payload as a contract

**Panels broadcast**:
The `panels_updated` event: "ask for your panels again". Home Assistant's own
event, not this integration's, and the only one that reaches a
non-administrator — so it is what carries a Permission change to the user the
change is about. Fired by the Panel Gate: on install, on restore, when the
store loads, and once per Permission write, debounced. It carries no payload at
all, and it is a global broadcast — every connected client re-reads, not just
the user concerned.
_Avoid_: Announcement, panel event, push, notification, panel update

**Panel Gate**:
The backend layer that decides which panels leave Home Assistant. It wraps Home
Assistant's own `get_panels`, drops the panels a non-administrator has no View
permission for, and never touches an administrator's answer. Single owner: the
panel list a browser receives is the whole of what that user may see. Installed
in `async_setup`, handed back on unload — so disabling this integration lifts
every restriction, deliberately (ADR-0011).
_Avoid_: backend filter, panel filter, sidebar filter, interceptor

**Degraded set**:
What the Panel Gate sends a non-administrator when it is running and cannot
answer: `notfound` and `profile`, built from the panel registry, and nothing
else. A refusal in the shape of an answer. Every way of reaching it except one
— the Permission store not being loaded yet, which happens once per start and
corrects itself — is an error in the log and a persistent notification.
_Avoid_: fallback, empty panels, safe mode, minimal set

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
