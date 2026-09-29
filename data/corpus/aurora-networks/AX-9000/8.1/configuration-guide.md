---
title: AX-9000 Configuration Guide
doc_type: config_guide
url: https://docs.aurora-networks.example/ax9000/8.1/config-guide
---

# AX-9000 Configuration Guide — AuroraOS 8.1

## 1. Configuration model

AuroraOS 8.1 introduces a **candidate configuration** with transactional commits. Commands
entered in configuration mode are staged in the candidate and have no effect until committed.
`write memory` is no longer supported; a successful `commit` is persistent automatically.

1. Enter configuration mode with `configure`.
2. Enter the configuration commands.
3. Review the pending changes with `show configuration diff`.
4. Commit with automatic rollback protection: `commit confirmed 5`. If you lose access to the
   router, the change is rolled back automatically after 5 minutes.
5. When the change is verified, make it permanent with `commit`.
6. Leave configuration mode with `exit`.

To undo a committed change, run `rollback 1` followed by `commit`. The last 50 commits are kept;
list them with `show system commit history`.

## 2. Interface configuration

### 2.1 Enabling an Ethernet interface

1. `configure`
2. `interfaces ge-0/1/3 description UPLINK-TO-AGG-01`
3. `interfaces ge-0/1/3 mtu 9100`
4. `interfaces ge-0/1/3 admin-state up`
5. `commit confirmed 5` then `commit`

The default MTU on AuroraOS 8.1 is 9100 bytes (changed from 1514 in 7.4). When a 7.4 router
peers with an 8.1 router over a link with default settings, the MTU will not match. Set the MTU
explicitly on both ends.

### 2.2 Link aggregation (LAG)

1. `interfaces lag-10 lacp mode active`
2. `interfaces lag-10 member ge-0/1/3`
3. `interfaces lag-10 member ge-0/1/4`
4. `interfaces lag-10 min-links 1`

## 3. OSPF

1. `protocols ospf instance 1 router-id 10.255.0.1`
2. `protocols ospf instance 1 area 0 interface ge-0/1/3`
3. `protocols ospf instance 1 area 0 interface loopback0 passive`

Verify with `show ospf neighbors`.

## 4. BGP

In AuroraOS 8.1 the `router bgp` stanza is replaced by the hierarchical `protocols bgp` tree.

1. `protocols bgp local-as 64512`
2. `protocols bgp router-id 10.255.0.1`
3. `protocols bgp neighbor 10.0.0.2 peer-as 64513`
4. `protocols bgp neighbor 10.0.0.2 description PEER-TRANSIT-A`
5. `protocols bgp neighbor 10.0.0.2 authentication-key <md5-key>`
6. `protocols bgp neighbor 10.0.0.2 timers keepalive 10 hold 30`
7. `protocols bgp neighbor 10.0.0.2 family ipv4-unicast`
8. `commit`

Verify with `show bgp summary` and `show bgp neighbor 10.0.0.2`.

### 4.1 Soft reset

The `clear ip bgp` command family was removed in 8.1. To re-apply policy without dropping the
session, run `reset bgp neighbor 10.0.0.2 soft inbound`. A hard reset is
`reset bgp neighbor 10.0.0.2 hard`.

## 5. QoS

1. `qos classifier VOICE match dscp ef`
2. `qos policy EDGE-OUT class VOICE priority-percent 20`
3. `interfaces ge-0/1/3 qos output-policy EDGE-OUT`

## 6. Management and logging

- Syslog: `system logging remote 10.10.10.5 vrf MGMT`
- NTP: `system ntp server 10.10.10.1 prefer`
- Telemetry (new in 8.1): `telemetry destination 10.10.10.7 port 57000 encoding gpb`
