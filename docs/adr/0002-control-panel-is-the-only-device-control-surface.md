# Control Panel is the only device-control surface

The merged integration ships exactly two panels: the admin-only Permission
Manager panel, and the Control Panel. The standalone Area Control and Label
Control panels — and their ~4000 lines of JS — were deleted rather than moved.

The Control Panel already existed inside `ha_permission_manager` and was written
to replace them; its `cp-*` components are the two old panels' components merged
under one prefix, with Areas and Labels as tabs.

## Consequences

An audit before deleting found Area at full parity and Label at a **net gain**:
the Label tab picks up the 15 domain-specific tiles, domain tabs, and search that
the standalone Label panel never had. The one thing lost is the standalone Label
panel's inline expandable sections (`LabelSection`) — labels are now cards you
open, identical to Areas. That uniformity is the point of the merge, and the
drill-in model degrades better when a label holds many entities.

The panel URLs `area-control` and `label-control` are simply gone. No redirect
shim was registered: bookmarks break once, whereas a shim would keep two phantom
panels alive in the sidebar logic forever.
