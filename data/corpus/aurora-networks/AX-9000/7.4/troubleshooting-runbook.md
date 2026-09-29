---
title: AX-9000 Troubleshooting Runbook
doc_type: runbook
url: https://docs.aurora-networks.example/ax9000/7.4/runbook
---

# AX-9000 Troubleshooting Runbook — AuroraOS 7.4

Use this runbook during incidents on AX-9000 core and edge routers running AuroraOS 7.4.x.
Always open an incident ticket and note the start time before making changes.

## RB-101 BGP session down or flapping

**Symptoms:** alarm `AX-ALM-4102 BGP peer down`, customer prefixes withdrawn, traffic shifted
to backup transit.

### Diagnosis

1. Check the session state: `show ip bgp summary`. A state of `Active` or `Idle` means the
   session is not established.
2. Check the reason for the last reset: `show ip bgp neighbors 10.0.0.2 | include Last reset`.
3. Verify reachability of the peer address: `ping 10.0.0.2 source loopback0`.
4. Check the underlying interface for errors: `show interface ge-0/1/3 counters errors`.
5. Look for hold-timer expiry in the log: `show logging | include BGP-5-ADJCHANGE`.

### Resolution

1. If the reset reason is `Hold timer expired` and the interface shows input errors, fix the
   physical layer first (see RB-102).
2. If the reason is `MD5 authentication failure`, confirm the key with the peer and re-enter
   it: `configure terminal` → `router bgp 64512` → `neighbor 10.0.0.2 password <key>`.
3. If the session is stuck after the underlying issue is fixed, perform a soft reset:
   `clear ip bgp 10.0.0.2 soft`.
4. Only if the soft reset does not recover the session, perform a hard reset:
   `clear ip bgp 10.0.0.2`. Expect all routes from that peer to be withdrawn for up to 90
   seconds.
5. Save any configuration change with `write memory`.
6. Confirm recovery: `show ip bgp summary` shows the peer `Established` and the prefix count is
   back to the baseline recorded in the CMDB.

**Escalate** to Aurora TAC if the session flaps more than 3 times in 10 minutes after the
physical layer is confirmed clean.

## RB-102 Interface CRC / input errors

**Symptoms:** alarm `AX-ALM-3007 Interface error threshold crossed`, packet loss on the link.

### Diagnosis

1. Read the counters: `show interface ge-0/1/3 counters errors`. Note the CRC and input error
   values.
2. Clear the counters and re-check after 60 seconds: `clear counters ge-0/1/3`.
3. Check optical levels: `show optics ge-0/1/3`. Receive power below −14 dBm on a 10G-LR optic
   indicates a dirty or damaged fibre.

### Resolution

1. If receive power is low, dispatch field operations to clean the connectors at both ends.
2. If receive power is normal but CRC errors keep incrementing, replace the optic.
3. If errors persist after the optic swap, move the circuit to a spare port and raise an RMA
   for the line card.
4. After the fix, confirm counters stay at zero for 15 minutes before closing the incident.

## RB-103 High CPU on the route processor

**Symptoms:** alarm `AX-ALM-1201 RP CPU above 90%`, slow CLI, protocol flaps.

### Diagnosis

1. Identify the top processes: `show processes cpu sorted`.
2. If `bgpd` is on top, check the route churn: `show ip bgp summary` and look at the
   `MsgRcvd` counters.
3. If `snmpd` is on top, check for aggressive polling from the NMS.

### Resolution

1. For BGP churn caused by a single flapping peer, apply a dampening policy or shut the peer
   (`neighbor 10.0.0.2 shutdown`) after informing the peering team.
2. For SNMP polling storms, rate-limit SNMP with `snmp-server rate-limit 200`.
3. If CPU stays above 90% for more than 15 minutes with no identifiable cause, fail over to the
   standby route processor: `redundancy switchover`.

## RB-104 OSPF adjacency stuck in EXSTART/EXCHANGE

1. `show ip ospf neighbor` — confirm the neighbor is stuck in `EXSTART` or `EXCHANGE`.
2. Compare the MTU on both ends: `show interface ge-0/1/3 | include MTU`.
3. Set matching MTU values on both ends (`mtu 9100`), then `write memory`.
4. If MTU cannot be changed on the far end, configure `ip ospf mtu-ignore` on the interface as a
   temporary workaround and raise a change request.

## RB-105 Line card temperature alarm

**Symptoms:** alarm `AX-ALM-2031 Line card temperature critical`.

1. `show environment temperature` — confirm which slot is over threshold (critical ≥ 85 °C).
2. `show environment fans` — check for a failed fan tray.
3. If a fan tray has failed, hot-swap it; AX-9000 supports fan-tray replacement without an
   outage if completed within 120 seconds.
4. If fans are healthy, check the site HVAC and raise a facilities ticket.
5. If the card reaches 95 °C it shuts down automatically to protect the hardware.
