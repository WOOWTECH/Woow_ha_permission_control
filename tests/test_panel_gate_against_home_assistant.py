"""The Panel Gate, driven against a real Home Assistant.

`tests/test_panel_gate.py` opens by saying "Home Assistant is not a dependency
of these tests", and for everything it holds that is right: wrapping, ordering,
and the pure decision are all decidable on their own. This file is the one
place in the repo where that stops being true.

The Gate's correctness **is defined by Home Assistant's internals**. It is a
handler read out of a shared dict, a `send_message` swapped on a slotted
object, and a response whose shape it has to recognise. A stub can be written
to agree with any of those, and one that has drifted makes the offline suite
agree with a Gate that does not work — which is exactly what happened once
already, when a stubbed `Debouncer.async_shutdown` was a coroutine, the tests
passed, and the entry never unloaded on the instance.

So here Home Assistant is installed and used: its own `websocket_get_panels`,
its own `ActiveConnection`, its own `Panel` objects and their `to_response`,
its own event bus and persistent notifications. What is *not* here is a running
instance — no config entries, no HTTP, no `async_start`. `hass` is constructed
and driven by hand, because the Gate never needs more of Home Assistant than
this and everything more is another thing that can be flaky in CI. The suites
that do point at a running instance are the `verify_issue_*.py` scripts, and
they erase whatever they point at.

**Two Home Assistants run this file in CI** (`.github/workflows/tests.yml`):

- the pinned one, on every push — the version this integration was verified
  against, so a change here is measured against a fixed Home Assistant;
- Home Assistant `dev`, on a schedule and unpinned — the only part of this repo
  that can say a Home Assistant release has broken the Gate *before* a user
  upgrades into it. #9 and #10 were both found the other way round, after a
  release had already broken them silently.

**A skip here is a pass, so CI is not allowed to take one.** Both guards
below — the stub check and the missing-install check — raise instead of
skipping when `PANEL_GATE_REQUIRES_HOME_ASSISTANT` is set, which both CI jobs
set. Without that, `pip install homeassistant` resolving to something that
cannot import leaves the job green with nothing run, which is the same failure
as not having the job. Skipping stays the right answer for a developer running
`pytest tests/`, and only there.

**This file cannot share a process with the offline suites.**
`tests/test_panel_gate.py` puts stub modules into `sys.modules` under the
`homeassistant.*` names at import time, and pytest imports every collected file
before running anything. Running `pytest tests/` therefore hands this file a
`homeassistant` package with no `frontend` in it. Rather than fight that, the
guard below notices the stubs and skips, and CI runs the two in separate jobs.
`test_panel_gate.py::test_the_home_assistant_suite_runs_in_a_job_of_its_own`
holds that separation, because a silent skip is how this suite would stop
running without anybody noticing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import types
from pathlib import Path

import pytest

COMPONENT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "ha_permission_manager"
)

# Set by both Home Assistant jobs in .github/workflows/tests.yml. Where it is
# set, there is no such thing as "Home Assistant is not available" — that is
# the job failing, not a suite that does not apply.
REQUIRED = "PANEL_GATE_REQUIRES_HOME_ASSISTANT"


def _cannot_run(reason: str) -> None:
    """Skip, unless the caller has said this suite has to run."""
    if os.environ.get(REQUIRED):
        raise RuntimeError(f"{REQUIRED} is set, and {reason}")
    pytest.skip(reason, allow_module_level=True)


# The stub check, before any Home Assistant import. A stub module is built with
# `types.ModuleType`, which has no `__file__`; the installed package has one.
_already_imported = sys.modules.get("homeassistant")
if _already_imported is not None and getattr(_already_imported, "__file__", None) is None:
    _cannot_run(
        "tests/test_panel_gate.py has stubbed homeassistant in this process. Run "
        "this file on its own: pytest tests/test_panel_gate_against_home_assistant.py"
    )

try:
    import homeassistant.components.frontend  # noqa: F401
except ImportError as error:  # pragma: no cover - the whole file is the cover
    _cannot_run(f"Home Assistant is not importable: {error}")

from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER  # noqa: E402
from homeassistant.auth.models import Group, User  # noqa: E402
from homeassistant.components import frontend, websocket_api  # noqa: E402
from homeassistant.components.persistent_notification import (  # noqa: E402
    SIGNAL_PERSISTENT_NOTIFICATIONS_UPDATED,
)
from homeassistant.components.websocket_api.connection import (  # noqa: E402
    ActiveConnection,
)
from homeassistant.core import HomeAssistant, callback  # noqa: E402
from homeassistant.helpers.dispatcher import async_dispatcher_connect  # noqa: E402

# The offline suites' trick, under a name of its own: a package whose
# `__path__` is the integration's directory resolves its relative imports
# without running its `__init__.py`, which sets up config entries, services and
# listeners this file has no use for.
_live_package = types.ModuleType("ha_permission_manager_live")
_live_package.__path__ = [str(COMPONENT)]
sys.modules.setdefault("ha_permission_manager_live", _live_package)

from ha_permission_manager_live import panel_gate  # noqa: E402
from ha_permission_manager_live.const import DOMAIN  # noqa: E402

# What a non-administrator receives when the Gate is running and cannot answer.
DEGRADED = {"notfound", "profile"}

# The id every request below carries. Home Assistant matches a response to a
# request by it, and so does the Gate — `_is_result` checks it — so it is named
# rather than sprinkled, and the one test that cares uses a different one on
# purpose.
MESSAGE_ID = 7


# =============================================================================
# One Home Assistant, built by hand
# =============================================================================


class HomeAssistantUnderTest:
    """A Home Assistant with panels, two users, and a way to ask for panels.

    Everything a test needs to drive `get_panels` the way a browser does, and
    nothing that needs Home Assistant to have been started. Deliberately not
    called an instance: in this repo that word means the running box at
    192.168.2.6 that the verify_issue_*.py scripts point at, and this is the
    opposite of one.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.panels_updated: list = []
        self.notifications: dict = {}

        admin_group = Group(
            id=GROUP_ID_ADMIN, name="Administrators", policy={}, system_generated=True
        )
        user_group = Group(
            id=GROUP_ID_USER, name="Users", policy={}, system_generated=True
        )
        self.administrator = User(
            name="An administrator",
            perm_lookup=None,
            is_active=True,
            groups=[admin_group],
        )
        self.non_administrator = User(
            name="A non-administrator",
            perm_lookup=None,
            is_active=True,
            groups=[user_group],
        )
        # Home Assistant's own answer to the question the Gate branches on, so
        # a change to how it decides is caught here rather than misread as a
        # filtering bug.
        assert self.administrator.is_admin and not self.non_administrator.is_admin

        @callback
        def _panels_updated(event) -> None:
            self.panels_updated.append(event)

        hass.bus.async_listen(panel_gate.EVENT_PANELS_UPDATED, _panels_updated)

        @callback
        def _notified(update_type, notifications) -> None:
            self.notifications.update(notifications)

        async_dispatcher_connect(
            hass, SIGNAL_PERSISTENT_NOTIFICATIONS_UPDATED, _notified
        )

    # -- what a browser does ------------------------------------------------

    def ask(self, user: User) -> list:
        """Ask `get_panels` as `user` would, through a real ActiveConnection.

        The connection is built the way Home Assistant builds one, so its
        `handlers` really is the dict read out of `hass.data["websocket_api"]`
        and its `send_message` really is the slotted attribute the Gate swaps.
        Those two are the whole mechanism, and they are the two things an
        offline fake cannot honestly assert.
        """
        sent: list = []
        # Bound once and held: `sent.append` is a fresh object on every
        # attribute read, so the identity check below needs the same one the
        # connection was handed.
        send = sent.append
        connection = ActiveConnection(
            logging.getLogger(__name__), self.hass, send, user, None, None
        )
        handler, _schema = connection.handlers[panel_gate.GET_PANELS]
        try:
            handler(self.hass, connection, {"id": MESSAGE_ID, "type": "get_panels"})
        finally:
            # Whatever happened, the connection must be sending for itself
            # again. One left filtering its own traffic would go on filtering
            # every later message on it, not just this answer.
            assert connection.send_message is send
        return sent

    def panels(self, user: User) -> dict:
        """The one `get_panels` result `user` receives."""
        sent = self.ask(user)
        assert len(sent) == 1, f"expected exactly one answer, got {sent}"
        return sent[0]["result"]

    # -- the Permission store, without a store -------------------------------

    def store_loaded(self, permissions: dict | None = None) -> None:
        """Say the Permission store is readable, and what it says.

        `permissions` is keyed by user id exactly as `hass.data[DOMAIN]` keeps
        it — the store's in-memory shape, which is all the Gate ever reads.
        """
        domain_data = self.hass.data.setdefault(DOMAIN, {})
        domain_data[panel_gate.DATA_PERMISSIONS] = permissions or {}
        panel_gate.async_panel_gate_store_loaded(self.hass)

    def grant(self, user: User, *panel_ids: str) -> None:
        """Give `user` a View level on each panel, and nobody anything else."""
        self.store_loaded({user.id: {f"panel_{panel_id}": 1 for panel_id in panel_ids}})


def _register_the_usual_panels(hass: HomeAssistant) -> None:
    """A panel registry in the shape #16 measured on 192.168.2.6.

    Small, but every kind the Gate has to tell apart is here: the two Home
    Assistant keeps for administrators, the real default dashboard, the stub
    `lovelace` that #17 is about, the router fallback, the account page, an
    ordinary grantable panel, and this integration's own two.
    """
    hass.data[frontend.DATA_PANELS_CONFIG] = {}
    register = frontend.async_register_built_in_panel

    register(hass, "config", require_admin=True)
    register(hass, "developer-tools", require_admin=True)
    # The default dashboard: a lovelace panel with a mode, so it is routable.
    register(hass, "lovelace", frontend_url_path="home", config={"mode": "storage"})
    # The stub lovelace panel Home Assistant keeps and never routes to. It has
    # no config at all, which is what `is_unroutable_panel` reads.
    register(hass, "lovelace")
    register(hass, "profile")
    register(hass, "custom", frontend_url_path="notfound")
    register(hass, "history")
    register(hass, "custom", frontend_url_path="ha_control_panel")
    register(
        hass, "custom", frontend_url_path="ha_permission_manager", require_admin=True
    )


@pytest.fixture(name="ha")
def ha_fixture():
    """A fresh Home Assistant per test, with `get_panels` registered.

    Constructed inside a loop because `HomeAssistant.__init__` reads the
    running one, then driven from the test's own thread — which is the same
    thread, so Home Assistant's `verify_event_loop_thread` is satisfied and
    `@callback` listeners run inline. Nothing here needs the loop to spin, and
    a suite that needs a loop spinning to observe an event is a suite that can
    hang in CI.
    """
    loop = asyncio.new_event_loop()
    try:

        async def _build() -> HomeAssistant:
            return HomeAssistant(str(Path(__file__).resolve().parent))

        hass = loop.run_until_complete(_build())
        _register_the_usual_panels(hass)
        websocket_api.async_register_command(hass, frontend.websocket_get_panels)
        yield HomeAssistantUnderTest(hass)
    finally:
        loop.close()


def _stand_in_for_home_assistants_handler(hass: HomeAssistant, behaviour) -> None:
    """Register `behaviour` where Home Assistant's own `get_panels` was.

    #21 asks for the degraded branches of #18 to be covered here, and says why
    they cannot be covered anywhere else: they cannot be forced on a live
    instance without breaking it on purpose. This is breaking it on purpose, as
    narrowly as it can be done — the handler the Gate wraps answers wrongly,
    and everything around it is still Home Assistant's: the registry the Gate
    reads it out of, the connection it is driven through, the `send_message` it
    swaps, and the panels the refusal is then built from.

    The module claim is set because that is what the Gate checks before it will
    wrap anything, and this stand-in is deliberately standing in for the
    handler it names.
    """
    behaviour.__module__ = panel_gate.FRONTEND_MODULE
    handlers = hass.data[websocket_api.const.DOMAIN]
    _original, schema = handlers[panel_gate.GET_PANELS]
    handlers[panel_gate.GET_PANELS] = (behaviour, schema)


# =============================================================================
# The takeover, against the handler that is actually registered
# =============================================================================


def test_home_assistant_hands_a_non_administrator_everything_before_we_install(ha):
    """The fail-open this whole layer exists to close, measured rather than
    quoted. #12 found a non-administrator holding 28 panels and a page that
    looked entirely normal; this is that, in miniature."""
    received = ha.panels(ha.non_administrator)

    assert set(received) == {
        "home",
        "lovelace",
        "profile",
        "notfound",
        "history",
        "ha_control_panel",
    }
    # Home Assistant's own per-user filter, and the only one it has.
    assert "config" not in received
    assert "developer-tools" not in received
    assert "ha_permission_manager" not in received


def test_installing_reaches_a_connection_that_already_exists(ha):
    """#16's central finding, and the one a stub cannot honestly assert:
    `ActiveConnection.__init__` takes `hass.data["websocket_api"]` as a
    reference, not a copy. If it were a copy, installing would do nothing for
    every browser already connected — which is every browser."""
    sent: list = []
    connection = ActiveConnection(
        logging.getLogger(__name__), ha.hass, sent.append, ha.non_administrator, None, None
    )
    assert connection.handlers is ha.hass.data[websocket_api.const.DOMAIN]

    assert panel_gate.async_install_panel_gate(ha.hass) is True
    ha.store_loaded()

    handler, _schema = connection.handlers[panel_gate.GET_PANELS]
    handler(ha.hass, connection, {"id": MESSAGE_ID, "type": "get_panels"})

    assert set(sent[0]["result"]) == DEGRADED


def test_installing_tells_every_browser_to_ask_again(ha):
    """A page that connected during startup is holding Home Assistant's own
    answer and has no reason to ask for another. `85d4977` caught exactly that
    in the act."""
    assert ha.panels_updated == []

    panel_gate.async_install_panel_gate(ha.hass)

    assert len(ha.panels_updated) == 1
    assert ha.panels_updated[0].event_type == "panels_updated"


def test_installing_twice_leaves_the_first_one_in_place(ha):
    """`async_setup` installs before any config entry exists and
    `async_setup_entry` installs again, because a disable/enable cycle never
    runs `async_setup` a second time. Whichever gets there first wins, and what
    is parked to restore is still Home Assistant's own handler."""
    panel_gate.async_install_panel_gate(ha.hass)
    installed, _schema = ha.hass.data[websocket_api.const.DOMAIN][panel_gate.GET_PANELS]

    assert panel_gate.async_install_panel_gate(ha.hass) is True

    again, _schema = ha.hass.data[websocket_api.const.DOMAIN][panel_gate.GET_PANELS]
    assert again is installed
    assert ha.hass.data[DOMAIN][panel_gate.DATA_GATE] is frontend.websocket_get_panels


def test_a_non_administrator_receives_only_what_they_were_granted(ha):
    """The whole point, through Home Assistant's own handler."""
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home", "ha_control_panel")

    assert set(ha.panels(ha.non_administrator)) == {
        "home",
        "ha_control_panel",
        "profile",
        "notfound",
    }


def test_an_administrator_receives_home_assistants_own_answer_untouched(ha):
    """Not one key. This is what keeps the Permission Manager panel reachable
    when everything else here has failed, so it is compared against the answer
    Home Assistant gave before the Gate was there — the whole message, not the
    key set."""
    before = ha.ask(ha.administrator)[0]

    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator)  # the administrator has no rows at all

    assert ha.ask(ha.administrator)[0] == before


def test_the_stub_lovelace_panel_is_refused_even_with_a_row(ha):
    """#17's first test, against real `Panel` objects rather than dicts.

    The spike's own rule honoured `panel_lovelace: 1` and handed the user a
    sidebar row Home Assistant bounces straight off. `is_unroutable_panel`
    reads `component_name` and `config` off whatever the registry holds, and
    here that is Home Assistant's `Panel` class — an object, not the mapping
    the offline suite passes it.
    """
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home", "lovelace")

    received = ha.panels(ha.non_administrator)

    assert "lovelace" not in received
    assert "home" in received


def test_a_grant_cannot_resurrect_a_panel_home_assistant_withheld(ha):
    """The answer is a subset of what Home Assistant offered, never more. A
    store row for an administrators-only panel is not a way in."""
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "config", "developer-tools", "ha_permission_manager")

    received = ha.panels(ha.non_administrator)

    assert "config" not in received
    assert "developer-tools" not in received
    assert "ha_permission_manager" not in received
    assert set(received) == DEGRADED


def test_home_assistants_own_panel_config_still_decides_require_admin(ha):
    """Wrap, do not reimplement — with the thing that would catch a
    reimplementation.

    Home Assistant lets `frontend_panels_config` override `require_admin` per
    panel, and computes the override itself inside `websocket_get_panels`. The
    Gate never looks at it. If it ever recomputed who may see what instead of
    deleting keys from Home Assistant's answer, this is the test that would
    fail — and on an instance it would be an administrator's deliberate
    lockdown quietly not applying.
    """
    ha.hass.data[frontend.DATA_PANELS_CONFIG]["history"] = {"require_admin": True}
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "history", "home")

    received = ha.panels(ha.non_administrator)

    assert "history" not in received
    assert "home" in received
    assert "history" in ha.panels(ha.administrator)


def test_restoring_gives_home_assistants_own_answer_back(ha):
    """Disabling this integration lifts every restriction — deliberately, and
    without a restart. It is the escape hatch the whole design leans on."""
    before = ha.ask(ha.non_administrator)[0]
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home")
    assert set(ha.panels(ha.non_administrator)) != set(before["result"])

    panel_gate.async_restore_panel_gate(ha.hass)

    assert ha.ask(ha.non_administrator)[0] == before
    handler, _schema = ha.hass.data[websocket_api.const.DOMAIN][panel_gate.GET_PANELS]
    assert handler is frontend.websocket_get_panels
    assert panel_gate.DATA_GATE not in ha.hass.data[DOMAIN]


def test_restoring_tells_every_browser_to_ask_again(ha):
    """Otherwise a page keeps the filtered list it was last handed, and
    disabling the integration looks like it did nothing."""
    panel_gate.async_install_panel_gate(ha.hass)
    ha.panels_updated.clear()

    panel_gate.async_restore_panel_gate(ha.hass)

    assert len(ha.panels_updated) == 1


def test_restoring_declines_when_somebody_registered_over_us(ha):
    """Putting the original back would delete theirs, which is the thing we
    complain about when it is done to us."""
    panel_gate.async_install_panel_gate(ha.hass)

    @callback
    def somebody_else(hass, connection, msg) -> None:
        connection.send_message(websocket_api.result_message(msg["id"], {}))

    handlers = ha.hass.data[websocket_api.const.DOMAIN]
    handlers[panel_gate.GET_PANELS] = (somebody_else, None)

    panel_gate.async_restore_panel_gate(ha.hass)

    handler, _schema = handlers[panel_gate.GET_PANELS]
    assert handler is somebody_else
    assert ha.notifications[panel_gate.NOTIFICATION_ID]["message"].startswith(
        "The `get_panels` WebSocket handler was replaced"
    )


# =============================================================================
# Refusing to install, which is the loud kind of failure
# =============================================================================


def test_we_will_not_wrap_a_handler_that_is_not_home_assistants(ha):
    """Someone else got there first, so we do not know what we are wrapping —
    and a second wrapper over a first is how a restore ends up deleting a
    handler that is still in use."""

    @callback
    def somebody_else(hass, connection, msg) -> None:
        connection.send_message(websocket_api.result_message(msg["id"], {}))

    handlers = ha.hass.data[websocket_api.const.DOMAIN]
    handlers[panel_gate.GET_PANELS] = (somebody_else, None)

    assert panel_gate.async_install_panel_gate(ha.hass) is False

    assert handlers[panel_gate.GET_PANELS][0] is somebody_else
    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "is already wrapping it" in message


def test_we_say_so_when_there_is_no_get_panels_at_all(ha):
    """Home Assistant then serves its own unfiltered list, which looks like a
    perfectly normal instance to everybody except the user who is supposed to
    be restricted."""
    del ha.hass.data[websocket_api.const.DOMAIN][panel_gate.GET_PANELS]

    assert panel_gate.async_install_panel_gate(ha.hass) is False

    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "no `get_panels` WebSocket handler" in message


def test_a_missing_router_fallback_is_reported_and_does_not_stop_us(ha):
    """#7 asked whether `notfound` is really registered, and nothing checked.
    The frontend could only assume; the backend can look — at Home Assistant's
    own registry, which is what makes this worth asserting here.

    Refusing to install would lift every restriction on the instance in order
    to protect one router fallback, which is the worse of the two failures by
    a distance."""
    ha.hass.data[frontend.DATA_PANELS].pop("notfound")

    assert panel_gate.async_install_panel_gate(ha.hass) is True

    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "['notfound']" in message


def test_an_empty_registry_at_install_time_is_asked_again_when_the_store_loads(ha):
    """On a cold start the Gate goes in before the registry is filled, and
    installing is idempotent — so without the second ask the check would simply
    never happen on such a boot, and #7 would be closed by a line that did not
    run."""
    registered = dict(ha.hass.data[frontend.DATA_PANELS])
    ha.hass.data[frontend.DATA_PANELS].clear()

    assert panel_gate.async_install_panel_gate(ha.hass) is True
    assert panel_gate.NOTIFICATION_ID not in ha.notifications

    ha.hass.data[frontend.DATA_PANELS].update(registered)
    ha.hass.data[frontend.DATA_PANELS].pop("notfound")
    ha.store_loaded()

    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "['notfound']" in message


# =============================================================================
# The degraded set: #18's other branch, which an instance cannot be made to
# take without breaking it on purpose
# =============================================================================


# The wrong answers, written once. Each is what one of `_is_result`'s
# conditions is for; the tests below say which, and what the user gets instead.


@callback
def answers_with_an_error(hass, connection, msg) -> None:
    """`success` is not True. The commonest wrong answer, and the only one of
    these Home Assistant itself could plausibly send."""
    connection.send_message(websocket_api.error_message(msg["id"], "boom", "no"))


@callback
def answers_a_string(hass, connection, msg) -> None:
    """Not a dict at all.

    `ActiveConnection.send_message` is typed `bytes | str | dict`, because Home
    Assistant coalesces and pre-serialises messages on connections that ask for
    it. So a `message` the Gate cannot index is not a hypothetical: it is the
    other half of a signature the Gate is sitting in the middle of.
    """
    connection.send_message('{"id": 7, "type": "result", "success": true}')


@callback
def answers_the_wrong_request(hass, connection, msg) -> None:
    """A result, well-formed, for somebody else's message id.

    Filtering it would hand this user an answer computed for another request,
    and `real_send` would put the wrong id on the wire either way.
    """
    connection.send_message(websocket_api.result_message(msg["id"] + 1, {}))


@callback
def answers_without_a_panel_map(hass, connection, msg) -> None:
    """A successful result whose `result` is not a mapping of panels."""
    connection.send_message(websocket_api.result_message(msg["id"], ["home"]))


@callback
def answers_nothing(hass, connection, msg) -> None:
    """No answer at all. The request would never get a reply."""
    return


@callback
def raises(hass, connection, msg) -> None:
    """A handler that falls over."""
    raise RuntimeError("get_panels fell over")


def _errors(caplog) -> list:
    """The error-level records the Gate wrote. #18 asks for a log line *and* a
    notification, so both are asserted rather than the notification alone."""
    return [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_before_the_store_is_loaded_a_non_administrator_is_refused(ha, caplog):
    """Between installing and the store being read we are running and cannot
    answer. The window is one file read; the alternative is the naked one."""
    caplog.set_level(logging.DEBUG)
    panel_gate.async_install_panel_gate(ha.hass)

    received = ha.panels(ha.non_administrator)

    assert set(received) == DEGRADED
    # Expected once per start and self-correcting, so it is a warning and no
    # notification. Every other way of reaching the degraded set is an error
    # and a notification, and the tests below hold that.
    assert panel_gate.NOTIFICATION_ID not in ha.notifications
    assert not _errors(caplog)
    assert [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "before the Permission store was loaded" in record.getMessage()
    ]


def test_the_degraded_set_is_built_from_home_assistants_own_panels(ha):
    """Not from a literal. If Home Assistant stops registering one of the two,
    the refusal is smaller rather than naming a panel that is not there — and
    the entries are whatever `Panel.to_response()` says they are, on whichever
    version is being tested."""
    panel_gate.async_install_panel_gate(ha.hass)

    received = ha.panels(ha.non_administrator)

    registry = ha.hass.data[frontend.DATA_PANELS]
    # `to_response()` is called here with no argument on purpose, even though
    # `_panel_response` hedges both arities — #16 read `panel.to_response(
    # config_override)` off the handler and the signature has since gained a
    # default. If Home Assistant ever makes the argument required again, this
    # line raises TypeError on the dev job, which is the dev job doing its
    # work: the hedge in the production code would still be carrying the
    # instance, and somebody would find out from CI rather than from a user.
    assert received == {
        panel_id: registry[panel_id].to_response() for panel_id in DEGRADED
    }


@pytest.mark.parametrize(
    "behaviour",
    [
        answers_with_an_error,
        answers_a_string,
        answers_the_wrong_request,
        answers_without_a_panel_map,
    ],
    ids=["an error", "not a dict", "another request's id", "no panel map"],
)
def test_an_unrecognised_answer_becomes_the_degraded_set(ha, caplog, behaviour):
    """`_is_result` asks four things of an answer, and every no is this.

    Passing one through is the one thing that must not happen. None of the four
    carries a panel map, so nothing would leak — but each leaves the browser
    with no route at all, and each means the Gate is watching something it does
    not understand. Both are worth saying out loud, which is why the log and
    the notification are asserted as well as what the user receives.
    """
    caplog.set_level(logging.DEBUG)
    _stand_in_for_home_assistants_handler(ha.hass, behaviour)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home", "history")

    assert set(ha.panels(ha.non_administrator)) == DEGRADED
    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "a shape the Panel Gate does not recognise" in message
    assert _errors(caplog)


def test_an_unrecognised_answer_still_reaches_an_administrator_untouched(ha):
    """`connection.user.is_admin` is readable before the answer is. That is
    what keeps an administrator's session working no matter what the response
    turns out to look like."""
    _stand_in_for_home_assistants_handler(ha.hass, answers_with_an_error)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.store_loaded()

    assert ha.ask(ha.administrator) == [
        websocket_api.error_message(MESSAGE_ID, "boom", "no")
    ]


def test_a_handler_that_sends_nothing_becomes_the_degraded_set(ha, caplog):
    """The request would otherwise never get a reply, and the page would sit on
    whatever it was last handed."""
    caplog.set_level(logging.DEBUG)
    _stand_in_for_home_assistants_handler(ha.hass, answers_nothing)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home")

    assert set(ha.panels(ha.non_administrator)) == DEGRADED
    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "sent nothing while the Panel Gate" in message
    assert _errors(caplog)


def test_a_handler_that_raises_becomes_the_degraded_set(ha, caplog):
    """A handler that raises must still close, rather than fail open or leave
    the connection filtering its own traffic."""
    caplog.set_level(logging.DEBUG)
    _stand_in_for_home_assistants_handler(ha.hass, raises)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home")

    assert set(ha.panels(ha.non_administrator)) == DEGRADED
    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "raised" in message
    # The traceback is the whole of what says *why*, and the notification does
    # not carry one — it says to go and read this.
    assert [record for record in _errors(caplog) if record.exc_info]


def test_a_handler_that_raises_still_raises_for_an_administrator(ha):
    """An administrator's answer is not wrapped at all, so there is nothing to
    be left holding if the original throws on the way out. Home Assistant's own
    error handling takes it from here, exactly as it would with no Gate."""
    _stand_in_for_home_assistants_handler(ha.hass, raises)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.store_loaded()

    with pytest.raises(RuntimeError):
        ha.ask(ha.administrator)


def test_a_decision_that_raises_becomes_the_degraded_set(ha, caplog, monkeypatch):
    """The decision failing must not fail open. This is the branch that would
    otherwise be reached only by a bug in `panel_policy`, on an instance, in
    front of a user."""

    def boom(**kwargs):
        raise ValueError("cannot decide")

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(panel_gate, "visible_panel_ids", boom)
    panel_gate.async_install_panel_gate(ha.hass)
    ha.grant(ha.non_administrator, "home", "history")

    assert set(ha.panels(ha.non_administrator)) == DEGRADED
    message = ha.notifications[panel_gate.NOTIFICATION_ID]["message"]
    assert "could not decide" in message
    assert [record for record in _errors(caplog) if record.exc_info]


def test_a_refusal_with_no_registry_to_build_it_from_is_still_an_answer(ha):
    """The last thing standing between a user and no answer at all. An
    exception thrown back through Home Assistant's own handler is a request
    that never gets a reply, so an unreadable registry yields an empty result
    instead."""
    panel_gate.async_install_panel_gate(ha.hass)
    ha.hass.data[frontend.DATA_PANELS].clear()

    sent = ha.ask(ha.non_administrator)

    assert sent[0]["success"] is True
    assert sent[0]["result"] == {}
