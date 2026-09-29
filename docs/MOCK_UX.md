# Mock UX — query / answer experience

Three-column layout (single column on mobile):

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ◉ NOC Copilot                                            [52 sections indexed · flash]  │
├────────────────────┬─────────────────────────────────────────┬───────────────────────────┤
│ Equipment          │ BGP peer 10.0.0.2 stuck in Idle…        │ SOURCES                   │
│ [AX-9000 ▾]        │ [AX-9000 8.1] [grounded answer] [1.8 s] │ [1] AX-9000 Troubleshoot… │
│ Software release   │ Soft-reset the peer once the physical   │ AX-9000 8.1 · RB-101 BGP… │
│ ( 7.4 ) [ 8.1 ]    │ layer is clean.                         │ lines 26–46 · rel 0.82    │
│ Search in          │ 1. Check session state ¹                │ ┌───────────────────────┐ │
│ (Runbooks)(Config) │    ┌──────────────────────────┐ [Copy]  │ │ ### Resolution        │ │
│ (Manuals)(Release) │    │ show bgp summary         │         │ │ 1. If the last error… │ │
│ Symptom / alarm    │    └──────────────────────────┘         │ └───────────────────────┘ │
│ ┌────────────────┐ │ 2. Soft reset ¹                         │ Open in vendor portal ↗   │
│ │                │ │    reset bgp neighbor 10.0.0.2 soft     │                           │
│ └────────────────┘ │ ⚠ Known issue AX-81-0042 … ¹            │ [2] AuroraOS 8.1 Release… │
│ [Find resolution]  │                                         │                           │
│ Try: …examples…    │ (follow-up questions stack below)       │                           │
└────────────────────┴─────────────────────────────────────────┴───────────────────────────┘
```

Principles:
- **Release first.** The release selector sits above the question box and is always visible. The
  answer header repeats the release as a tag.
- **Commands are copyable blocks**, copied verbatim from the source.
- **Every step has a superscript citation.** Clicking it scrolls to and highlights the source card.
- **Not found is loud.** A red box explains that nothing in *this release's* docs matches and shows
  the closest sections, so the engineer can escalate with confidence.
- **Incident context.** Follow-ups keep history until the engineer clicks "New incident" or
  changes the equipment or release.
