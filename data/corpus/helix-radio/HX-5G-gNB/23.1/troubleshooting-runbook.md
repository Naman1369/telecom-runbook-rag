---
title: HX-5G gNodeB Troubleshooting Runbook
doc_type: runbook
url: https://support.helix-radio.example/hx5g/23.1/runbook
---

# HX-5G gNodeB Troubleshooting Runbook — Software 23.1

Applies to HX-5G gNodeB baseband units running software release 23.1.x. The 23.1 CLI uses the
new `nr-cell` and `transport` command trees; 22.3 commands such as `hxcli cell lock` are no
longer accepted.

## RN-201 NR cell down

**Symptoms:** alarm `HX-CELL-UNAVAILABLE`, no UEs attached on the cell.

### Diagnosis

1. List the cell states: `hxcli nr-cell list`. An operational state of `disabled` confirms the
   outage.
2. Check dependent alarms: `hxcli alarm list --active --correlated`. 23.1 groups correlated
   alarms and marks the root cause with `(root)`.
3. Check the radio unit: `hxcli ru status --cell 3`.

### Resolution

1. If no root-cause alarm is active, restart the cell:
   `hxcli nr-cell set-admin-state 3 locked`, wait 30 seconds, then
   `hxcli nr-cell set-admin-state 3 unlocked`.
2. If the cell does not recover, restart only the affected cell's software process (new in 23.1,
   other cells keep carrying traffic): `hxcli nr-cell restart 3`.
3. Only if the cell restart fails, perform a node warm restart: `hxcli node restart --warm`.
4. Confirm recovery with `hxcli nr-cell list` (operational state `enabled`).

## RN-202 PTP / GNSS synchronisation loss

**Symptoms:** alarm `HX-SYNC-LOSS` or `HX-SYNC-HOLDOVER`.

### Diagnosis

1. Check the overall sync state: `hxcli sync status`. States are `LOCKED`, `HOLDOVER` or
   `FREERUN`.
2. The same command shows the GNSS satellite count and the PTP grandmaster identity.

### Resolution

1. Release 23.1 on baseband hardware revision C (OCXO oscillator) supports **24-hour holdover**.
   Hardware revisions A/B still have a 4-hour holdover. Check the hardware revision with
   `hxcli inventory show`.
2. While in `HOLDOVER`, cells keep carrying traffic; raise a P2 incident (P1 if remaining
   holdover is below 1 hour — shown in `hxcli sync status`).
3. If GNSS satellites are below 4, dispatch field operations to check the GNSS antenna.
4. If PTP is the source, ask transport to verify the boundary clock on the cell-site router.
5. New in 23.1: you can switch to the backup source manually with
   `hxcli sync set-source ptp` or `hxcli sync set-source gnss`.

## RN-203 NG-C link to AMF down

**Symptoms:** alarm `HX-NG-LINK-DOWN`, new UE registrations fail.

### Diagnosis

1. Check the NG-C transport status: `hxcli transport ng-c status`. Each AMF should be `UP`.
2. Ping the AMF N2 address: `hxcli transport ping 10.20.0.10 --vrf SIG`.

### Resolution

1. If ping fails, raise a transport incident — the problem is in the backhaul.
2. If ping succeeds but the NG-C link is down, reset it: `hxcli transport ng-c reset --amf 1`.
3. 23.1 supports AMF pooling: if one AMF is down, confirm UEs are served by the pool with
   `hxcli transport ng-c status --pool`.

## RN-204 High VSWR on radio unit

**Symptoms:** alarm `HX-RU-VSWR-HIGH`; threshold is VSWR 1.5.

1. Run the built-in VSWR test (new in 23.1): `hxcli ru vswr-test --cell 3 --port A`. The test
   takes 20 seconds and briefly mutes the branch under test.
2. If one branch is above 1.5, dispatch field operations to inspect the jumper and connector.
3. As a temporary mitigation reduce output power: `hxcli nr-cell set-power 3 40`.
