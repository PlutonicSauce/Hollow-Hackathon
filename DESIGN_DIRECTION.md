> Historical Milestone 5 direction. The current launch redesign and resource evaluation are documented in [DESIGN_REVIEW.md](./DESIGN_REVIEW.md).

# LIFELINE — Design Direction

**Document status:** Historical, superseded design exploration. The deployed light recovery workspace is documented in [DESIGN_REVIEW.md](DESIGN_REVIEW.md); do not implement or restore this earlier direction.
**Do not modify the Python backend, simulation logic, or optimization engine.**

---

## Why the Current Design Isn't Working

Five consequential problems, in order of severity:

**1. The page teaches before it shows.**
A large headline, a paragraph of introduction, a scenario selector dropdown, an incident strip, and a numbered section label all appear before the user sees a single node in the dependency graph. The most compelling thing LIFELINE does—propagating a failure visually—is buried below the fold. A judge has already formed an impression before reaching the product.

**2. The information hierarchy is inverted.**
The 1,100 score is displayed as a hero number inside the sidebar. It is incomprehensible without context. The comparison that makes the number meaningful (0 → 720 → 720 → 1,100) is two panels further down the page, subordinated under a section called "Counterfactuals." The story should be told forward, not assembled backwards.

**3. Every container carries the same visual weight.**
Eight bordered panels, all dark green, all with the same padding, the same `panel-kicker` label, the same h2 heading. The incident strip, the network panel, the response panel, the timeline, the comparison panel, the impact panel, the controls panel, and the receipt panel are stylistically identical. Nothing is prominent; nothing recedes. The eye has nowhere to land.

**4. Slop patterns undermine credibility.**
The current interface exhibits: unnecessary eyebrow labels above nearly every heading (DEPENDENCY MAP / System topology; COMPUTED RESPONSE / Recommended plan; COUNTERFACTUALS / Same incident. Different plans), arbitrary section numbering (01 INFRASTRUCTURE STATE), decorative glowing status dots (the pulse in the topbar and incident strip), tiny uppercase kicker labels repeated eight times in view, a hero metric (1,100) displayed without immediate comparison, and monotonous 14px spacing grids throughout. These patterns signal automated output, not design judgment.

**5. The dependency graph does not communicate structure—it communicates complexity.**
Nodes are uniformly sized rectangles with uppercase status labels inside them. All edges look similar. The graph does not visually distinguish between a source node (the thing that broke), an infrastructure hub (the thing whose restoration changes everything), and a demand node (the people whose service is at stake). A viewer cannot immediately read the graph as a story.

---

## Chosen Concept: The Field Dossier

**Why not the other two concepts:**
- *"Control Room"* evokes generic military dashboards and invites every cyberpunk cliché listed in the brief.
- *"Schematic Blueprint"* is visually arresting but structurally awkward for an interactive application with real-time state changes and playback controls.

**The Field Dossier** treats LIFELINE as the operational document a planning officer in the Hollow would carry. Not a software dashboard. Not a data terminal. A working document with physical presence—the kind of thing made when decision-making stakes are high, information must be verified, and there is no room for decoration.

The reference is field engineering documents, infrastructure survey maps, incident command worksheets, and civic planning documents. These have high information density, clear typographic hierarchy, deliberate use of ruled lines and zones rather than bordered cards, and a visual vocabulary that earns trust through restraint.

This is not nostalgia. It is a character claim: LIFELINE is an artifact produced by and for a civilization that takes infrastructure seriously.

---

## Visual Identity

### Typography

**Primary (headings, labels, UI text):** `IBM Plex Sans` — engineered, legible, slightly institutional. Its narrower proportions and rational construction read as working documents, not startup landing pages. Available via Google Fonts, no installation required.

**Data and coordinates:** `IBM Plex Mono` — matches the primary, reads as measurements and identifiers rather than code-terminal decoration.

**Reject:** DM Sans (too generic), Manrope (too expressive), any font that reads as a marketing deck.

### Color

Abandon the dark green monochrome. The Hollow is underground: no daylight, specific ambient light conditions, aging infrastructure. The palette should feel like worn materials under controlled artificial light—not vegetation.

| Token | Value | Role |
|---|---|---|
| `--surface` | `#0f0e0c` | Base: deep coal, not green |
| `--surface-1` | `#161512` | Elevated panels |
| `--surface-2` | `#1e1c18` | Input fields, insets |
| `--rule` | `#2e2b25` | Dividers, panel borders |
| `--text` | `#e8e4dc` | Primary text: warm near-white |
| `--text-2` | `#9b9589` | Secondary: aged paper tone |
| `--text-3` | `#5e5a53` | Muted: rules, placeholders |
| `--signal` | `#c8a86b` | Amber: active backup, warnings. The only warm accent. |
| `--operational` | `#8aab78` | Muted sage: operational/working status |
| `--fault` | `#c26b5e` | Dull clay-red: faults and failures |
| `--exact` | `#7ba3c4` | Steel blue: verification, receipt, exact search. Used once. |
| `--mono` | IBM Plex Mono | |

**No gradients.** No glow. No radial backgrounds. Texture comes from typography and spacing, not blurred color fields.

The amber (`--signal`) is the only warm color in the system. It carries all the meaning: backup services, stale states, warnings, the moment a plan is working. Everything else is cool and neutral. When amber appears, it matters.

### Spacing

Replace monotonous card-grid spacing with a document column system.

- Maximum content width: 1,320px (desktop)
- Two-column split: 60% dependency map / 40% response panel (not equal halves)
- Horizontal rules, not bordered boxes, to separate major zones
- Dense within zones, generous between them

**No panel-kicker labels.** The section heading itself should communicate what a section is. If it cannot, the section heading is wrong.

### Surfaces

Panels are **not** bordered boxes. Major zones are defined by horizontal rules and typographic hierarchy. Where a contained area is needed (the graph, the scrubber), use a background tint (`--surface-1`) without a border. Only the receipt and verification result get a subtle border—because they represent a distinct artifact with provenance.

---

## Primary Screen Layout and Hierarchy

### Desktop (≥ 960px wide)

```
┌─────────────────────────────────────────────────────────────────┐
│ LIFELINE                              Hollow / Planning Office   │
│ [scenario dropdown]                                             │
├─────────────────────────────────────────────────────────────────┤
│                     INCIDENT HEADER                             │
│  [fault description, plain language]        [horizon / status]  │
├──────────────────────────────┬──────────────────────────────────┤
│                              │                                  │
│   DEPENDENCY GRAPH           │   COORDINATED RESPONSE          │
│   (full topology, animated)  │   [crew assignments, plain lang] │
│                              │   ─────────────────             │
│   [plan selector tabs]       │   OUTCOME COMPARISON            │
│   [minute scrubber]          │   [4-row score bars, prominent]  │
│                              │   ─────────────────             │
│                              │   COMMUNITY OUTCOMES             │
│                              │   [2 service rows, coverage bar] │
├──────────────────────────────┴──────────────────────────────────┤
│                   WHAT-IF CONDITIONS                            │
│   [resources]              [travel times]    [fairness]         │
│                            [recalculate]                        │
├─────────────────────────────────────────────────────────────────┤
│                   DECISION RECEIPT                   [verify]   │
└─────────────────────────────────────────────────────────────────┘
```

**Key structural change:** The comparison panel (counterfactuals) moves **into** the right column, directly below the crew assignments. The user sees the winning number and the alternatives in the same visual zone. The dependency graph and outcome comparison are neighbors, not separated by a scroll event.

Community outcomes (formerly "Modeled Needs") move to the bottom of the right column. They are subordinate to the plan choice, not equal to it.

### Mobile (< 640px wide)

```
┌────────────────────────┐
│ LIFELINE               │
│ [scenario]             │
├────────────────────────┤
│ INCIDENT               │
│ [fault description]    │
├────────────────────────┤
│ COORDINATED RESPONSE   │
│ [crew list]            │
│ COMPARISON [bars]      │
├────────────────────────┤
│ DEPENDENCY GRAPH       │
│ [vertical stack]       │
│ [plan tabs] [scrubber] │
├────────────────────────┤
│ COMMUNITY OUTCOMES     │
├────────────────────────┤
│ CONDITIONS             │
├────────────────────────┤
│ RECEIPT     [verify]   │
└────────────────────────┘
```

On mobile, the response and comparison panels come **before** the graph. The recommendation is the first thing a user reads; the graph is the supporting evidence.

---

## User Journey: Signature Scenario

1. **Page loads.** The incident header states, in plain language: "Feeder offline. Aquifer interrupted. Air and water services at risk." No jargon. No eyebrow label. No icon.

2. **The graph is visible at first scroll.** Two fault nodes are red. The pump in the middle is red (both inputs missing). The two demand endpoints are red. The cascade is obvious.

3. **The right column shows the recommendation.** Not a number first—the assignments first: "Mobile generator crew → pump power input. Water tanker crew → pump water input." Then the score context. Then the comparison showing that a direct response protects ventilation (720), while coordinating both crews restores the pump and protects both ventilation and water (1,100).

4. **The user understands the complementarity.** The graph and comparison are side-by-side. No scrolling required to see why the plan beats the alternatives.

5. **The user scrubs the timeline.** Tabs under the graph let them switch between LIFELINE / Greedy / Static / None. The graph animates the minute state. Amber edges appear when backup crews are active.

6. **The user adjusts conditions.** What-if controls are below the fold. Stale state is communicated by an amber tint on the right column, not a separate banner.

7. **The user verifies the receipt.** The receipt section is at the bottom. Single "Verify" button. Verification result is binary and clear: passed or failed with specific checks.

---

## The Central Before/After Comparison

The comparison is not a subordinate panel. It is the second most important element on the page, after the graph.

**New treatment:**
- Four rows, stacked vertically, each showing: plan name, a horizontal bar, and the score
- Bars are proportionally scaled to the peak score (1,100)
- "No intervention" and both baselines: `--text-3` bars (dim, muted)
- "LIFELINE exact": full-width `--operational` bar with the score in `--text`
- The score delta appears as a plain annotation: "+380 above next best"
- No "RECOMMENDED" badge, no eyebrow label. The bar communicates the advantage visually.

The comparison block should be ~180px tall. It must be fully visible without scrolling on a standard 1080p display when combined with the crew list above it.

---

## The Dependency Graph

**Problems to fix:**
- All nodes look the same
- The graph is not readable as a story
- Node labels include UPPERCASE STATUS TEXT that crowds the visual space

**New treatment:**

**Node shapes communicate role:**
- Source nodes (things that failed): horizontal rectangle, `--fault` left border (3px), red status dot
- Hub/facility nodes (the pump and battery): slightly larger rectangle with a thicker border, amber left border when receiving backup
- Demand endpoint nodes (community services): rounded rectangle with an outer ring (not a demand-ring circle in a corner—a full node ring), `--operational` when served

**Edge weight communicates importance:**
- Primary dependency edges: 2px solid
- Currently-active-backup edges: 2px dashed amber, slightly thicker than normal edges
- Failed/unmet edges: 1.5px dashed red, reduced opacity

**Node label hierarchy:**
- Asset name: 13px IBM Plex Sans, medium weight (the primary label, center of node)
- Status: 11px, one line only, plain language: "offline" / "on backup" / "on reserve" / "working"
- Remove the UPPERCASE TYPE LABEL ("SOURCE", "FACILITY") from inside the node. Put the asset kind as a tiny notation outside or at the top of the node only when space allows.

**Demand rings:** Replace the small circle in the corner with a visible concentric ring around the full demand-endpoint node. The ring changes color (operational → sage, offline → red) to show service status at a glance.

---

## Response Recommendation Explanation

**Remove:** The "WHY THIS PLAN" kicker and the bordered blockquote treatment.

**Replace with:** Plain language, integrated into the assignment list rather than separated.

Format:
```
Coordinating separate crews at Shared deep-sector water pump provides both missing inputs.
Generator → pump power   (arrives minute 0)
Tanker → pump water      (arrives minute 1)

A direct response protects ventilation. Coordinating both crews protects ventilation and water.
```

The RecommendationInsight component logic is correct. The presentation just needs to express it as a human sentence at the top of the assignments, not as a labeled box below them.

---

## Decision Receipt

**Problem:** The receipt section is currently as long as the entire rest of the page. It overwhelms.

**Solution:** Collapse it by default. The verify button is prominent and immediately accessible. The raw payload is a secondary disclosure (`<details>`). The verification result is the star—not the JSON.

**New treatment:**
- Receipt section: single row with scenario name, SHA-256 digest (first 8 chars), and "Verify" button
- After verification: expand to show the check list (7 rows, two columns)
- Verification pass: `--operational` left border on the section. Verification fail: `--fault` border.
- Remove: the 4-stat summary row (SCHEMA, SEARCH, BEST PRIMARY SCORE, SELECTED SCORE)—this information is redundant with the comparison panel
- Retain: assumptions and limitations lists, collapsed inside a `<details>` below the verification result

---

## Elements to Remove, Replace, or Retain

**Remove:**
- All `panel-kicker` / eyebrow labels above every heading
- The `01 INFRASTRUCTURE STATE` section number
- The `workspace-dot` glowing dot in the topbar
- The `status-pulse` glowing dot in the incident strip
- The `model-badge` ("DETERMINISTIC MODEL") and `live-indicator` ("LOCAL SIMULATION") in the topbar — this information belongs in the footer disclaimer only
- The large h1 marketing headline ("See the cascade. / Choose what holds.") — replace with the incident description
- The `eyebrow-line` decorative horizontal line before the eyebrow label
- Background radial gradients

**Replace:**
- All `panel` bordered boxes → zone-based layout with ruled horizontal separators
- `DM Sans` / `Manrope` fonts → IBM Plex Sans / IBM Plex Mono
- Dark green monochrome palette → warm coal/amber/sage palette defined above
- The separate comparison panel below the fold → embedded in the right column
- Node status labels in ALL CAPS → plain sentence case inside nodes
- The recommendation score hero number at the top of the right panel → assignments first, then score, then comparison

**Retain:**
- All functional controls: scenario select, resource checkboxes, travel time inputs, fairness slider, recalculate button, play/pause, scrubber
- All React component logic and API calls — zero functional changes
- The existing SVG-based DependencyMap component, adapted with new CSS classes
- The RecommendationInsight logic (complementary assignment detection)
- The ReceiptInspector component, collapsed by default
- All stale-state handling logic — replace the banner with an amber tint on the right column
- All responsive breakpoints — adapt to new layout
- All accessibility attributes and ARIA labels

---

## Acceptance Criteria

A judge can open the page and within 30 seconds answer:

1. **What happened?** The incident description in the header states it in plain language.
2. **What is affected?** Two red demand-endpoint nodes are visible in the graph without scrolling (or at the top of scroll on mobile).
3. **What is the response?** The crew list and comparison bars are visible in the right column without scrolling (desktop).
4. **Why does the response work?** The explanation showing that a direct response protects only ventilation while coordinated crew dispatch restores shared pump service for both ventilation and water is clearly stated.
5. **Can I trust it?** The "Verify this decision" button is in the receipt section at the bottom. One click returns a pass/fail.

**Measurable implementation checks:**

| Check | Criterion |
|---|---|
| Zero panel-kicker / eyebrow labels | Grep `panel-kicker`, `eyebrow` in CSS/JSX = 0 results |
| Zero glowing decorative dots in topbar | No `workspace-dot`, `status-pulse`, `live-indicator span` elements |
| Comparison bars visible without scrolling | CSS: comparison block is inside right column, not below `.lower-grid` |
| Fonts load correctly | `IBM Plex Sans` and `IBM Plex Mono` in network tab |
| No background radial-gradient | CSS: `body` background is flat `--surface` |
| Node status in sentence case | No `text-transform: uppercase` on node status text inside SVG |
| Receipt collapsed by default | No `open` attribute on the receipt details section on load |
| Stale state: amber tint on right column | `.response-panel` gets a left-border tint change, not a banner above the graph |
| Graph visible at ≤ 2 scroll events on 1080p | Manual check at 1920×1080 |

---

## Implementation Handoff

The implementation agent should work in this order:

**Phase 1: Typography and tokens (30 min)**
- Add `IBM Plex Sans` and `IBM Plex Mono` via Google Fonts import in `index.html` (400, 500, 600 weights)
- Replace all CSS custom properties in `:root` with the new palette above
- Update `font-family` declarations throughout `styles.css`
- Remove: radial-gradient backgrounds from `body`

**Phase 2: Remove slop (45 min)**
- Delete `topbar-center`, `workspace-dot`, `model-badge`, `live-indicator` from JSX and CSS
- Delete all `eyebrow` / `panel-kicker` elements from JSX
- Delete the `section-label` numbered section divider
- Replace the `h1` / `eyebrow` / `intro` / `page-heading` block with an incident header component (plain language fault description from the scenario data, full width)
- Keep the scenario selector — move it to the topbar right, next to the brand

**Phase 3: Layout restructure (60 min)**
- Remove all `panel` class border styling; use zone-based layout with ruled `border-top: 1px solid var(--rule)` separators
- Move comparison list into right column (after dispatch list, before community outcomes)
- Move community outcomes to bottom of right column
- Make right column `position: sticky; top: 0` on desktop so it stays visible while scrolling the left graph

**Phase 4: Graph restyling (45 min)**
- Apply new node CSS classes: `node-source`, `node-hub`, `node-demand` for shape and border treatment
- Remove uppercase text-transform from node status labels
- Apply `--signal` color to amber edges (backup-active edges)
- Increase demand-ring from corner circle to full node stroke

**Phase 5: Response and comparison restyling (30 min)**
- Restructure dispatch list: short plain-language summary sentence above assignments
- Reorder: summary sentence → dispatch rows → comparison bars
- Restyle comparison bars: muted for baselines, `--operational` for LIFELINE exact
- Replace "RECOMMENDED" badge with "+N above next best" annotation

**Phase 6: Receipt collapse and verification (30 min)**
- Collapse receipt section to single row by default
- Expand on verify button click (or use `<details>`)
- Apply left-border color change on verification pass/fail
- Move assumptions/limitations inside nested `<details>`

**Phase 7: Stale state (20 min)**
- Remove `stale-banner` above graph
- Apply amber left-border tint to right column when results are stale
- Keep stale-banner text as a small inline note at the top of right column only

**Do not change:** `api.ts`, `types.ts`, any backend files, test files, the `layoutAssets` function logic (only CSS restyling of the graph output), or any of the React state management.

---

*This document is the design contract for the next implementation agent. All decisions above are final. Do not interpret absence of specification as latitude to introduce new components, install design frameworks, or add decorative elements.*
