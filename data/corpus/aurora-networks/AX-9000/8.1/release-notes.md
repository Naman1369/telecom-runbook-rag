---
title: AuroraOS 8.1 Release Notes
doc_type: release_notes
url: https://docs.aurora-networks.example/ax9000/8.1/release-notes
---

# AuroraOS 8.1 Release Notes (AX-9000)

## Upgrade path

- Supported direct upgrade: 7.4.6 or later → 8.1.x. Routers on 7.4.0–7.4.5 must first upgrade
  to 7.4.6.
- The upgrade converts the running configuration to the 8.1 hierarchical syntax automatically.
  Review the converted configuration with `show configuration` before the first `commit`.
- Plan a maintenance window of 25 minutes per router; line cards reload sequentially.

## Breaking changes

| Area | AuroraOS 7.4 | AuroraOS 8.1 |
| --- | --- | --- |
| Configuration model | Immediate apply, `write memory` | Candidate + `commit`, `write memory` removed |
| Enter config mode | `configure terminal` | `configure` |
| BGP configuration | `router bgp <asn>` | `protocols bgp local-as <asn>` |
| BGP session reset | `clear ip bgp <peer> [soft]` | `reset bgp neighbor <peer> soft|hard` |
| BGP status | `show ip bgp summary` | `show bgp summary` |
| Interface errors | `show interface <if> counters errors` | `show interfaces <if> statistics errors` |
| Optics | `show optics <if>` | `show interfaces <if> transceiver` |
| CPU processes | `show processes cpu sorted` | `show system processes cpu` |
| RP failover | `redundancy switchover` | `request system switchover` |
| Default MTU | 1514 | 9100 |
| OSPF MTU ignore | `ip ospf mtu-ignore` supported | Removed |

## Alarm renaming

| 7.4 alarm | 8.1 alarm |
| --- | --- |
| AX-ALM-1201 RP CPU above 90% | SYS-CPU-HIGH |
| AX-ALM-2031 Line card temperature critical | SYS-TEMP-CRIT |
| AX-ALM-3007 Interface error threshold crossed | IF-ERRORS-THRESHOLD |
| AX-ALM-4102 BGP peer down | ROUTING-BGP-PEER-DOWN |
| AX-ALM-5001 Power supply failure | SYS-PSU-FAIL |

## New features

- `commit confirmed <minutes>` with automatic rollback.
- BGP graceful restart enabled by default (120 s restart time).
- Streaming telemetry (gRPC, GPB encoding).
- Copper cable diagnostics: `test interfaces <if> cable-diagnostics`.
- Thermal throttling at 90 °C before shutdown.

## Known issues

- **AX-81-0042** — `bgpd` memory exhaustion with more than 500,000 received prefixes causes
  session flaps on 8.1.0 and 8.1.1. Fixed in 8.1.2. Workaround: `max-prefix 450000 warning-only`.
- **AX-81-0057** — `show interfaces transceiver` reports receive power as −40 dBm for 100G-ZR
  optics on 8.1.0. Cosmetic; fixed in 8.1.1.
