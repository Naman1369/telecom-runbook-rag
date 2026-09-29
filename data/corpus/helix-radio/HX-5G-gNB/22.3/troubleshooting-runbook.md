---
title: HX-5G gNodeB Troubleshooting Runbook
doc_type: runbook
url: https://support.helix-radio.example/hx5g/22.3/runbook
---

# HX-5G gNodeB Troubleshooting Runbook — Software 22.3

Applies to HX-5G gNodeB baseband units running software release 22.3.x. Log in to the
baseband with `hxcli` from the OSS jump host.

## RN-201 NR cell down

**Symptoms:** alarm `HX-CELL-UNAVAILABLE`, no UEs attached on the cell, KPI dashboard shows
zero traffic.

### Diagnosis

1. List the cell states: `hxcli cell show --all`. An operational state of `disabled` confirms the
   outage.
2. Check dependent alarms: `hxcli alarm list --active`. A cell is usually down because of a
   sync, transport or radio unit fault — resolve those first (RN-202 to RN-204).
3. Check the RRU link: `hxcli rru show --cell-id 3`.

### Resolution

1. If no dependent alarm is active, restart the cell by locking and unlocking it:
   `hxcli cell lock --cell-id 3`, wait 30 seconds, then `hxcli cell unlock --cell-id 3`.
2. If the cell does not recover, restart the baseband software (outage for all cells on the
   site, about 4 minutes): `hxcli node restart --warm`.
3. Confirm recovery with `hxcli cell show --cell-id 3` (operational state `enabled`) and check
   UE attach counts on the KPI dashboard.

## RN-202 PTP / GNSS synchronisation loss

**Symptoms:** alarm `HX-SYNC-LOSS`, followed by `HX-CELL-UNAVAILABLE` if not resolved.

### Diagnosis

1. Check the PTP state: `hxcli ptp show`. The state should be `LOCKED`.
2. Check the GNSS receiver: `hxcli gnss show` — at least 4 satellites must be tracked.
3. Check the grandmaster reachability from the transport team.

### Resolution

1. On 22.3 the baseband stays in holdover for a maximum of **4 hours**. After holdover expires the
   TDD cells are disabled automatically to avoid interference. Treat sync loss as a P1 incident.
2. If GNSS is the primary source and satellites are below 4, dispatch field operations to check
   the GNSS antenna and cable.
3. If PTP is the primary source, ask transport to verify the boundary clock on the cell-site
   router.
4. Once the source is restored, confirm `hxcli ptp show` returns `LOCKED`; cells re-enable
   automatically within 5 minutes.

## RN-203 NG-C link to AMF down

**Symptoms:** alarm `HX-NG-LINK-DOWN`, new UE registrations fail.

### Diagnosis

1. Check the SCTP associations: `hxcli sctp show`. The association to each AMF should be
   `ESTABLISHED`.
2. Ping the AMF N2 address from the baseband: `hxcli ping 10.20.0.10 --vrf SIG`.

### Resolution

1. If ping fails, raise a transport incident — the problem is in the backhaul.
2. If ping succeeds but SCTP is down, reset the association: `hxcli sctp reset --assoc 1`.
3. If the association still fails, check the AMF side with the core team (PLMN and TAC
   configuration must match).

## RN-204 High VSWR on radio unit

**Symptoms:** alarm `HX-RRU-VSWR-HIGH`; threshold is VSWR 1.5.

1. Read the VSWR per branch: `hxcli rru show --cell-id 3 --vswr`.
2. If one branch is above 1.5, the jumper or connector on that branch is usually loose or
   water-damaged. Dispatch field operations with a site-master.
3. As a temporary mitigation reduce output power: `hxcli cell set --cell-id 3 --power 40`.
