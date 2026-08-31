"""Unit tests for panel_gate — the Panel Gate's wrapping, offline.

Home Assistant is not a dependency of these tests. The Gate is a wrapper around
one Home Assistant handler, so what it has to get right is wrapping: take over
`get_panels` only when the handler on offer is the one we think it is, hand an
administrator's answer back untouched, drop keys from everybody else's, and
close rather than pass through when the answer is not what we expected.

None of that needs a real instance, and issue #16's spike is the reason not to
wait for one: its expectations were reached by reading, and the first live run
disagreed with them. What a live instance is still for is
`tests/verify_issue_16.py`.

Home Assistant is stubbed below rather than installed — the modules panel_gate
and discovery import, and nothing else. A stub that drifts from the real thing
would make these tests agree with a Gate that does not work, so each one is
deliberately trivial: an identity decorator, a dict builder, a recorder. The
thing that cannot be stubbed honestly — that `hass.data["websocket_api"]` really
is the dict every live connection reads its handlers out of — is #16's finding
and verify_issue_16.py's measurement, not this file's.
"""
import asyncio
import re
import sys
import types
from pathlib import Path

import pytest

COMPONENT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "ha_permission_manager"
)


# =============================================================================
# The Home Assistant stubs
# =============================================================================

NOTIFICATIONS: list[dict] = []


def _stub(name: str, is_package: bool = False, **attributes) -> types.ModuleType:
    """Register one stub module, reachable by `from ... import ...`."""
    module = types.ModuleType(name)
    if is_package:
        module.__path__ = []
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    sys.modules[name] = module
    parent, _, leaf = name.rpartition(".")
    if parent:
        setattr(sys.modules[parent], leaf, module)
    return module


def _result_message(iden, result):
    """Home Assistant's own result envelope, in the shape it sends it."""
    return {"id": iden, "type": "result", "success": True, "result": result}


def _async_create(hass, message, title=None, notification_id=None):
    NOTIFICATIONS.append(
        {"message": message, "title": title, "notification_id": notification_id}
    )


_stub("homeassistant", is_package=True)
_stub("homeassistant.core", callback=lambda func: func, HomeAssistant=object)
_stub("homeassistant.components", is_package=True)
_stub("homeassistant.components.persistent_notification", async_create=_async_create)
_stub("homeassistant.components.websocket_api", is_package=True)
_stub("homeassistant.components.websocket_api.const", DOMAIN="websocket_api")
_stub("homeassistant.components.websocket_api.messages", result_message=_result_message)
_stub("homeassistant.helpers", is_package=True)
_stub("homeassistant.helpers.area_registry", async_get=lambda hass: None)
_stub("homeassistant.helpers.label_registry", async_get=lambda hass: None)


class FakeDebouncer:
    """Home Assistant's Debouncer, recorded rather than reimplemented.

    Collapsing a burst on a timer is Home Assistant's job and is tested
    upstream; reimplementing it here would only prove the reimplementation
    right. What these tests hold is the wiring — that a Permission write goes
    through a debouncer rather than straight to the bus, that the whole
    integration shares one, that its cooldown matches the store's own
    batching, and that the function it would eventually run fires the event.

    Whether a burst actually collapses is measured on an instance, by
    tests/verify_issue_19.py.

    **The signatures below are copied, not guessed**, from
    `homeassistant/helpers/debounce.py` on HA 2026.7.2:

        def __init__(self, hass, logger, *, cooldown, immediate,
                     function=None, background=False)
        async def async_call(self) -> None          # a coroutine
        @callback
        def async_shutdown(self) -> None            # NOT a coroutine
        @callback
        def async_cancel(self) -> None              # NOT a coroutine

    That distinction is here because getting it wrong cost a deploy. This stub
    first had `async def async_shutdown`, the code under test awaited it, and
    these tests passed — because the stub had been written to agree with the
    assumption rather than with Home Assistant. On the instance it raised
    `TypeError: 'NoneType' object can't be awaited` out of
    `async_unload_entry`, so the entry never unloaded and disabling the
    integration silently did nothing. A stub is only worth what its fidelity
    is worth; check the real signature before adding a method here.
    """

    instances: list["FakeDebouncer"] = []

    def __init__(self, hass, logger, *, cooldown, immediate, function=None):
        self.hass = hass
        self.cooldown = cooldown
        self.immediate = immediate
        self.function = function
        self.calls = 0
        self.was_shut_down = False
        FakeDebouncer.instances.append(self)

    async def async_call(self):
        self.calls += 1

    def async_shutdown(self):
        # Sync, like the real one. See the docstring above.
        self.was_shut_down = True


_stub("homeassistant.helpers.debounce", Debouncer=FakeDebouncer)

# The same stand-in package tests/test_panel_policy.py uses: it resolves the
# integration's relative imports without running its __init__.py, which does
# import Home Assistant for real.
_offline_package = types.ModuleType("ha_permission_manager_offline")
_offline_package.__path__ = [str(COMPONENT)]
sys.modules.setdefault("ha_permission_manager_offline", _offline_package)

from ha_permission_manager_offline import panel_gate  # noqa: E402
from ha_permission_manager_offline.panel_gate import (  # noqa: E402
    DATA_FALLBACK_CHECKED,
    DATA_GATE,
    DATA_STORE_LOADED,
    EVENT_PANELS_UPDATED,
    GET_PANELS,
    PANELS_UPDATED_COOLDOWN,
    async_broadcast_panels_changed,
    async_install_panel_gate,
    async_panel_gate_store_loaded,
    async_restore_panel_gate,
    async_stop_panel_broadcasts,
)

DOMAIN = "ha_permission_manager"
WEBSOCKET_API = "websocket_api"
FRONTEND_MODULE = "homeassistant.components.frontend"


# =============================================================================
# The fakes: a hass with a data dict and a bus, and a connection that records
# =============================================================================


class FakeBus:
    def __init__(self):
        self.fired = []

    def async_fire(self, event_type, event_data=None):
        self.fired.append(event_type)


class FakeHass:
    def __init__(self, panels=None, handlers=None):
        self.data = {}
        self.bus = FakeBus()
        if panels is not None:
            self.data["frontend_panels"] = panels
        if handlers is not None:
            self.data[WEBSOCKET_API] = handlers


class FakeUser:
    def __init__(self, user_id, is_admin):
        self.id = user_id
        self.is_admin = is_admin


class FakeConnection:
    def __init__(self, user):
        self.user = user
        self.sent = []
        self.send_message = self._send

    def _send(self, message):
        self.sent.append(message)


def frontend_handler(result_for):
    """A stand-in for Home Assistant's own `websocket_get_panels`.

    `__module__` is what the Gate checks before taking a handler over, so the
    stand-in claims the module the real one lives in. A handler that does not
    is the "somebody else got there first" case, spelt by `foreign_handler`.
    """

    def websocket_get_panels(hass, connection, msg):
        connection.send_message(_result_message(msg["id"], result_for(connection)))

    websocket_get_panels.__module__ = FRONTEND_MODULE
    return websocket_get_panels


def foreign_handler(hass, connection, msg):
    """A `get_panels` somebody else already wrapped."""
    connection.send_message(_result_message(msg["id"], {}))


foreign_handler.__module__ = "some_other_integration.panel_gate"


# Home Assistant's own non-admin answer, as the panel registry holds it. Panel
# objects are dicts here because that is one of the two shapes panel_policy
# already reads, and the shape a get_panels result is made of.
PANELS = {
    "notfound": {"component_name": "custom", "title": None, "url_path": "notfound"},
    "profile": {"component_name": "profile", "title": None, "url_path": "profile"},
    "home": {"component_name": "lovelace", "config": {"mode": "storage"}, "title": "Home"},
    "energy": {"component_name": "energy", "title": "Energy"},
    "lovelace": {"component_name": "lovelace", "config": None, "title": None},
}

MSG = {"id": 7, "type": "get_panels"}


def make_hass(permissions=None, store_loaded=True, panels=None, handler=None):
    """A hass with the frontend's `get_panels` registered and our store loaded."""
    panels = PANELS if panels is None else panels
    if handler is None:
        handler = frontend_handler(lambda connection: dict(panels))
    hass = FakeHass(panels=panels, handlers={GET_PANELS: (handler, "schema")})
    hass.data[DOMAIN] = {"permissions": permissions or {}}
    if store_loaded:
        hass.data[DOMAIN][DATA_STORE_LOADED] = True
    return hass


def ask(hass, connection):
    """Run whatever handler is registered for `get_panels`, as a connection would."""
    handler, _schema = hass.data[WEBSOCKET_API][GET_PANELS]
    handler(hass, connection, MSG)


@pytest.fixture(autouse=True)
def _clear_notifications():
    NOTIFICATIONS.clear()
    FakeDebouncer.instances.clear()
    yield
    NOTIFICATIONS.clear()
    FakeDebouncer.instances.clear()


def run(coroutine):
    """Run one coroutine. There is no pytest-asyncio here, and none is needed:
    nothing under test awaits Home Assistant, only the debouncer stub."""
    return asyncio.run(coroutine)


# =============================================================================
# Installing
# =============================================================================


def test_install_takes_over_get_panels_and_says_so():
    """The handler is replaced in place, and every live browser told to re-ask.

    The event is the half that closes the window `85d4977` caught in the act: a
    browser that reconnected during startup read Home Assistant's full list and
    had no reason to ask again.
    """
    hass = make_hass()
    original, schema = hass.data[WEBSOCKET_API][GET_PANELS]

    assert async_install_panel_gate(hass) is True

    installed, kept_schema = hass.data[WEBSOCKET_API][GET_PANELS]
    assert installed is not original
    assert kept_schema is schema
    assert hass.bus.fired == [EVENT_PANELS_UPDATED]


def test_installing_twice_changes_nothing():
    """A reload is unload + setup, and setup installs from two places."""
    hass = make_hass()

    async_install_panel_gate(hass)
    gated, _schema = hass.data[WEBSOCKET_API][GET_PANELS]
    hass.bus.fired.clear()

    assert async_install_panel_gate(hass) is True
    assert hass.data[WEBSOCKET_API][GET_PANELS][0] is gated
    assert hass.bus.fired == []


def test_no_get_panels_handler_is_an_error_and_a_notification():
    """Not being in control is the one thing that must never be a debug line.

    Home Assistant then serves its own list and every restriction is off, which
    looks exactly like a working instance to whoever is not the restricted user.
    """
    hass = FakeHass(panels=PANELS, handlers={})

    assert async_install_panel_gate(hass) is False
    assert hass.data[WEBSOCKET_API] == {}
    assert len(NOTIFICATIONS) == 1
    assert hass.bus.fired == []


def test_a_handler_that_is_not_home_assistants_is_left_alone():
    """Somebody else got there first. Wrapping them would hide both of us."""
    hass = make_hass(handler=foreign_handler)

    assert async_install_panel_gate(hass) is False
    assert hass.data[WEBSOCKET_API][GET_PANELS][0] is foreign_handler
    assert len(NOTIFICATIONS) == 1


def test_a_missing_notfound_panel_is_reported_and_the_gate_still_installs():
    """Issue #7's "nothing checks", answered where the registry is readable.

    `notfound` is kept without a Permission because Home Assistant's
    default-panel lookup falls through to it. If it is not registered, that
    reasoning is void — but a Gate that refused to install over it would lift
    every restriction to protect one router fallback.
    """
    panels = {key: value for key, value in PANELS.items() if key != "notfound"}
    hass = make_hass(panels=panels)

    assert async_install_panel_gate(hass) is True
    assert len(NOTIFICATIONS) == 1
    assert "notfound" in NOTIFICATIONS[0]["message"]


def test_an_empty_registry_at_install_leaves_the_router_check_unanswered():
    """A cold start puts the Gate in before the panel registry is filled.

    Reporting "no panels" then would be an error notification about startup
    ordering. Installing is idempotent, so nothing would ever ask again — the
    check would be a line that never ran, and #7 would be closed by it.
    """
    hass = make_hass(panels={})

    assert async_install_panel_gate(hass) is True
    assert NOTIFICATIONS == []
    assert hass.data[DOMAIN].get(DATA_FALLBACK_CHECKED) is None


def test_the_router_check_is_asked_again_once_the_store_loads():
    """And by then an empty registry is an answer, not an ordering artefact."""
    hass = make_hass(panels={}, store_loaded=False)
    async_install_panel_gate(hass)

    async_panel_gate_store_loaded(hass)

    assert len(NOTIFICATIONS) == 1
    assert "notfound" in NOTIFICATIONS[0]["message"]


def test_the_router_check_is_not_asked_twice_when_it_already_answered():
    """The ordinary boot says nothing, once."""
    hass = make_hass(store_loaded=False)
    async_install_panel_gate(hass)

    async_panel_gate_store_loaded(hass)

    assert hass.data[DOMAIN][DATA_FALLBACK_CHECKED] is True
    assert NOTIFICATIONS == []


def test_an_installed_gate_leaves_a_record():
    hass = make_hass()

    assert hass.data[DOMAIN].get(DATA_GATE) is None
    async_install_panel_gate(hass)
    assert hass.data[DOMAIN][DATA_GATE] is not None


# =============================================================================
# An administrator
# =============================================================================


def test_an_administrator_receives_the_original_answer_untouched():
    """Not one key. This is what keeps the Permission Manager panel reachable."""
    hass = make_hass(permissions={})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("admin-id", is_admin=True))

    ask(hass, connection)

    assert connection.sent == [_result_message(7, dict(PANELS))]
    assert NOTIFICATIONS == []


def test_an_administrators_connection_is_never_watched():
    """send_message is not swapped at all for an administrator, so there is
    nothing to leave swapped if the original throws on the way out."""
    hass = make_hass()
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("admin-id", is_admin=True))
    before = connection.send_message

    ask(hass, connection)

    assert connection.send_message is before


# =============================================================================
# A non-administrator
# =============================================================================


def test_a_denied_panel_never_reaches_the_browser():
    """The whole point: absent, not hidden. No route is left for a bookmark."""
    hass = make_hass(permissions={"user-id": {"panel_energy": 1}})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    (message,) = connection.sent
    assert set(message["result"]) == {"energy", "notfound", "profile"}
    assert message["id"] == 7
    assert message["type"] == "result"
    assert message["success"] is True


def test_the_panels_that_survive_are_home_assistants_own_objects():
    """Wrap, do not reimplement: keys are dropped and nothing else is touched."""
    hass = make_hass(permissions={"user-id": {"panel_energy": 1}})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert connection.sent[0]["result"]["energy"] is PANELS["energy"]


def test_a_level_on_a_panel_home_assistant_never_routes_to_is_refused():
    """The surprise of #16's first spike run, at the Gate this time.

    The store holds `panel_lovelace: 1` from before discovery stopped offering
    it. panel_policy refuses it, so the Gate does too, and the report and the
    decision cannot part company.
    """
    hass = make_hass(permissions={"user-id": {"panel_lovelace": 1, "panel_energy": 1}})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert "lovelace" not in connection.sent[0]["result"]


def test_the_connections_send_message_is_put_back():
    """The swap lasts one call. A connection left holding it would filter every
    later message on that socket, `get_states` included."""
    hass = make_hass(permissions={"user-id": {}})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))
    before = connection.send_message

    ask(hass, connection)

    assert connection.send_message is before


# =============================================================================
# Closing when we cannot answer
# =============================================================================

DEGRADED = {"notfound", "profile"}


def test_a_non_admin_is_denied_before_the_store_is_loaded():
    """We are installed and running, and cannot answer. That is a refusal.

    The window is one file read at startup. The alternative is the naked
    window: a browser reconnecting mid-startup reading the full list.
    """
    hass = make_hass(permissions={"user-id": {"panel_energy": 1}}, store_loaded=False)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    # Expected, and transient. A notification per restart would be noise.
    assert NOTIFICATIONS == []


def test_the_window_closes_when_the_store_arrives():
    """Whoever was refused during startup has to be told to ask again."""
    hass = make_hass(store_loaded=False)
    async_install_panel_gate(hass)
    hass.bus.fired.clear()

    async_panel_gate_store_loaded(hass)

    assert hass.data[DOMAIN][DATA_STORE_LOADED] is True
    assert hass.bus.fired == [EVENT_PANELS_UPDATED]


def test_an_unrecognised_response_degrades_rather_than_passing_through():
    """An answer we cannot read is an answer we cannot filter."""

    def sends_something_else(hass, connection, msg):
        connection.send_message("a string, not a result")

    sends_something_else.__module__ = FRONTEND_MODULE
    hass = make_hass(
        permissions={"user-id": {"panel_energy": 1}}, handler=sends_something_else
    )
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    assert len(NOTIFICATIONS) == 1


def test_an_error_response_degrades_too():
    """An error carries no panel map, so nothing leaks either way — but the
    browser still needs a routable answer, and we still need telling."""

    def sends_an_error(hass, connection, msg):
        connection.send_message(
            {"id": msg["id"], "type": "result", "success": False, "error": {}}
        )

    sends_an_error.__module__ = FRONTEND_MODULE
    hass = make_hass(handler=sends_an_error)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    assert len(NOTIFICATIONS) == 1


def test_a_handler_that_sends_nothing_degrades():
    """Nothing arrived while we were watching, so nothing is going to."""

    def sends_nothing(hass, connection, msg):
        return

    sends_nothing.__module__ = FRONTEND_MODULE
    hass = make_hass(handler=sends_nothing)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    assert len(NOTIFICATIONS) == 1


def test_a_handler_that_raises_degrades():
    """Home Assistant would answer `unknown_error` and the sidebar would have
    no route at all. A refusal that still routes is the better failure."""

    def raises(hass, connection, msg):
        raise RuntimeError("boom")

    raises.__module__ = FRONTEND_MODULE
    hass = make_hass(handler=raises)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    assert len(NOTIFICATIONS) == 1


def test_filtering_that_raises_degrades(monkeypatch):
    """The decision itself failing is the case that must not fail open."""

    def explode(**kwargs):
        raise ValueError("the decision broke")

    monkeypatch.setattr(panel_gate, "visible_panel_ids", explode)
    hass = make_hass(permissions={"user-id": {"panel_energy": 1}})
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == DEGRADED
    assert len(NOTIFICATIONS) == 1


def test_an_administrator_is_passed_through_however_broken_the_answer_is():
    """`connection.user.is_admin` is readable no matter what the response looks
    like, so the administrator's escape hatch does not depend on the answer."""

    def sends_something_else(hass, connection, msg):
        connection.send_message("a string, not a result")

    sends_something_else.__module__ = FRONTEND_MODULE
    hass = make_hass(handler=sends_something_else)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("admin-id", is_admin=True))

    ask(hass, connection)

    assert connection.sent == ["a string, not a result"]
    assert NOTIFICATIONS == []


def test_the_degraded_set_is_built_from_the_panel_registry():
    """Not from a literal. If Home Assistant stops registering one of them, the
    degraded answer says so by being smaller, rather than naming a panel that
    is not there."""
    panels = {key: value for key, value in PANELS.items() if key != "profile"}
    hass = make_hass(panels=panels, store_loaded=False)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == {"notfound"}


def test_a_registry_that_cannot_be_read_still_gets_an_answer():
    """The last thing between a user and silence, so it cannot raise.

    An exception here would go back out through Home Assistant's own handler
    and leave the request with no reply at all, which is worse than every other
    failure in this section: the browser waits rather than routing.
    """
    hass = make_hass(
        panels=["not", "a", "mapping"],
        store_loaded=False,
        handler=frontend_handler(lambda connection: dict(PANELS)),
    )
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert connection.sent[0]["result"] == {}


# =============================================================================
# Telling every browser a Permission changed (issue #19)
# =============================================================================


def test_a_permission_write_tells_every_browser_to_ask_again():
    """The only channel that reaches the user a revocation is about.

    Home Assistant refuses a non-administrator's subscription to the Permission
    store's own announcement (#13). `panels_updated` is in its
    SUBSCRIBE_ALLOWLIST, so it is the one event that gets through — and with
    the Gate deciding, re-running `get_panels` is the whole of what a page has
    to do about a Permission change.
    """
    hass = make_hass()
    async_install_panel_gate(hass)
    hass.bus.fired.clear()

    run(async_broadcast_panels_changed(hass))

    (debouncer,) = FakeDebouncer.instances
    assert debouncer.calls == 1
    # Not fired yet — the debouncer owns when. What it will run is the fire.
    assert hass.bus.fired == []
    run(debouncer.function())
    assert hass.bus.fired == [EVENT_PANELS_UPDATED]


def test_a_burst_of_writes_shares_one_debouncer():
    """Otherwise each write would build its own and none would collapse.

    The case #19 names is `bulk_set_permissions`, which ADR-0010 already made
    one write rather than one per row. The case it does not name is the one
    left: several service calls in quick succession, and the registry
    listeners, which reach the store once per deleted area or label.
    """
    hass = make_hass()
    async_install_panel_gate(hass)

    for _ in range(5):
        run(async_broadcast_panels_changed(hass))

    assert len(FakeDebouncer.instances) == 1
    assert FakeDebouncer.instances[0].calls == 5


def test_the_first_write_is_not_delayed():
    """A grant should reach an open page now, not in a second's time. The
    cooldown is there to collapse what follows, not to hold the first one up."""
    hass = make_hass()
    run(async_broadcast_panels_changed(hass))

    assert FakeDebouncer.instances[0].immediate is True


def test_the_cooldown_matches_the_permission_stores_own_batching():
    """One second, because #19 asked the two to match — a tripwire, not a law.

    They are not causally linked. The Gate answers from the in-memory map,
    which `_async_write` has already mutated before it broadcasts, and
    `async_delay_save` delays only the write to disk that nothing reads until a
    restart. So there is no stale-rows window for this to protect, and if there
    were, the leading edge would already be inside it.

    The test is here so that retuning the save delay is a decision about the
    debounce too, rather than an accident. If you are reading it because it
    failed: the two are allowed to differ, but say so on purpose.
    """
    delays = re.findall(
        r"async_delay_save\([^,]+,\s*([0-9.]+)\)", init_source()
    )

    assert delays == ["1.0"]
    assert PANELS_UPDATED_COOLDOWN == float(delays[0])


def test_the_debouncer_is_shut_down_and_forgotten():
    """A pending broadcast must not outlive the integration that scheduled it."""
    hass = make_hass()
    run(async_broadcast_panels_changed(hass))
    debouncer = FakeDebouncer.instances[0]

    async_stop_panel_broadcasts(hass)

    assert debouncer.was_shut_down is True
    # And the next write builds a fresh one rather than calling a dead one.
    run(async_broadcast_panels_changed(hass))
    assert len(FakeDebouncer.instances) == 2


def test_shutting_down_without_ever_having_written_is_harmless():
    hass = make_hass()

    async_stop_panel_broadcasts(hass)

    assert FakeDebouncer.instances == []


def test_stopping_broadcasts_is_not_a_coroutine():
    """`Debouncer.async_shutdown` is a `@callback`, so this is too.

    Awaiting it raises out of `async_unload_entry`, and an unload that raises
    means the entry stays loaded — the Gate stays installed and disabling the
    integration does nothing. Measured that way on the instance before this
    test existed, which is why it does.
    """
    assert not asyncio.iscoroutinefunction(async_stop_panel_broadcasts)
    assert "await async_stop_panel_broadcasts" not in init_source()


# =============================================================================
# Handing back
# =============================================================================


def test_restore_puts_home_assistants_own_handler_back_and_says_so():
    """Disabling this integration lifts every restriction, immediately."""
    hass = make_hass()
    original, schema = hass.data[WEBSOCKET_API][GET_PANELS]
    async_install_panel_gate(hass)
    hass.bus.fired.clear()

    async_restore_panel_gate(hass)

    assert hass.data[WEBSOCKET_API][GET_PANELS] == (original, schema)
    assert hass.bus.fired == [EVENT_PANELS_UPDATED]
    assert hass.data[DOMAIN].get(DATA_GATE) is None


def test_restoring_a_gate_that_was_never_installed_does_nothing():
    hass = make_hass()
    original = hass.data[WEBSOCKET_API][GET_PANELS]

    async_restore_panel_gate(hass)

    assert hass.data[WEBSOCKET_API][GET_PANELS] is original
    assert hass.bus.fired == []


def test_restore_leaves_a_handler_somebody_else_installed_after_us():
    """Putting the original back over a third party's wrapper would delete
    theirs. Whoever is on top when we leave stays on top."""
    hass = make_hass()
    async_install_panel_gate(hass)
    hass.data[WEBSOCKET_API][GET_PANELS] = (foreign_handler, "schema")
    hass.bus.fired.clear()

    async_restore_panel_gate(hass)

    assert hass.data[WEBSOCKET_API][GET_PANELS][0] is foreign_handler
    assert len(NOTIFICATIONS) == 1
    # And the original is still held. Discarding it on the way to declining
    # would leave a wrapper installed with nothing left that knows what it
    # wraps — the one state from which there is no way back but a restart.
    assert hass.data[DOMAIN][DATA_GATE] is not None


def test_restore_keeps_the_original_when_there_is_no_registry_to_put_it_in():
    hass = make_hass()
    async_install_panel_gate(hass)
    original = hass.data[DOMAIN][DATA_GATE]
    del hass.data[WEBSOCKET_API]

    async_restore_panel_gate(hass)

    assert hass.data[DOMAIN][DATA_GATE] is original


def test_a_reinstall_after_a_restore_gates_again():
    """Re-enabling the integration filters again, with no restart."""
    hass = make_hass(permissions={"user-id": {"panel_energy": 1}})
    async_install_panel_gate(hass)
    async_restore_panel_gate(hass)
    async_install_panel_gate(hass)
    connection = FakeConnection(FakeUser("user-id", is_admin=False))

    ask(hass, connection)

    assert set(connection.sent[0]["result"]) == {"energy", "notfound", "profile"}


# =============================================================================
# Source-text invariants
#
# Where the Gate is installed from is the whole of its startup guarantee, and
# it cannot be run offline. Held here as source text, in the idiom
# tests/test_permission_store.py established. Each was checked by breaking it.
# =============================================================================


def init_source():
    return (COMPONENT / "__init__.py").read_text(encoding="utf-8")


def init_section(start: str, end: str | None = None) -> str:
    source = init_source()
    begin = source.index(start)
    return source[begin:source.index(end)] if end else source[begin:]


def test_the_gate_is_installed_before_the_config_entry():
    """`async_setup` runs before any entry, and before any browser can ask.

    Installing only from `async_setup_entry` would leave the store read, the
    services registered and the panels registered ahead of the Gate — and a
    browser reconnecting through any of that reading the full list.
    """
    setup = init_section("async def async_setup(", "async def async_setup_entry(")

    assert "async_install_panel_gate(hass)" in setup


def test_the_gate_is_reinstalled_when_an_entry_is_set_up_again():
    """`async_setup` runs once per Home Assistant lifetime. A disable/enable
    cycle goes through `async_setup_entry` alone, so that installs too — and
    ahead of the store read, so the deny-before-loaded window is the same one."""
    setup_entry = init_section(
        "async def async_setup_entry(", "async def async_unload_entry("
    )

    assert "async_install_panel_gate(hass)" in setup_entry
    assert setup_entry.index("async_install_panel_gate(hass)") < setup_entry.index(
        "await store.async_load()"
    )


def test_the_store_is_declared_loaded_only_after_it_is_loaded():
    setup_entry = init_section(
        "async def async_setup_entry(", "async def async_unload_entry("
    )

    assert setup_entry.index("await store.async_load()") < setup_entry.index(
        "async_panel_gate_store_loaded(hass)"
    )


def test_the_broadcasts_are_stopped_before_our_data_is_thrown_away():
    """The debouncer is held in `hass.data[DOMAIN]`, which unload pops.

    Swap these two and the shutdown silently finds nothing, and a broadcast
    scheduled a moment before the unload goes out a second after it — telling
    every browser to re-read a panel list that nothing changed again.
    """
    unload = init_section("async def async_unload_entry(")

    assert unload.index("async_stop_panel_broadcasts(hass)") < unload.index(
        "hass.data.pop(DOMAIN"
    )


def test_the_broadcasts_are_stopped_before_the_gate_hands_back():
    """Restoring fires `panels_updated` itself, immediately and on purpose. A
    debounced one landing a second later would be a second, pointless one."""
    unload = init_section("async def async_unload_entry(")

    assert unload.index("async_stop_panel_broadcasts(hass)") < unload.index(
        "async_restore_panel_gate(hass)"
    )


def test_the_gate_is_restored_before_our_data_is_thrown_away():
    """The record of what to put back lives in `hass.data[DOMAIN]`."""
    unload = init_section("async def async_unload_entry(")

    assert unload.index("async_restore_panel_gate(hass)") < unload.index(
        "hass.data.pop(DOMAIN"
    )


def test_panels_updated_is_spelt_once():
    """One spelling across the integration's Python: the Gate owns the event."""
    spelt_in = sorted(
        path.relative_to(COMPONENT).as_posix()
        for path in COMPONENT.rglob("*.py")
        if '"panels_updated"' in path.read_text(encoding="utf-8")
    )

    assert spelt_in == ["panel_gate.py"]
    assert EVENT_PANELS_UPDATED == "panels_updated"


def test_one_module_reaches_into_the_websocket_handler_registry():
    """So there is one place to look when Home Assistant changes how it keeps
    them, and one place a takeover can be added from."""
    reaches = sorted(
        path.relative_to(COMPONENT).as_posix()
        for path in COMPONENT.rglob("*.py")
        if re.search(
            r"websocket_api\.const|GET_PANELS", path.read_text(encoding="utf-8")
        )
    )

    assert reaches == ["panel_gate.py"]


def test_the_home_assistant_suite_runs_in_a_job_of_its_own():
    """This file's stubs and that file's Home Assistant cannot share a process.

    Everything above stubs the `homeassistant.*` modules into `sys.modules` at
    import time, and pytest imports every collected file before it runs
    anything. So a job that runs this file and
    tests/test_panel_gate_against_home_assistant.py together hands the second
    one a `homeassistant` package with no `frontend` in it. That file notices
    and skips rather than failing — which is the right thing for a developer
    running `pytest tests/`, and exactly the wrong thing for CI, where a suite
    that quietly stops running is a suite that stops finding anything.

    This is the tripwire on that: the two are named in different jobs, or this
    fails.
    """
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "tests.yml"
    ).read_text(encoding="utf-8")

    # Everything below `jobs:`, where the job keys really are the only
    # two-space-indented ones — `on:` has children at that indent too, and
    # splitting the whole file would read `push:` as a job.
    jobs_section = workflow.split("\njobs:\n", 1)[1]
    blocks = re.split(r"^  (?=[\w-]+:$)", jobs_section, flags=re.MULTILINE)[1:]
    # Whole paths, never substrings: "tests/test_panel_gate.py" is a substring
    # of the other name.
    suites = {
        block.split(":", 1)[0]: set(re.findall(r"tests/\S+\.py", block))
        for block in blocks
    }

    stubbed = "tests/test_panel_gate.py"
    against_home_assistant = "tests/test_panel_gate_against_home_assistant.py"

    runs_stubbed = {job for job, files in suites.items() if stubbed in files}
    runs_real = {job for job, files in suites.items() if against_home_assistant in files}

    assert runs_stubbed, f"no job runs {stubbed}"
    assert runs_real, f"no job runs {against_home_assistant}"
    assert not runs_stubbed & runs_real, (
        f"{sorted(runs_stubbed & runs_real)} runs both suites in one process, so "
        f"{against_home_assistant} will skip and the job will pass anyway"
    )
