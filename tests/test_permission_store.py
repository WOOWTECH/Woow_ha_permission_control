"""Unit tests for permission_store — the Permission store's writes, offline.

Home Assistant is not a dependency of these tests. permission_store holds every
write this integration makes to the Permission store, and the announcement each
one owes, so both are asserted here once instead of being observed by listening
on a live instance's event bus.

The bug behind them is issue #14: `remove_user_permissions` and
`remove_resource_permissions` wrote the store and returned, so taking access
away was the one direction no live page was told about.
"""
import re
import sys
from pathlib import Path

COMPONENT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "ha_permission_manager"
)
sys.path.insert(0, str(COMPONENT))

import permission_store  # noqa: E402
from permission_store import (  # noqa: E402
    ACTION_BULK_SET,
    ACTION_REMOVE_RESOURCE,
    ACTION_REMOVE_USER,
    ACTION_RESET_ALL,
    ACTION_SET,
    bulk_set_permissions,
    remove_resource_permissions,
    remove_user_permissions,
    reset_all_permissions,
    set_permission,
)

# Every write in this module, named as issue #14 names them.
WRITES = (
    set_permission,
    bulk_set_permissions,
    remove_user_permissions,
    remove_resource_permissions,
    reset_all_permissions,
)


def a_store():
    """Two users with a Permission level each on a shared and a private Resource."""
    return {
        "alice": {"panel_home": 1, "area_kitchen": 1},
        "bob": {"panel_home": 0},
    }


def apply(write, permissions):
    """Call one write with arguments that suit it, on the store given."""
    if write is set_permission:
        return write(permissions, "alice", "panel_home", 0)
    if write is bulk_set_permissions:
        return write(
            permissions,
            [{"user_id": "alice", "resource_id": "panel_home", "level": 0}],
        )
    if write is remove_user_permissions:
        return write(permissions, "alice")
    if write is remove_resource_permissions:
        return write(permissions, "panel_home")
    return write(permissions)


# =============================================================================
# What each write does to the store
# =============================================================================


def test_set_permission_writes_the_level():
    permissions = a_store()

    set_permission(permissions, "bob", "area_kitchen", 1)

    assert permissions["bob"] == {"panel_home": 0, "area_kitchen": 1}


def test_set_permission_opens_a_map_for_a_user_who_has_none():
    permissions = {}

    set_permission(permissions, "carol", "panel_home", 1)

    assert permissions == {"carol": {"panel_home": 1}}


def test_bulk_set_permissions_applies_every_entry():
    permissions = a_store()

    bulk_set_permissions(permissions, [
        {"user_id": "alice", "resource_id": "panel_home", "level": 0},
        {"user_id": "carol", "resource_id": "label_lights", "level": 1},
    ])

    assert permissions["alice"]["panel_home"] == 0
    assert permissions["carol"] == {"label_lights": 1}


def test_remove_user_permissions_drops_the_whole_user():
    permissions = a_store()

    remove_user_permissions(permissions, "alice")

    assert permissions == {"bob": {"panel_home": 0}}


def test_remove_resource_permissions_drops_the_resource_from_every_user():
    permissions = a_store()

    remove_resource_permissions(permissions, "panel_home")

    assert permissions == {"alice": {"area_kitchen": 1}, "bob": {}}


def test_remove_resource_permissions_drops_a_closed_level_too():
    """`0` is a Permission level, not an absence. A falsy level is still a write.

    bob holds panel_home at Closed and nothing else. Removing the Resource has
    to empty his map and be counted for it, or a revocation leaves a level
    behind for a Resource that no longer exists and announces that it did not.
    """
    permissions = {"bob": {"panel_home": 0}}

    announcement = remove_resource_permissions(permissions, "panel_home")

    assert permissions == {"bob": {}}
    assert announcement["count"] == 1


def test_reset_all_permissions_empties_the_store_in_place():
    """In place, because a function handed the map cannot rebind the slot."""
    permissions = a_store()
    held = permissions

    reset_all_permissions(permissions)

    assert permissions == {}
    assert held is permissions


# =============================================================================
# What each write announces — issue #14
# =============================================================================


def test_every_write_announces():
    """The whole of issue #14: a write that returns no announcement is one that
    leaves a live page offering access the Permission store no longer grants.
    """
    for write in WRITES:
        announcement = apply(write, a_store())

        assert isinstance(announcement, dict), write.__name__
        assert "action" in announcement, write.__name__


def test_the_five_writes_announce_five_distinct_actions():
    """`action` is what a reader of a trace tells the write paths apart by."""
    announced = {apply(write, a_store())["action"] for write in WRITES}

    assert announced == {
        ACTION_SET,
        ACTION_BULK_SET,
        ACTION_REMOVE_USER,
        ACTION_REMOVE_RESOURCE,
        ACTION_RESET_ALL,
    }
    assert len(announced) == len(WRITES)


def test_set_permission_announces_what_it_wrote():
    permissions = a_store()

    announcement = set_permission(permissions, "bob", "area_kitchen", 1)

    assert announcement == {
        "action": ACTION_SET,
        "user_id": "bob",
        "resource_id": "area_kitchen",
        "level": 1,
    }


def test_bulk_set_permissions_announces_once_for_the_whole_batch():
    permissions = a_store()

    announcement = bulk_set_permissions(permissions, [
        {"user_id": "alice", "resource_id": "panel_home", "level": 0},
        {"user_id": "carol", "resource_id": "label_lights", "level": 1},
    ])

    assert announcement == {"action": ACTION_BULK_SET, "count": 2}


def test_remove_user_permissions_announces_the_user_and_how_much_went():
    permissions = a_store()

    announcement = remove_user_permissions(permissions, "alice")

    assert announcement == {
        "action": ACTION_REMOVE_USER,
        "user_id": "alice",
        "count": 2,
    }


def test_remove_resource_permissions_announces_the_resource_and_how_many_users():
    permissions = a_store()

    announcement = remove_resource_permissions(permissions, "panel_home")

    assert announcement == {
        "action": ACTION_REMOVE_RESOURCE,
        "resource_id": "panel_home",
        "count": 2,
    }


def test_reset_all_permissions_announces_how_many_users_were_cleared():
    permissions = a_store()

    announcement = reset_all_permissions(permissions)

    assert announcement == {"action": ACTION_RESET_ALL, "count": 2}


def test_a_write_that_changed_nothing_still_announces():
    """The announcement means "re-read the store", not "something changed".

    Both Filters ignore the payload and re-fetch, so a spurious announcement
    costs one round trip and no re-render — while a missing one is issue #14.
    Removing a user who holds nothing is the cheapest way to reach that state,
    so it is the one pinned here.
    """
    permissions = a_store()

    announcement = remove_user_permissions(permissions, "nobody")

    assert announcement == {
        "action": ACTION_REMOVE_USER,
        "user_id": "nobody",
        "count": 0,
    }


# =============================================================================
# Source-text invariants
#
# The wiring from these functions to `hass.bus` needs a Home Assistant, so it
# is held here as source text in the idiom tests/routing_anchor.test.mjs
# established: what cannot be run offline is at least held to being spelt in
# one place. Each was checked by breaking it.
# =============================================================================


def python_sources():
    """Every Python module of the integration, by path below it.

    `rglob`, not `glob`: a write added in a subpackage would otherwise pass all
    three invariants below by not being looked at.
    """
    return {
        path.relative_to(COMPONENT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(COMPONENT.rglob("*.py"))
    }


def test_the_event_name_is_spelt_once():
    """One spelling in the integration's Python, constant and prose alike.

    A rename is then one edit, and no docstring is left describing an event
    that no longer goes out under that name — which is how a handler came to
    document an announcement it did not make.
    """
    spelt_in = [
        name for name, source in python_sources().items()
        if "permission_manager_updated" in source
    ]

    assert spelt_in == ["permission_store.py"]
    assert permission_store.EVENT_PERMISSION_MANAGER_UPDATED == "permission_manager_updated"


def test_the_event_is_fired_from_exactly_one_place():
    """`__init__.py` announces; nothing else does.

    Three handlers used to fire it for themselves and two forgot to. One firing
    site is what stops that recurring.
    """
    fired_in = {
        name: len(re.findall(r"async_fire\(\s*EVENT_PERMISSION_MANAGER_UPDATED", source))
        for name, source in python_sources().items()
        if "async_fire(" in source
    }

    assert fired_in == {"__init__.py": 1}


def test_only_init_writes_the_permission_store():
    """A write path reaches the store through `__init__.py`, or not at all.

    `async_save_permissions` is the tell: a module that calls it is persisting
    a change it made itself, which is a write path with its own announcement to
    forget. services.py used to be one, for `bulk_set` and for `reset_all`.
    """
    saves_in = [
        name for name, source in python_sources().items()
        if "async_save_permissions(" in source
    ]

    assert saves_in == ["__init__.py"]


def test_no_consumer_branches_on_the_announcement_payload():
    """The payload is diagnostic. A consumer re-fetches — ADR-0010.

    Each Filter subscribes with a handler that reads nothing off the event; if
    one starts reading `event.data`, the payload has become a contract and the
    decision needs revisiting rather than quietly widening.
    """
    frontend = COMPONENT / "frontend"
    for name in ("ha_sidebar_filter.js", "ha_lovelace_filter.js"):
        source = (frontend / name).read_text(encoding="utf-8")
        end = source.index('"permission_manager_updated"')
        handler = source[source.rindex("subscribeEvents(", 0, end):end]

        assert "event.data" not in handler, name
