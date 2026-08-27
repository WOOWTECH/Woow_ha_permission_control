# One write path, one announcement, and the payload means nothing

Issue #14. Five services write the Permission store; three fired
`permission_manager_updated` and two did not, and the two silent ones were the
revocations — `remove_user_permissions` and `remove_resource_permissions`. So
taking access away was the one direction no live page was told about.

## Why two were missed

The announcement was written where each write path happened to end.
`async_set_permission` fires at the bottom of the helper in `__init__.py`;
`bulk_set` and `reset_all` fired at the bottom of their *handlers* in
`services.py`, each having reached into `hass.data` and mutated the store for
itself; and the two delete helpers wrote the store and returned.

Five sites, three of which remembered. Nothing made the fourth and fifth wrong
at the time they were written — a helper that saves and returns is a perfectly
ordinary-looking helper.

It was not a design gap. `docs/plans/2026-05-15-permission-services-design.md`
specifies "**Events**: Fires `permission_manager_updated`" under all five write
services, including both removals. And `docs/services-guide.md` had a row for
each of the two saying the event came "(fired by underlying function)" — a
statement about a function that did not fire it, sitting under a heading that
said "All write operations fire". So both documents asserted the behaviour from
2026-05-15 to 2026-08-27 while the code did not have it. That is what makes a test the
answer here rather than a clearer document: the documents were already clear.

**The decision: there is one way to write the Permission store, and it saves
and announces.** `_async_write()` in `__init__.py` takes a mutation, applies it
to the map off `hass.data`, calls `async_save_permissions()`, and fires the
event. Every write path goes through it, and a new one cannot be added without
both, because there is nowhere else the store can be reached from.

The mutations themselves moved to `permission_store.py`, which imports nothing
from Home Assistant, in the idiom `panel_policy.py` established. Each takes the
map, mutates it in place, and **returns the announcement it owes**. That is the
structural half of the same decision: the return type of a write is the thing
it has to say about itself, so a write that says nothing does not type as a
write. `tests/test_permission_store.py` asserts the store's shape after each of
the five, and that each returns an `action`, offline and without an instance.

The two source-text invariants in that file are the part that cannot be run
offline: `async_fire(EVENT_PERMISSION_MANAGER_UPDATED` appears exactly once and
in `__init__.py`, and `async_save_permissions(` is called from `__init__.py`
alone. The second is the tell for the defect this ADR is about — a module that
persists the store is one that made a change of its own, and therefore one with
an announcement to forget.

## The payload is diagnostic, not a contract

Issue #14 asks what the payload means, having noticed the shapes differ per
site: `{user_id, resource_id, level}` from `set_permission` against
`{action, count}` from `bulk_set`.

**It means nothing, and that is now written down.** The event says "the
Permission store has been written to, re-read it". Both Filters already work
that way and always have — `ha_sidebar_filter.js` subscribes with a handler
that takes an `event` and never opens it, `ha_lovelace_filter.js` takes no
argument at all, and both re-fetch and compare a hash of the result. Neither
would behave differently if the payload were empty.

So the payload was made uniform rather than meaningful. Every announcement
carries an `action` — one of `set`, `bulk_set`, `remove_user`,
`remove_resource`, `reset_all` — and whatever detail that write has to hand: the
ids it names, and a `count` of what it touched. It is there for whoever is
reading a trace, and `tests/test_permission_store.py` holds each shape so a
trace can be read against this file.

The alternative was to make it a contract — say what changed precisely enough
that a consumer could apply the change without re-fetching. Rejected: it buys
one round trip per write on a rare event, and it costs the correctness margin
that re-fetching gives. A consumer that applies the change it was handed is a
consumer that drifts the first time it misses one, and #14 exists because
announcements do get missed. Re-fetching means an extra announcement is free and
a dropped one self-heals on the next.

The invariant that keeps that true is also a test: neither Filter's
`permission_manager_updated` handler reads `event.data`. If one starts to, the
payload has become a contract and this decision needs reopening rather than
quietly widening.

## Every write announces, including one that changed nothing

`async_delete_user_permissions` used to save only `if user_id in permissions`,
and the equivalent guard in `async_delete_resource_permissions` was a `modified`
flag. Both are gone: the write happens, and the announcement goes out, whether
or not the map differed afterwards.

This is the cheaper way to be wrong. A spurious announcement costs each live
page one `get_all_permissions` round trip and no re-render, because the hash
comparison finds nothing new, plus one delayed `Store` save of a map that did
not change. A missing one is issue #14. Making the announcement conditional puts
a decision in front of it, and a decision in front of it is how the two
revocations came to be silent in the first place.

It does mean the registry listeners announce on every area, label and dashboard
deletion, most of which carry no Permission at all. That is a handful of events
a year, on a page that already re-fetches on `user_updated`,
`homeassistant_auth_updated` and every `lovelace_updated` — including the
dashboard deletion this now announces a second time, half a second earlier.

## Measured on the instance, before and after

`tests/verify_issue_14.py` is the issue's own instrument, made repeatable: it
subscribes to the event from an administrator's connection, calls each write
service over the REST API, and counts what arrives. It was run on 192.168.2.6
(HA 2026.7.2) against v2.0.8, then against v2.0.9, then against v2.0.8 again
after a rollback so that all seven cases were measured on both. Records are in
`tests/screenshots/issue-14/`.

| Write path | v2.0.8 | v2.0.9 |
| --- | --- | --- |
| `set_permission` | 1 | 1 |
| `bulk_set_permissions` | 1 | 1 |
| `remove_resource_permissions` | **0** | 1 |
| `remove_user_permissions` | **0** | 1 |
| `remove_user_permissions`, on a user holding nothing | **0** | 1 |
| `reset_all_permissions` | 1 | 1 |
| an area deletion, through the registry listener | **0** | 1 |

Every case answered HTTP 200 on both versions, which is the shape of the defect:
the write succeeded and said nothing.

The last row is the one the issue does not measure and the reason to care most.
`async_delete_resource_permissions` is reached from
`_handle_area_registry_update` with no service handler in front of it, so an
administrator deleting an area in the Home Assistant UI revoked every Permission
level on it and no page was told. Nobody is watching a page for that. The case
creates its own area, grants a level on it, deletes it, and cleans up.

`reset_all_permissions` was called, which #14 declined to do — "it erases the
store". The script reads the whole store first, restores it through
`bulk_set_permissions` at the end, and checks the result; the instance's
`.storage/ha_permission_manager` came back byte-identical to the backup taken
before the run, same sha256, on both versions. That is the condition on which
this ADR's "no live test" caveat is now withdrawn.

The payloads are in the records too, and they are what the section above
describes: `set_permission` on v2.0.8 carried `{user_id, resource_id, level}`
and now carries the same plus `action`, and `reset_all` carried `{action}` and
now carries a `count`.

## What the fix is worth today, measured against the issue

Issue #14 says an administrator watching a removal "sees nothing happen" because
"the Permission Manager panel listens to that event". **The panel does not
listen.** `frontend/ha_permission_manager.js` subscribes to nothing; it writes
through `permission_manager/set_permission` and updates its own local state, and
it has no removal control at all — the two remove services are reachable from
Developer Tools and the REST API, not from the panel.

What does listen on an administrator's page is the two Filters, injected on
every page. So the observable difference this fix makes today is that an
administrator's own sidebar and dashboard re-filter after a revocation, instead
of waiting for a reload. That is smaller than the issue claims, and it is still
the right direction: for a non-admin — the user a revocation is actually
about — the sidebar filter is the only thing standing between a removed
Permission level and a panel that is still offered.

It also stays bounded by #13 until #13 is fixed: a non-admin's subscription to
this event is refused by Home Assistant, so no non-admin page receives the
announcement however reliably it is fired. #14 is the half of that pair that can
be fixed from this side of the wire.

## What this does not answer

**#19 does not relay this event, by design.** Once the Panel Gate (#16) lands,
`panels_updated` is what tells a browser to re-read its panel list, and #19
fires it from all five write paths directly rather than chaining off
`permission_manager_updated`. `_async_write()` is where that second announcement
goes when it arrives — one site, already holding every write path — and #19's
debounce requirement is already half-met here, since `bulk_set_permissions` is
now one write rather than one per row.

**This contradicts #19 on what the two events are for, and #19 is the one that
is wrong.** #19 sets out the distinction to carry into ADR-0009 as:
"`permission_manager_updated` — fine-grained, carries user/resource/level, for
the Permission Manager panel." Neither half holds. The panel does not subscribe
to it (see above), and the payload is not fine-grained in any usable sense —
`bulk_set` and `reset_all` never carried user/resource/level, and now no site
promises to, because nothing reads it. What the event is actually for is the two
Filters, and what it actually says is "re-read the store". The rest of #19 is
unaffected: it is an argument for firing `panels_updated` at the write paths
rather than relaying, and that argument is about reliability, not payload.

**Nothing here was measured as a non-admin, and cannot be.** Every row of the
table above was read from an administrator's connection, because Home Assistant
refuses a non-admin's subscription to this event (#13). So the announcement is
proven to leave the backend and proven to arrive at an administrator's page.
Whether the user a revocation is *about* ever sees it is #13's question, and
this ADR cannot answer it.

**Whether a `count` of `0` should read differently from a `count` that is
absent** is unanswered because nothing reads either. It becomes a question the
first time something does, which is the same moment this decision has to be
reopened.
