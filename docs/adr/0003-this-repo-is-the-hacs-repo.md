# This repo is the HACS repo

The repo is laid out as a standard HACS integration —
`custom_components/ha_permission_manager/` plus a root `hacs.json` — and users add
`WOOWTECH/Woow_ha_permission_control` directly as a custom repository.

`hacs-dist.json` and `.github/workflows/hacs-dist-sync.yml`, which mirrored each
integration into its own Dist repo, are deleted. They existed solely to satisfy
HACS's one-integration-per-repo rule; with one integration that rule is satisfied
by construction, and the mirror was a failure point plus a standing "do not edit
this repo" hazard.

## Consequences

The three Dist repos get a final commit explaining the deprecation and are then
archived, not deleted — a reader who already added one deserves a readable notice
rather than a 404.

One trap follows from ADR-0001: because the domain is unchanged, anyone still
holding `WOOWTECH/hacs-ha_permission_manager` as a custom repository will keep
being served the old version by HACS. Removing the old custom repository is a
required manual step and must be stated in the deprecation notice and the
CHANGELOG.
