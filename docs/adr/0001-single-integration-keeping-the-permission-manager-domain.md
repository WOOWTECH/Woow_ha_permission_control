# Single integration, keeping the `ha_permission_manager` domain

This repo shipped three Home Assistant integrations (`ha_permission_manager`,
`ha_area_control`, `ha_label_control`) where the latter two declared a hard
`dependencies` on the first and could not function without it. We merged them
into one integration and kept the domain `ha_permission_manager`, even though the
repo is named `Woow_ha_permission_control`.

## Considered Options

Renaming the domain to match the repo (`woow_permission_control`) was rejected.
The domain is not just a label: it is the `.storage` key holding every
permission, the namespace of all 14 services, and the identity of the existing
config entry. Renaming would have forced a storage migration, a service rename,
and every user to re-add the integration — buying nothing but a tidier name. The
display name in `manifest.json` carries the branding instead.
