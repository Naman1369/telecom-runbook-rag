---
title: AX-9000 Configuration Guide
doc_type: config_guide
url: https://docs.aurora-networks.example/ax9000/7.4/config-guide
---

# AX-9000 Configuration Guide — AuroraOS 7.4

## 1. Configuration model

AuroraOS 7.4 uses an **immediate-apply** configuration model. Every command entered in
configuration mode takes effect as soon as you press Enter. There is no candidate
configuration and no automatic rollback.

1. Enter configuration mode with `configure terminal`.
2. Enter the configuration commands.
3. Leave configuration mode with `end`.
4. Save the running configuration to flash with `write memory`. Changes that are not saved
   are lost on reload.

To revert a mistake you must manually re-enter the previous configuration. Operators are
advised to take a backup with `copy running-config flash:backup-<date>.cfg` before any
maintenance window.

## 2. Interface configuration

### 2.1 Enabling an Ethernet interface

1. `configure terminal`
2. `interface ge-0/1/3`
3. `description UPLINK-TO-AGG-01`
4. `mtu 9100`
5. `no shutdown`
6. `end` then `write memory`

The default MTU on AuroraOS 7.4 is 1514 bytes. Jumbo frames must be enabled per interface.
Both ends of a link must use the same MTU, otherwise OSPF adjacencies can stall in the
EXSTART/EXCHANGE state.

### 2.2 Link aggregation (LAG)

1. `interface lag-10`
2. `lacp mode active`
3. `member ge-0/1/3` and `member ge-0/1/4`
4. `minimum-links 1`

## 3. OSPF

1. `router ospf 1`
2. `router-id 10.255.0.1`
3. `network 10.0.0.0 0.0.0.255 area 0`
4. `passive-interface loopback0`

Verify with `show ip ospf neighbor`.

## 4. BGP

AuroraOS 7.4 configures BGP under the `router bgp` stanza.

1. `router bgp 64512`
2. `bgp router-id 10.255.0.1`
3. `neighbor 10.0.0.2 remote-as 64513`
4. `neighbor 10.0.0.2 description PEER-TRANSIT-A`
5. `neighbor 10.0.0.2 password <md5-key>`
6. `neighbor 10.0.0.2 timers 10 30` (keepalive 10 s, hold 30 s)
7. `address-family ipv4 unicast` then `neighbor 10.0.0.2 activate`

Verify with `show ip bgp summary` and `show ip bgp neighbors 10.0.0.2`.

### 4.1 Soft reconfiguration

To apply a new route policy without tearing the session down, run
`clear ip bgp 10.0.0.2 soft in`. A hard reset (`clear ip bgp 10.0.0.2`) drops the session
and all routes learned from that peer — avoid it during business hours.

## 5. QoS

1. `class-map VOICE` → `match dscp ef`
2. `policy-map EDGE-OUT` → `class VOICE` → `priority percent 20`
3. `interface ge-0/1/3` → `service-policy output EDGE-OUT`

## 6. Management and logging

- Syslog: `logging host 10.10.10.5 vrf MGMT`
- NTP: `ntp server 10.10.10.1 prefer`
- SNMP traps: `snmp-server host 10.10.10.6 version 2c <community>`
