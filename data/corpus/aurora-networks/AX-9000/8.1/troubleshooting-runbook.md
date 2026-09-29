---
title: AX-9000 Troubleshooting Runbook
doc_type: runbook
url: https://docs.aurora-networks.example/ax9000/8.1/runbook
---

# AX-9000 Troubleshooting Runbook — AuroraOS 8.1

Use this runbook during incidents on AX-9000 routers running AuroraOS 8.1.x. Commands differ
from 7.4 — do not use 7.4 procedures on 8.1 routers. Alarm names follow the new 8.1 scheme.

## RB-101 BGP session down or flapping

**Symptoms:** alarm `ROUTING-BGP-PEER-DOWN`, customer prefixes withdrawn, traffic shifted to
backup transit.

### Diagnosis

1. Check the session state: `show bgp summary`. A state of `Active`, `Connect` or `Idle` means
   the session is not established.
2. Check the reason for the last reset: `show bgp neighbor 10.0.0.2 last-error`.
3. Verify reachability of the peer address: `ping 10.0.0.2 source-interface loopback0`.
4. Check the underlying interface for errors: `show interfaces ge-0/1/3 statistics errors`.
5. Look for hold-timer expiry in the event log: `show log events filter bgp`.

### Resolution

1. If the last error is `Hold timer expired` and the interface shows errors, fix the physical
   layer first (see RB-102).
2. If the last error is `Authentication failure`, confirm the key with the peer, then:
   `configure` → `protocols bgp neighbor 10.0.0.2 authentication-key <key>` →
   `commit confirmed 5` → `commit`.
3. If the session is stuck after the underlying issue is fixed, perform a soft reset:
   `reset bgp neighbor 10.0.0.2 soft`.
4. Only if the soft reset does not recover the session, perform a hard reset:
   `reset bgp neighbor 10.0.0.2 hard`. Graceful restart in 8.1 keeps forwarding for up to
   120 seconds during the reset.
5. Confirm recovery: `show bgp summary` shows the peer `Established` and the prefix count is
   back to the CMDB baseline.

**Known issue AX-81-0042:** on 8.1.0 and 8.1.1, sessions with more than 500,000 received
prefixes may flap because `bgpd` exhausts memory. Upgrade to 8.1.2, or as a workaround set
`protocols bgp neighbor 10.0.0.2 max-prefix 450000 warning-only`.

**Escalate** to Aurora TAC if the session flaps more than 3 times in 10 minutes after the
physical layer is confirmed clean.

## RB-102 Interface CRC / input errors

**Symptoms:** alarm `IF-ERRORS-THRESHOLD`, packet loss on the link.

### Diagnosis

1. Read the counters: `show interfaces ge-0/1/3 statistics errors`.
2. Clear the counters and re-check after 60 seconds: `clear interfaces ge-0/1/3 statistics`.
3. Check optical levels: `show interfaces ge-0/1/3 transceiver`. Receive power below −14 dBm on
   a 10G-LR optic indicates a dirty or damaged fibre.
4. New in 8.1: run the built-in cable test on copper ports with
   `test interfaces ge-0/1/3 cable-diagnostics`.

### Resolution

1. If receive power is low, dispatch field operations to clean the connectors at both ends.
2. If receive power is normal but CRC errors keep incrementing, replace the optic.
3. If errors persist after the optic swap, move the circuit to a spare port and raise an RMA
   for the line card.
4. After the fix, confirm counters stay at zero for 15 minutes before closing the incident.

## RB-103 High CPU on the route processor

**Symptoms:** alarm `SYS-CPU-HIGH`, slow CLI, protocol flaps.

### Diagnosis

1. Identify the top processes: `show system processes cpu`.
2. If `bgpd` is on top, check for known issue AX-81-0042 (see RB-101) and the route churn with
   `show bgp summary`.
3. If `telemetryd` is on top, check the number of telemetry subscriptions:
   `show telemetry subscriptions`.

### Resolution

1. For BGP churn caused by a single flapping peer, disable the peer after informing the peering
   team: `protocols bgp neighbor 10.0.0.2 admin-state down` → `commit`.
2. For telemetry overload, raise the sample interval to at least 30 seconds.
3. If CPU stays above 90% for more than 15 minutes with no identifiable cause, fail over to the
   standby route processor: `request system switchover`.

## RB-104 OSPF adjacency stuck in EXSTART/EXCHANGE

1. `show ospf neighbors` — confirm the neighbor is stuck in `ExStart` or `Exchange`.
2. Compare the MTU on both ends: `show interfaces ge-0/1/3 | match mtu`. Remember that the 8.1
   default MTU is 9100 while 7.4 defaults to 1514 — this is the most common cause after an
   upgrade.
3. Set matching MTU values: `interfaces ge-0/1/3 mtu 1514` (or 9100 on both ends) → `commit`.
4. `ip ospf mtu-ignore` is not available in 8.1; the MTU must match.

## RB-105 Line card temperature alarm

**Symptoms:** alarm `SYS-TEMP-CRIT` (was `AX-ALM-2031` in 7.4).

1. `show system environment temperature` — confirm the slot over threshold (critical ≥ 85 °C).
2. `show system environment fans` — check for a failed fan tray.
3. If a fan tray has failed, hot-swap it within 120 seconds.
4. If fans are healthy, check the site HVAC and raise a facilities ticket.
5. In 8.1 the card throttles line rate by 50% at 90 °C before shutting down at 95 °C.
