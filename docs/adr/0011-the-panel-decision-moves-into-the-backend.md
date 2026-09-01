# The panel decision moves into the backend, behind one wrapped handler

> **Update, v2.0.13.** All four sub-issues have landed. #20 deleted the Filters,
> so the two places below that say they still ship — "What this supersedes" and
> "What this does not answer" — describe the release this document landed with
> (v2.0.11) and not the code as it stands. The supersession list has been
> corrected in place, because it is an index rather than a dated claim, and
> ADR-0009 has been added to it: the loading overlay went with the Filters.
>
> The prediction that the two layers must not coexist held, with a wrinkle
> worth recording: #18 and #20 did **not** ship together. v2.0.11 through
> v2.0.12 ran a Gate underneath Filters that had nothing left to do, and the
> baseline contamination ADR-0007 warns of did not bite, because the Gate
> subtracts from what a Filter would have subtracted from anyway.

Issue #16, implemented in #17 (the decision), #18 (the Gate), #19 (the event)
and #20 (deleting the Filters). Numbered 0011 rather than the 0009 #16 asked
for: 0009 and 0010 were taken while #16 was open.

Every panel decision this integration made happened in the browser, after Home
Assistant had already handed the user the full panel map. That is why a Filter
that does not run is a non-admin with 28 panels and a page that looks entirely
normal (#12), and it is the shared root of #6, #7, #8 and #11 — four tickets
that are all some version of "this time the JavaScript did not run correctly".

**The decision moves to the one place the panel map leaves Home Assistant.** A
browser then never receives a panel its user may not see, and the whole failure
class goes with the code that produced it.

## What was verified before anything was written

Against Home Assistant 2026.7.2 source, and live on 192.168.2.6.

**One exit.** `websocket_get_panels` in
`homeassistant/components/frontend/__init__.py` is the only place a panel map
reaches a browser — nothing embedded in HTML, no REST endpoint. It filters on
exactly one per-user dimension, `require_admin`.

**Handlers are a shared, overwritable dict.** `async_register_command` does
`handlers[command] = (handler, schema)` — silently, no check, no warning. And
`ActiveConnection.__init__` does `self.handlers = self.hass.data[const.DOMAIN]`,
a **reference, not a copy**, so taking over affects connections that already
exist and handing back takes effect immediately.

**`send_message` is swappable.** It is in `ActiveConnection.__slots__`, assigned
in `__init__`, and Home Assistant reassigns it itself in `async_handle_close()`.

**There is a push channel a non-admin may use.** `EVENT_PANELS_UPDATED` is in
the WebSocket API's `SUBSCRIBE_ALLOWLIST`, and the frontend's `subscribePanels`
re-runs `get_panels` on it. Measured live: a non-admin's `subscribe_events` for
`panels_updated` is accepted, and for `permission_manager_updated` is refused
(`unauthorized`) — which is #13.

**The leak was Home Assistant's own non-admin list, and our own Control Panel
on top.** Live `get_panels` with nothing of ours filtering: admin 37, non-admin
28 — the same 28 #12 measured. Both counts include the two panels this
integration registers; with it disabled the same instance answers 35 and 27, and
27 is what a stock non-admin sees. So the fail-open exposed everything a stock
non-admin would see, plus the Control Panel, and nothing more.

## The decision

### 1. Wrap, do not reimplement

Swap `connection.send_message` for the duration of one call, let Home Assistant
compute its own answer, delete keys from the result. Nothing in `panel_gate.py`
copies Home Assistant's logic, so a change to `to_response()` or to
`config_override` cannot silently make us wrong. The panels that survive are the
same objects Home Assistant put in the result; the Gate's only edit is which
keys are there.

### 2. A denied panel is absent, not hidden

Not `show_in_sidebar: false` — that leaves a route a bookmark or `navigate()`
still reaches, and it would keep the whole frontend layer alive to cover the
content. This is what retires ADR-0008's anchor and the Access Denied page with
it: there is nothing to cover, because there is nothing to route to.

### 3. Administrators are never filtered

Not one key, and their `send_message` is not swapped at all — so there is
nothing to be left holding if the original throws on the way out. This is what
keeps the Permission Manager panel reachable when everything else here has
failed, and it is why the bootstrap trap #12 worries about does not exist: the
backend knows who is an administrator without having to ask the browser.
`connection.user.is_admin` is readable before the answer is, so the escape hatch
does not depend on the answer being one we understand.

### 4. When we are running and cannot answer, we close

A non-administrator then receives the **degraded set** — `notfound` and
`profile`, built from the panel registry rather than from a literal, so a panel
Home Assistant has stopped registering makes the answer smaller rather than
naming something that is not there. Four ways of not being able to answer, all
of them an error in the log and a persistent notification:

- the response is not a successful `result` dict for the message we are watching;
- Home Assistant's handler sent nothing while we were watching;
- Home Assistant's handler raised;
- deciding raised.

An error response is degraded rather than passed through. It carries no panel
map, so passing it on would leak nothing — but it leaves the browser with no
route at all, and it means the Gate is watching something it does not
understand. Both are worth saying out loud, and a refusal that still routes is
the more usable of the two failures.

The fifth case is the one that is expected: **the store is not loaded yet.**
Between installing and `async_panel_gate_store_loaded()` we are running and
cannot answer, so a non-administrator is refused. The window is one file read
at startup, and the alternative is the naked window `85d4977` caught in the act,
where a browser reconnecting during startup read the full list. That one is a
warning and no notification: it is expected once per start, and it corrects
itself. `panels_updated` is fired when the store arrives, so a page that asked
inside the window is told to ask again.

### 5. When we are not running at all, there is no choice to make

Home Assistant serves its own list, and **disabling this integration lifts every
restriction**. That is deliberate: it is how an administrator recovers an
instance they have locked themselves out of, and it is now in the README rather
than only in the code. It is also why failing to install is an error and a
notification and not a debug line — an instance with no Gate looks entirely
normal to everybody except the user who is supposed to be restricted, which is
#12's failure mode arriving by a different road.

Two ways of not being in control are reported and refuse to install: there is
no `get_panels` handler, or the one registered does not belong to
`homeassistant.components.frontend` because somebody else got there first.
Wrapping a third party's wrapper would hide both of us. For the same reason,
restoring checks that the handler on top is still ours: putting the original
back over somebody else's registration would delete theirs.

### 6. Install in `async_setup`, restore in `async_unload_entry`

`async_setup` runs before any config entry, and therefore before the store is
read, before the services are registered and before our own panels are. It also
runs once per Home Assistant lifetime, so `async_setup_entry` installs too —
a disable/enable cycle never comes back through `async_setup`. Both calls are
idempotent and `tests/test_panel_gate.py` holds the order of them as source
text, because where the Gate is installed from is the whole of its startup
guarantee and none of it can be run offline.

A reload is unload plus setup, so there is a millisecond window with the Gate
off. Accepted: the alternative is not reloading.

### 7. One release, no coexistence

A version with both layers would let the frontend read a backend-filtered map as
its unfiltered baseline — ADR-0007's contamination, from a source the `FILTERED`
mark cannot see. So #18 and #20 ship together. Rolling back is a HACS downgrade
to a tested state; a coexistence release is a state nobody has tested.

### 8. Upstream in parallel

Home Assistant has no per-user panel hook. The wrap is a bridge; ask for the
real thing, and delete the bridge when it lands.

The ask is written and lives at
[`docs/upstream/2026-08-31-per-user-panel-hook.md`](../upstream/2026-08-31-per-user-panel-hook.md):
one registration point at `get_panels`, given the user and the panel keys Home
Assistant has already computed, allowed to subtract and never to add. It was to go to
`home-assistant/architecture` as a discussion.

**It was never sent.** 2026-09-01: #28 closed without posting it, and nothing
tracks sending it now. The draft stays where it is — corrected, and checked
line for line against 2026.7.2 — as the record of what we would have asked for.

So this section's second half did not happen, and the consequence belongs here
rather than only in the closed issue: **the wrap is not a bridge, it is the
mechanism.** Everything the draft says about the technique still holds against
us. `async_register_command` overwrites in silence, so a second integration
taking over `get_panels` wins and is never reported, and the users of whichever
one registered first quietly receive an unfiltered list. Our install-time checks
refuse to wrap a handler that is not `homeassistant.components.frontend`, which
catches us arriving second. Nothing catches us being arrived upon. That is the
standing risk of not asking, and it is now permanent rather than temporary.

Anyone reviving this starts by redoing two things the draft cannot keep fresh
on its own: the search for an existing upstream discussion, and the check that
the handler quoted in it still matches the version they are on.

## One decision, one function, and the run that proved it necessary

`panel_policy.visible_panel_ids()` is the whole answer to "which panels may this
user see", and both the Gate and `get_panel_permissions` read it (#17). They
have to, and the evidence is the Gate's own first spike run: a non-admin came
back with five panels where the report said four. The extra one was the stub
`lovelace` that `is_unroutable_panel()` exists for — the Permission store still
holds `panel_lovelace: 1` for that user from before discovery stopped offering
it, `ws_get_panel_permissions` drops it deliberately, and the spike's own rule
did not. Two places answering the same question disagreed on the first run.

The Gate hands that function the panels **Home Assistant already computed for
this user**, and the function never returns more than it was given. So the
`require_admin` filtering stays Home Assistant's, and ours only ever subtracts.

## The two events are not redundant

They look it, and they are not. This is the section #16 asked for.

| | `permission_manager_updated` | `panels_updated` |
| --- | --- | --- |
| means | the Permission store has been written to, re-read it | the panel list changed, ask for it again |
| audience | the admin-side consumers | every browser, including the restricted user's |
| a non-admin may subscribe | **no** — Home Assistant refuses it (#13) | yes — it is in `SUBSCRIBE_ALLOWLIST` |
| fired from | `_async_write()` in `__init__.py`, once per write (ADR-0010) | `panel_gate.py` — on install, on restore, when the store loads, and on every Permission write |
| payload | diagnostic, never read (ADR-0010) | none |
| debounced | no, one per write | yes, 1.0 s, leading edge first |

The distinction that matters is the third row. A revocation is *about* a
non-administrator, and that user's page is the one Home Assistant will not let
hear about it. `panels_updated` is the only channel that reaches them, which is
why the Gate uses it and why #19 fires it from the write paths rather than
relaying `permission_manager_updated`, which would inherit the refusal.

ADR-0010 already contradicted #19 on what `permission_manager_updated` is for,
and that correction stands: it is not fine-grained, nothing reads its payload,
and the Permission Manager panel does not subscribe to it.

`tests/test_permission_store.py` names every `async_fire` in the integration
rather than counting them, so a module that starts firing something shows up
whatever it fires. It also holds `_async_write()` to making both announcements,
in the same way and for the same reason it holds it to making the first.

### Both events go out for every write, and the broadcast is debounced

`async_broadcast_panels_changed()` is called for **every** write, including one
that touched no panel and one that changed nothing. A decision in front of an
Announcement is exactly how two of the five write paths came to be silent (#14),
and the same reasoning holds for the Panels broadcast; it would buy little here
anyway, because the debounce already bounds the cost.

The debounce is **1.0 s with the leading edge first**, so the write that starts
a burst reaches an open page at once and everything in the following second
collapses into one more broadcast. Measured on the instance at 2 broadcasts for
6 back-to-back writes, arriving at 0.02 s and 1.02 s.

The number is the one `async_save_permissions()` gives `Store.async_delay_save`,
because #19 asked the two to match. **They are not causally linked**, and it is
worth saying so because the opposite is the natural assumption: the Gate answers
from the in-memory map in `hass.data[DOMAIN]`, which `_async_write` has already
mutated before it broadcasts, and `async_delay_save` delays only the write to
disk that nothing reads again until a restart. There is no window in which a
browser could re-read stale rows — and if there were, the leading edge would
already be inside it, going out a whole cooldown before the save.

What actually decides the number is that it has to be long enough to collapse a
run of back-to-back service calls and short enough that the trailing broadcast
still arrives while somebody is looking. The test holding the two values equal
is a tripwire, so that retuning the save delay is a decision about this one too
rather than an accident.

`bulk_set_permissions` was already one write rather than one per row (ADR-0010),
so the burst the debounce is actually for is the one #19 does not name: several
service calls in quick succession, and the registry listeners, which reach the
store once per deleted area or label.

### `panels_updated` is a global broadcast

One user's Permission change makes **every** connected client re-run
`get_panels`, not only the user it concerns. Home Assistant's event bus has no
way to address one connection, and `subscribePanels` re-runs the command on any
`panels_updated` whoever fired it. At household scale that is a handful of small
round trips and the debounce bounds them.

It is written down because it does not look like this from the call site. A
future reader who takes it for point-to-point will size something wrongly — and
if this integration ever runs somewhere with a large number of simultaneous
sessions, this is the line that has to be reopened rather than discovered.

## Issue #7's "nothing checks", answered

`ROUTER_FALLBACK_PANELS` keeps `notfound` without a Permission because Home
Assistant resolves its default panel as `panels[default] ?? panels.home ??
panels.notfound` and throws reading `.url_path` when all three are gone. The
frontend could only assume that panel exists; the backend can look, and now does
at install time.

A missing one is reported and **does not stop the Gate installing.** Refusing to
install would lift every restriction on the instance in order to protect one
router fallback, which is the worse of the two failures by a distance.

#7 also offered a second option — stop depending on `notfound` and anchor
whatever the default-panel lookup resolves to. That is harder here, not easier:
the resolution lives in the browser and reads the user's own `defaultPanel`,
which the backend does not have. What would have been a lateral move in the
frontend is a reimplementation in Python.

## What this supersedes

ADR-0005, ADR-0007, ADR-0008 and ADR-0009 are all about the internals of
Filters that #20 deleted in v2.0.13 — the last of them about the loading overlay
`ha_sidebar_filter.js` raised. All four are marked superseded by this one and
left in place, as the record of how those layers worked and why each existed.

**ADR-0006 stays live.** Its rule — an asset carries its cache buster onto what
it pulls in — still applies: the two panels still import `lit.js`, and
`tests/frontend_assets.test.mjs` still holds it. Only its scope narrows, to
those two files.

## What this does not answer

**Live updates for areas and labels.** The mechanism here is the likely answer
to #13's other half too, but nothing in it applies to a Resource that is not a
panel. Still open.

**Whether the frontend Filters are gone.** They are not, in the release this
ADR lands with; that is #20, which ships alongside. Until it does, this document
describes a Gate running under Filters that no longer have anything to do.

**Who reads a user's rows out of the store.** `permissions.get(user_id, {})`
is now spelt in eight places across `__init__.py`, `services.py`,
`websocket_api.py` and `panel_gate.py`. The *decision* is shared and that is
what #17 was about; the *lookup* is not, and never has been. Unifying it is a
change of its own — `permission_store.py` is the obvious home, and its own
opening sentence says it holds writes — and it was left out of this one rather
than made worse quietly.

**What a third party wrapping `get_panels` after us should get.** The Gate
declines to restore over them and says so. Nothing decides whose filtering wins
while both are installed, because nothing has ever been observed doing it.
