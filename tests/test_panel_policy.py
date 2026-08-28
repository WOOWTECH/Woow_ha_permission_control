"""Unit tests for panel_policy — the pure panel decisions, no Home Assistant needed.

Home Assistant is not a dependency of these tests. panel_policy holds the
decisions that both discovery and the WebSocket API make about panels, so they
are asserted here once instead of being observed in a live browser.
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# panel_policy reads its constants out of the package's const.py, and neither
# file imports Home Assistant. Resolving `from .const` needs a package to
# resolve against, but not the package's __init__.py — that one does import
# Home Assistant. So a stand-in package is registered whose search path is the
# integration directory, and nothing else of the integration is executed.
_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "ha_permission_manager"
_offline_package = types.ModuleType("ha_permission_manager_offline")
_offline_package.__path__ = [str(_PACKAGE_DIR)]
sys.modules.setdefault("ha_permission_manager_offline", _offline_package)

from ha_permission_manager_offline.panel_policy import (  # noqa: E402
    admin_panel_resources,
    deleted_dashboard_resource_id,
    unroutable_panel_ids,
    visible_panel_ids,
)


def panel(**kwargs):
    """A panel as Home Assistant registers it: an object with attributes."""
    kwargs.setdefault("component_name", "custom")
    kwargs.setdefault("config", None)
    kwargs.setdefault("title", None)
    return SimpleNamespace(**kwargs)


def test_stub_lovelace_panel_is_unroutable():
    """The stub `lovelace` panel on an instance with no legacy overview.

    Home Assistant's own ha-panel-lovelace reads `this.panel.config?.mode` and
    navigates away when it is missing, so this panel never renders. `home` has
    `config: null` too and must not be caught by the same test.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home", config=None),
    }

    assert unroutable_panel_ids(panels) == {"lovelace"}


def test_admin_panel_resources_omits_the_panel_that_cannot_be_honoured():
    """The permission matrix must not offer a toggle that saves and does nothing.

    Discovery stopped offering the stub panel as a Resource, but the admin UI
    builds its own list. A toggle here that get_panel_permissions then drops is
    worse than the bug it replaced, so the exclusion has to hold at both ends.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home", title="Home"),
    }

    offered = admin_panel_resources(panels)

    assert [r["id"] for r in offered] == ["home"]


def test_admin_only_panels_are_not_offered_as_resources():
    """Home Assistant's own administrator panels carry no Permission."""
    panels = {
        "developer-tools": panel(),
        "config": panel(),
        "profile": panel(),
        "home": panel(component_name="home"),
    }

    assert [r["id"] for r in admin_panel_resources(panels)] == ["home"]


def test_a_resource_is_named_by_its_panel_title_then_its_config_then_its_id():
    panels = {
        "titled": panel(title="Titled"),
        "configured": panel(config={"title": "Configured", "mode": "storage"}),
        "bare": panel(),
    }

    names = {r["id"]: r["name"] for r in admin_panel_resources(panels)}

    assert names == {"titled": "Titled", "configured": "Configured", "bare": "bare"}


def test_panels_are_read_the_same_whether_dicts_or_objects():
    """Home Assistant hands panels over in either shape depending on version."""
    as_objects = {"lovelace": panel(component_name="lovelace", config=None)}
    as_dicts = {"lovelace": {"component_name": "lovelace", "config": None}}

    assert unroutable_panel_ids(as_objects) == unroutable_panel_ids(as_dicts) == {"lovelace"}


def test_a_real_dashboard_is_routable_and_stays_on_offer():
    """Only the stub is excluded. An instance with a legacy overview has a
    `lovelace` panel with a config mode, and it must keep its Resource."""
    panels = {"lovelace": panel(component_name="lovelace", config={"mode": "storage"})}

    assert unroutable_panel_ids(panels) == set()
    assert [r["id"] for r in admin_panel_resources(panels)] == ["lovelace"]


def test_the_matrix_never_offers_a_panel_the_permission_endpoints_would_drop():
    """The invariant the admin UI broke.

    ws_get_admin_data offers the Resources; ws_get_panel_permissions and
    ws_get_all_permissions report the levels. When those two lists disagree an
    administrator gets a toggle that saves a level nothing ever honours, so
    assert them against each other rather than trusting each in isolation.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home"),
        "config": panel(),
        "energy": panel(component_name="energy", title="Energy"),
        "dashboard-kitchen": panel(component_name="lovelace", config={"mode": "storage"}),
    }

    offered = {r["id"] for r in admin_panel_resources(panels)}
    dropped = unroutable_panel_ids(panels)

    assert offered & dropped == set()
    assert offered == {"home", "energy", "dashboard-kitchen"}


# =============================================================================
# visible_panel_ids — the one answer to "which panels may this user receive"
# =============================================================================


def test_a_stored_level_on_an_unroutable_panel_grants_nothing():
    """The disagreement that put this function here.

    The Permission store still holds `panel_lovelace: 1` for users granted it
    before discovery stopped offering the stub, and the level is left alone so
    it comes back to life if the panel ever becomes real. What must not happen
    is a sidebar row for a panel Home Assistant bounces straight off — the
    first spike of the Panel Gate handed one over, because it answered this
    question in a second place of its own.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home"),
    }

    visible = visible_panel_ids(
        panel_ids=["lovelace", "home"],
        panels=panels,
        user_permissions={"panel_lovelace": 1, "panel_home": 1},
        is_admin=False,
    )

    assert visible == {"home"}


def test_an_administrator_receives_everything():
    """Not one key is dropped from an administrator's panel list.

    This is what keeps the Permission Manager panel reachable when every other
    part of this integration has failed, so it holds even for the panels a
    non-admin is refused: the stub, and everything carrying no level.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home"),
        "config": panel(),
    }

    visible = visible_panel_ids(
        panel_ids=["lovelace", "home", "config"],
        panels=panels,
        user_permissions={},
        is_admin=True,
    )

    assert visible == {"lovelace", "home", "config"}


def test_profile_and_notfound_survive_without_a_permission():
    """The two panels kept for a reason other than a Permission.

    `profile` is every user's own account page and is no Resource; `notfound`
    is where Home Assistant's router falls back, and taking it away is what
    made the router throw. Neither carries a Permission level.
    """
    panels = {"profile": panel(), "notfound": panel(), "home": panel(component_name="home")}

    visible = visible_panel_ids(
        panel_ids=["profile", "notfound", "home"],
        panels=panels,
        user_permissions={},
        is_admin=False,
    )

    assert visible == {"profile", "notfound"}


def test_a_user_with_nothing_in_the_store_receives_only_those_two():
    """The degraded set, reached by an empty store as much as by a missing one."""
    panels = {"profile": panel(), "notfound": panel(), "home": panel(component_name="home")}

    for user_permissions in ({}, None):
        assert visible_panel_ids(
            panel_ids=["profile", "notfound", "home"],
            panels=panels,
            user_permissions=user_permissions,
            is_admin=False,
        ) == {"profile", "notfound"}


def test_only_a_level_above_closed_grants_a_panel():
    """Closed and absent say the same thing. Only View hands a panel over."""
    panels = {
        "granted": panel(component_name="granted"),
        "closed": panel(component_name="closed"),
        "unmentioned": panel(component_name="unmentioned"),
    }

    visible = visible_panel_ids(
        panel_ids=["granted", "closed", "unmentioned"],
        panels=panels,
        user_permissions={"panel_granted": 1, "panel_closed": 0},
        is_admin=False,
    )

    assert visible == {"granted"}


def test_a_permission_is_read_off_the_prefixed_resource_id():
    """The store is keyed by Resource id, and a bare panel id is not one.

    Reading `home` instead of `panel_home` would let an Area or Label that
    happens to be named like a panel answer a panel's question.
    """
    panels = {"home": panel(component_name="home")}

    visible = visible_panel_ids(
        panel_ids=["home"],
        panels=panels,
        user_permissions={"home": 1, "area_home": 1, "label_home": 1},
        is_admin=False,
    )

    assert visible == set()


def test_nothing_comes_back_that_was_not_offered():
    """The answer is a subset of the question.

    The caller decides which panels are on the table — the Panel Gate offers
    the panels Home Assistant computed for this user, which is already less
    than every panel registered. A View level on a panel that was not offered
    cannot add it back, and neither can being `profile`.
    """
    panels = {"home": panel(component_name="home"), "profile": panel()}

    visible = visible_panel_ids(
        panel_ids=["home"],
        panels=panels,
        user_permissions={"panel_home": 1, "panel_energy": 1},
        is_admin=False,
    )

    assert visible == {"home"}


def test_a_panel_offered_with_no_registry_entry_is_decided_by_its_permission():
    """A panel id with nothing to read a component name off is not the stub.

    Only the stub `lovelace` is unroutable, and that verdict needs the panel
    object. An id the caller offers that the panels mapping does not describe
    is an ordinary panel, so its Permission still governs it.
    """
    visible = visible_panel_ids(
        panel_ids=["home", "energy"],
        panels={},
        user_permissions={"panel_home": 1},
        is_admin=False,
    )

    assert visible == {"home"}


def test_a_real_dashboard_is_granted_like_any_other_panel():
    """Only the stub is refused. A `lovelace` panel with a config mode is real."""
    panels = {
        "lovelace": panel(component_name="lovelace", config={"mode": "storage"}),
        "dashboard-kitchen": panel(component_name="lovelace", config={"mode": "storage"}),
    }

    visible = visible_panel_ids(
        panel_ids=["lovelace", "dashboard-kitchen"],
        panels=panels,
        user_permissions={"panel_lovelace": 1, "panel_dashboard-kitchen": 1},
        is_admin=False,
    )

    assert visible == {"lovelace", "dashboard-kitchen"}


def test_a_fully_permitted_non_admin_receives_what_was_offered_and_their_own_page():
    """The two ends of the integration, asserted against each other.

    admin_panel_resources decides which panels an administrator may set a
    Permission level on; visible_panel_ids decides what a level is worth. Turn
    every toggle the Permission Manager panel offers to View, and what comes
    back is exactly those panels — the stub and Home Assistant's own
    administrator panels stay refused however hard the store is asked — plus
    the one panel that never carried a Permission level at all.
    """
    panels = {
        "lovelace": panel(component_name="lovelace", config=None),
        "home": panel(component_name="home"),
        "config": panel(),
        "developer-tools": panel(),
        "profile": panel(),
        "notfound": panel(),
        "energy": panel(component_name="energy", title="Energy"),
    }

    offered = {r["id"] for r in admin_panel_resources(panels)}
    user_permissions = {f"panel_{panel_id}": 1 for panel_id in offered}

    visible = visible_panel_ids(
        panel_ids=panels.keys(),
        panels=panels,
        user_permissions=user_permissions,
        is_admin=False,
    )

    assert visible == offered | {"profile"}
    assert "lovelace" not in visible
    assert visible.isdisjoint({"config", "developer-tools"})


# =============================================================================
# A dashboard Home Assistant no longer has (issue #8)
# =============================================================================


def test_a_dashboard_that_left_the_registry_names_its_resource():
    """A deleted dashboard is a url_path with no panel behind it.

    Home Assistant removes the panel before it fires `lovelace_updated`, so
    this is what a deletion looks like by the time the event is read. Nothing
    else in the payload says so — there is no action to read.
    """
    panels = {"home": panel(component_name="home"), "energy": panel()}

    assert deleted_dashboard_resource_id("dashboard-kitchen", panels) == (
        "panel_dashboard-kitchen"
    )


def test_a_saved_dashboard_keeps_its_permissions():
    """The same event fires on every save, and a save deletes nothing."""
    panels = {
        "home": panel(component_name="home"),
        "dashboard-kitchen": panel(component_name="lovelace"),
    }

    assert deleted_dashboard_resource_id("dashboard-kitchen", panels) is None


def test_the_default_dashboards_own_config_names_no_resource():
    """`url_path` is None for the default dashboard, whose panel never leaves.

    Saving or deleting the default dashboard's config fires this event with
    `url_path: None` — Home Assistant then serves the auto-generated
    dashboard from the same panel. No panel disappeared, so no row may.
    """
    panels = {"home": panel(component_name="home")}

    assert deleted_dashboard_resource_id(None, panels) is None
    assert deleted_dashboard_resource_id("", panels) is None


def test_an_unreadable_panel_registry_deletes_nothing():
    """The failure mode worth refusing: every save reading as a deletion.

    The registry is read off `hass.data`, and an empty answer means it could
    not be read rather than that Home Assistant has no panels. Guessing a
    deletion from it would erase every dashboard's Permissions on an
    ordinary save, so an unreadable registry decides nothing.
    """
    assert deleted_dashboard_resource_id("dashboard-kitchen", {}) is None
