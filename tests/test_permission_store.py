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

    No consumer reads the payload, so a spurious announcement costs whoever is
    listening one round trip — while a missing one is issue #14.
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
# is held here as source text in the idiom tests/frontend_assets.test.mjs
# uses: what cannot be run offline is at least held to being spelt in one
# place. Each was checked by breaking it.
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

    Every `async_fire` in the integration is named rather than counted, so a
    module that starts firing something shows up here whatever it fires. There
    are two events and they are not interchangeable: this one says "the
    Permission store has been written to, re-read it" and only an administrator
    is allowed to receive it (#13), while `panels_updated` says "ask for your
    panels again" and reaches everybody. ADR-0011 has the distinction.
    """
    fired_in = {
        name: sorted(set(re.findall(r"async_fire\(\s*([A-Za-z_][A-Za-z0-9_]*)", source)))
        for name, source in python_sources().items()
        if "async_fire(" in source
    }

    assert fired_in == {
        "__init__.py": ["EVENT_PERMISSION_MANAGER_UPDATED"],
        "panel_gate.py": ["EVENT_PANELS_UPDATED"],
    }

    # Named above, counted here: one site, not one spelling of several sites.
    announcements = re.findall(
        r"async_fire\(\s*EVENT_PERMISSION_MANAGER_UPDATED",
        python_sources()["__init__.py"],
    )
    assert len(announcements) == 1


def test_every_write_also_tells_the_browsers():
    """The second announcement lives beside the first, in the one write path.

    Issue #19. Home Assistant refuses a non-administrator's subscription to
    `permission_manager_updated` (#13), and a revocation is about a
    non-administrator — so on its own, the announcement above never reaches the
    user whose access just changed. `panels_updated` does, and with the Panel
    Gate deciding, re-running `get_panels` is the whole of what their page has
    to do about it.

    Held here rather than beside the Gate's own tests because it is the same
    invariant as the one above, for the same reason: one write path, and it
    cannot be added to without both announcements. Called once, from
    `_async_write`, and from nowhere else.
    """
    called_in = {
        name: len(re.findall(r"await async_broadcast_panels_changed\(hass\)", source))
        for name, source in python_sources().items()
        if "async_broadcast_panels_changed(hass)" in source
    }

    assert called_in == {"__init__.py": 1}

    init = python_sources()["__init__.py"]
    write = init[
        init.index("async def _async_write("):init.index("async def async_set_permission(")
    ]
    assert "await async_broadcast_panels_changed(hass)" in write


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


def test_no_frontend_module_subscribes_to_the_announcement():
    """The payload is diagnostic, and since v2.0.13 nothing here even hears it.

    ADR-0010 is about consumers re-fetching rather than reading `event.data`.
    The two that did were the Filters, and deleting them (#20) left the
    Announcement with no consumer in this repo at all: a live page learns of a
    Permission change from the Panels broadcast now, which has no payload to
    read.

    So the check is the stronger one the code allows. A frontend module that
    subscribes to the Announcement again is a browser being told something
    about access over an event Home Assistant refuses to a non-administrator
    (#13) — the shape of every bug issue #16 closed.
    """
    for path in sorted((COMPONENT / "frontend").glob("*.js")):
        source = path.read_text(encoding="utf-8")

        assert "permission_manager_updated" not in source, path.name
