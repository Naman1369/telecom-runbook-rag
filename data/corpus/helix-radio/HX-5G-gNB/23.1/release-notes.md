---
title: HX-5G Software 23.1 Release Notes
doc_type: release_notes
url: https://support.helix-radio.example/hx5g/23.1/release-notes
---

# HX-5G gNodeB Software 23.1 Release Notes

## Upgrade

- Minimum source release: 22.3.4. Earlier 22.3 builds must be upgraded to 22.3.4 first.
- Activation restarts the node (about 6 minutes of site outage).
- CLI scripts written for 22.3 must be migrated — see the command mapping below.

## CLI command mapping

| Task | 22.3 | 23.1 |
| --- | --- | --- |
| List cells | `hxcli cell show --all` | `hxcli nr-cell list` |
| Lock cell | `hxcli cell lock --cell-id 3` | `hxcli nr-cell set-admin-state 3 locked` |
| Unlock cell | `hxcli cell unlock --cell-id 3` | `hxcli nr-cell set-admin-state 3 unlocked` |
| Output power | `hxcli cell set --cell-id 3 --power 40` | `hxcli nr-cell set-power 3 40` |
| Sync status | `hxcli ptp show` / `hxcli gnss show` | `hxcli sync status` |
| NG-C status | `hxcli sctp show` | `hxcli transport ng-c status` |
| NG-C reset | `hxcli sctp reset --assoc 1` | `hxcli transport ng-c reset --amf 1` |
| Radio unit | `hxcli rru show` | `hxcli ru status` |

## New features

- 24-hour sync holdover on hardware revision C (OCXO).
- Per-cell software restart (`hxcli nr-cell restart <id>`) without a node restart.
- Built-in VSWR test (`hxcli ru vswr-test`).
- Alarm correlation with root-cause marking.
- AMF pooling on NG-C.

## Alarm changes

- `HX-RRU-VSWR-HIGH` renamed to `HX-RU-VSWR-HIGH`.
- New alarm `HX-SYNC-HOLDOVER` raised when the node enters holdover (before `HX-SYNC-LOSS`).

## Known issues

- **HX-23-117** — after `hxcli nr-cell restart`, the cell may report `enabled` while the carrier
  is still muted for up to 90 seconds. Wait 2 minutes before declaring recovery.
- **HX-23-131** — `hxcli sync status` shows remaining holdover as 0 on revision A/B hardware.
  Cosmetic; use the 4-hour rule for those revisions.
