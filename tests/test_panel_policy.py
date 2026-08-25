"""Unit tests for panel_policy — the pure panel decisions, no Home Assistant needed.

Home Assistant is not a dependency of these tests. panel_policy holds the
decisions that both discovery and the WebSocket API make about panels, so they
are asserted here once instead of being observed in a live browser.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "ha_permission_manager"))

from panel_policy import admin_panel_resources, unroutable_panel_ids  # noqa: E402


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
