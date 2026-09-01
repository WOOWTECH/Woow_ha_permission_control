# Upstream request: a per-user hook for `get_panels`

**Status:** drafted 2026-08-31. Corrected, and checked against 2026.7.2,
on 2026-09-01 — and **not sent**. #28 was closed that day without posting
it, so nothing tracks sending it. What follows is a record of what we would
have asked for, not a plan.

**Where it goes:** a discussion in
[home-assistant/architecture](https://github.com/home-assistant/architecture/discussions/new),
category **General** — that repo's README asks for discussions, and its issue
tracker is closed with a pinned notice saying so.

**Why the text lives here:** ADR-0011 §8 says the Panel Gate is a bridge and
that we should ask for the real thing. This is the ask, kept in the repo, so the
bridge and the request to remove it sit next to each other. It was not
posted. If that is ever revisited, two things below have to be redone before it
goes anywhere: the search for an existing discussion upstream, and the check
that the handler quoted in “The one exit” still matches the Home Assistant the
reader is on. Both were true on 2026.7.2 and neither stays true by itself.

The text below is what gets posted, verbatim.

---

## A per-user hook for `get_panels`

### What we are doing, and would rather not

We maintain a custom integration that decides which panels a non-administrator
may see. Home Assistant offers one per-user dimension for that decision —
`require_admin`, which is two-valued and the same for every non-administrator —
so anything finer has to come from somewhere else.

We started in the browser: frontend modules added with `add_extra_js_url()` that
removed sidebar entries and covered denied pages. That approach is wrong in a
way the browser cannot fix. **The full panel map has already been delivered by
the time any of that code runs.** A module that fails to load, loads late, is
served stale from cache, or throws once leaves the user holding every panel, on
a page that looks entirely normal. We have four separate bug reports that are
all that one failure, and the server has no way of knowing it happened.

So we moved the decision to the one place the panel map leaves Home Assistant.
It works. We would like to stop doing it the way we currently do it.

### The one exit

`websocket_get_panels`, in `homeassistant/components/frontend/__init__.py`
(quoted from 2026.7.2):

```python
@callback
@websocket_api.websocket_command({"type": "get_panels"})
def websocket_get_panels(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Handle get panels command."""
    user_is_admin = connection.user.is_admin
    panels_config = hass.data[DATA_PANELS_CONFIG]
    panels: dict[str, PanelResponse] = {}
    for panel_key, panel in connection.hass.data[DATA_PANELS].items():
        config_override = panels_config.get(panel_key)
        require_admin = (
            config_override.get("require_admin", panel.require_admin)
            if config_override
            else panel.require_admin
        )
        if not user_is_admin and require_admin:
            continue
        panels[panel_key] = panel.to_response(config_override)

    connection.send_message(websocket_api.result_message(msg["id"], panels))
```

As far as we can find this is the only place a panel map reaches a browser:
nothing is embedded in the served HTML, and there is no REST equivalent. That is
what makes a server-side decision possible at all, and it is why we are asking
here rather than in the frontend repo.

### What we do instead, and why it should not be anybody's recommended technique

We replace the registered handler and swap `connection.send_message` for the
duration of one call, so Home Assistant computes its own answer and we delete
keys from the result before it is sent. We never add a key, and an
administrator's response is passed through untouched.

It works because of three things that are true today and are not API:

- `async_register_command` does `handlers[command] = (handler, schema)` with no
  check and no warning, and `ActiveConnection.__init__` takes
  `self.handlers = hass.data[websocket_api.DOMAIN]` as a reference rather than a
  copy — so replacing the handler reaches connections that already exist;
- `send_message` is in `ActiveConnection.__slots__`, and Home Assistant
  reassigns it itself in `async_handle_close()`;
- the handler entry is a 2-tuple whose first element can be called directly.

Our own code treats all three as load-bearing and checks them when it installs.
We refuse to wrap a handler that does not belong to
`homeassistant.components.frontend`, and we raise a persistent notification
whenever anything looks unfamiliar. But no amount of care on our side removes
the defect in the technique: **two integrations doing this cannot both be right,
and neither of them is told.** The second to register wins silently, and the
first one's users quietly receive an unfiltered list. Nothing declares
ownership, and nothing detects the collision.

### What we are asking for

One registration point at the exit above, with one rule: **a hook may remove
panels and may not add any.**

```python
# homeassistant/components/frontend/__init__.py

@callback
def async_register_panel_visibility(
    hass: HomeAssistant,
    hook: Callable[[User, set[str]], set[str]],
) -> CALLBACK_TYPE:
    """Register a filter over the panels a user receives.

    The hook is given the user asking and the panel keys Home Assistant has
    already computed for them. It returns the subset that user may receive;
    anything it adds is ignored. Returns a callable that unregisters it.
    """
```

and, in the handler, after the existing loop:

```python
    for hook in hass.data.get(DATA_PANEL_VISIBILITY, ()):
        allowed = hook(connection.user, set(panels))
        panels = {key: value for key, value in panels.items() if key in allowed}
```

The properties that matter to us, in order:

1. **The hook subtracts from Home Assistant's own answer.** It never computes a
   panel map of its own, so a later change to `to_response()`, to
   `config_override`, or to how `require_admin` is applied cannot silently make
   an integration wrong. This is the most valuable property of the wrap we
   already have, and the one we would most like to keep.
2. **More than one may register**, and each is visible in `hass.data`.
3. **A hook that raises is contained, and the failure is loud.** Our own answer
   to a decision we cannot make is to send the router fallback and the user's
   own profile page rather than the full list. Core's answer should be core's
   own — but it should not be "log it and serve everything" without saying so.
4. **Unregistering is supported**, because an integration gets unloaded. Ours
   restores the original handler on unload, deliberately: disabling the
   integration lifts every restriction it applied.

Refreshing costs nothing new. `panels_updated` already exists, is already in
`SUBSCRIBE_ALLOWLIST`, and the frontend's `subscribePanels` already re-runs
`get_panels` on it. We fire it from our own write paths today, and a page that
is already open updates with no reload. The hook needs no push channel of its
own.

### What we are not asking for

- **No permission model in core.** No storage, no UI, no notion of a group or a
  role. Who may see what stays entirely the integration's business; we are
  asking only for the place to say it.
- **Not a security boundary, and it should not be described as one.** A panel
  key that never reaches a browser is a great deal better than one hidden by
  JavaScript, but the websocket and REST APIs underneath are unchanged, and we
  say so plainly to our own users. The hook shapes what a user is offered. It
  authorises nothing.
- **No change to `require_admin`.** It stays exactly as it is. The hook runs
  after it and can only subtract further.

### Evidence

Measured on Home Assistant 2026.7.2, against a live instance, with a real
non-administrator account:

| | administrator | non-administrator |
|---|---|---|
| `get_panels`, nothing of ours filtering | 37 | 28 |
| `get_panels`, our filtering running | 37, not one key touched | 4 |
| a grant, on a page already open | — | `panels_updated`, refetch, panel appears |
| a revoke, on a page already open | — | `panels_updated`, refetch, panel goes |
| integration disabled, no restart | 35 | 27 |

All four counts come from one instance. The first two rows have our integration
installed, so the two panels it registers are counted with the rest — one of
them is visible to a non-administrator. The last row is that same instance with
the integration disabled, which deregisters both: 35 and 27 are Home Assistant's
own numbers, and 27 is what a stock non-administrator sees.

That 28 in the first row is the shape of the failure we started from — every
panel Home Assistant would give that user, and ours on top. When the
browser-side approach did not run, 28 is exactly what the user got, and nothing
anywhere recorded it.

Happy to write the PR if the shape is agreeable.
