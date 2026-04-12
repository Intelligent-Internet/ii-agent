---
applyTo: "**/*.md"
---

# Diagrams

Use Mermaid diagrams instead of ASCII art in all markdown files. Generate GitHub Markdown
compatible Mermaid using only supported features: HEX colors, standard shapes, basic text
formatting.

- Use Mermaid charts with actual class/interface names in blocks and method/member names in arrows
- If pImpl pattern is used, merge interface class and impl into one block and name it e.g. `SoaMaster(Impl)`

---

## Supported Features

**Colors:** Apply via `classDef`/`class` (fill/stroke HEX), `linkStyle` (stroke HEX, width, dasharray)

**Shapes:** Rectangle `[Label]`, circle `((Label))`, stadium `([Label])`, diamond `{Label}`,
subroutine `[[Label]]`, parallelogram `/Label/`

**Arrows:** Solid `-->`, dotted `-.->`, thick `==>`, open `--o`. Customize with `linkStyle`

**Directions:** `TD` (top-down), `LR` (left-right), `RL` (right-left), `BT` (bottom-top)

**Text:** Bold `**text**`, italic `_text_`, line breaks `<br/>` (labels only). No per-label font
size/underline/family

---

## Required Theme Configuration

Every Mermaid diagram MUST include this init directive on the first line:

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal'}}}%%
```

- **CRITICAL:** Use `base` theme for automatic GitHub light/dark mode adaptation
- **REQUIRED:** Arial 13px normal weight prevents text cutoff and ensures readability across platforms
- **REQUIRED:** Use `classDef` with fill and stroke only — no explicit `color:#` text color
- **CRITICAL:** Avoid explicit `color:#` specifications as they conflict with automatic theme adaptation
- **NEVER** use explicit text color specifications that override automatic theme adaptation

---

## Dark/Light Mode Compatibility

These diagrams must render professionally across three targets:

1. **VS Code** — Markdown Preview Enhanced with GitHub light and dark preview themes
2. **Prince PDF** — exported from Markdown Preview Enhanced (light background)
3. **GitHub** — viewed in both light and dark mode

### Design Principles

- For **hierarchical diagrams**, use alpha-transparent fills (8-digit hex `#RRGGBBAA`) on container
  subgraphs. This produces automatic bi-directional hierarchy: darker inward on light backgrounds,
  lighter inward on dark backgrounds
- For **flat diagrams** and **innermost nodes**, use solid medium-tone fills (45–75% lightness)
- Do NOT specify `color:#` in any `classDef` — let the renderer handle text color
- Use HEX values only — 6-digit (`#RRGGBB`) or 8-digit (`#RRGGBBAA`). No CSS color names, no
  `rgba()`, no gradients
- Stroke colors should use higher alpha than their corresponding fill for border definition
- All solid fills must have sufficient contrast against both `#ffffff` (light) and `#0d1117` (dark)
  backgrounds

### Recommended Base Fill Colors (Non-Hierarchical Diagrams)

Medium tones that adapt automatically to both light and dark themes:

| Purpose | Fill | Stroke |
|---------|------|--------|
| Primary (blue) | `#4a90d9` | `#2c6cb0` |
| Success (green) | `#34a870` | `#1e8850` |
| Warning (orange) | `#e8a838` | `#c08828` |
| Danger (red) | `#d06050` | `#a84838` |
| Purple | `#8e6aad` | `#6e4a8d` |
| Blue-gray | `#5a7a90` | `#3e5e74` |

---

## Hierarchical Diagram Color System

Many diagrams require up to **four levels of nesting** using subgraphs. Use the alpha-transparent
palette below to create clear visual hierarchy that adapts to both light and dark backgrounds.

### How It Works

Container subgraphs use **alpha-transparent fills** (8-digit hex: `#RRGGBBAA`) on a single
base color. The renderer composites these against the page background, automatically creating
bi-directional hierarchy:

- **Light mode (white background):** Low-alpha outer containers composite to near-white;
  higher-alpha inner containers composite to progressively darker shades — subtle to prominent
- **Dark mode (dark background):** Low-alpha outer containers composite to near-black;
  higher-alpha inner containers composite to progressively lighter shades — subtle to prominent

Innermost nodes (Level 4) use **full-opacity solid fills** at ~50–55% lightness, ensuring they
stand out against both backgrounds.

### Universal Hierarchy Palette

Container subgraphs (Levels 1–3) share a base blue-gray with increasing alpha. Level 4 nodes
are fully opaque:

| Level | Role | Fill | Stroke | Alpha |
|-------|------|------|--------|-------|
| **L1** | Outermost container | `#5888a833` | `#3c6c904D` | 20% / 30% |
| **L2** | Section container | `#5888a866` | `#3c6c908C` | 40% / 55% |
| **L3** | Module container | `#5888a8A6` | `#3c6c90CC` | 65% / 80% |
| **L4** | Nodes (primary) | `#5888a8` | `#3c6c90` | 100% |

**Effective appearance after compositing on light (`#ffffff`) and dark (`#0d1117`) backgrounds:**

| Level | On Light BG | On Dark BG |
|-------|-------------|------------|
| **L1** | `#dee7ee` (very light, subtle) | `#1c2934` (very dark, subtle) |
| **L2** | `#bccfdc` (light) | `#2b4151` (dark) |
| **L3** | `#92b1c6` (medium-light) | `#3e5e75` (medium-dark) |
| **L4** | `#5888a8` (solid, prominent) | `#5888a8` (solid, prominent) |

### Additional Node Variants (Level 4)

Use these for semantic differentiation among nodes at the innermost level:

| Variant | Fill | Stroke | Use For |
|---------|------|--------|---------|
| Blue (default) | `#5888a8` | `#3c6c90` | Standard components |
| Green | `#58a888` | `#3c906c` | Services, APIs, success states |
| Orange | `#c49858` | `#a87c3c` | Queues, async, warnings |
| Red | `#b07070` | `#944c4c` | Errors, critical paths |
| Purple | `#8a78a8` | `#6e5c90` | Auth, security, policies |

### Applying Hierarchy Styles

Use `style` directives for subgraph containers and `classDef`/`class` for nodes:

```text
%% Subgraph fills — alpha-transparent hex (8-digit #RRGGBBAA)
style L1_id fill:#5888a833,stroke:#3c6c904D,stroke-width:2px
style L2_id fill:#5888a866,stroke:#3c6c908C,stroke-width:2px
style L3_id fill:#5888a8A6,stroke:#3c6c90CC,stroke-width:2px

%% Node fills — fully opaque, use classDef/class
classDef L4 fill:#5888a8,stroke:#3c6c90,stroke-width:2px
class N1,N2,N3 L4
```

### Common Mistakes

> **CRITICAL:** `classDef`/`class` does NOT style subgraphs — it only styles nodes.
> Subgraphs MUST use `style` directives. If you only define `classDef` and `class`,
> nodes will be colored but subgraph containers will render with the default transparent
> background — invisible against the document background.

---

## Subgraph Structure for Hierarchy

Use nested `subgraph` blocks to represent containment. Each subgraph gets a quoted title label.

```text
graph TD
    subgraph L1["Platform"]
        subgraph L2["Service"]
            subgraph L3["Module"]
                N1["Component A"]
                N2["Component B"]
            end
        end
    end
```

Rules:

- **Maximum 4 levels** of nesting (3 subgraph levels + nodes)
- Keep subgraph titles short (under 25 characters)
- Place `style` directives for subgraphs **after the graph definition**, not inside subgraph blocks
- Use descriptive but concise subgraph IDs (e.g., `L2_api`, `L3_auth`)

---

## Edge and Connector Styling

### Edge Labels

- Keep labels under 25 characters
- Use abbreviations: "Config" for "Configuration", "Exec" for "Execution", "Auth" for "Authentication"
- Use `|label text|` syntax on the arrow: `A -->|validates| B`

### linkStyle Directives

Apply `linkStyle` using 0-based edge index (order edges appear in the source):

```text
linkStyle 0 stroke:#4a90d9,stroke-width:2px
linkStyle 1 stroke:#d06050,stroke-width:2px,stroke-dasharray:5 5
```

### Recommended Edge Colors

| Type | Stroke Color | Style |
|------|-------------|-------|
| Data flow | `#4a90d9` | solid, 2px |
| Control flow | `#34a870` | solid, 2px |
| Error/fallback | `#d06050` | dashed, 2px |
| Async/eventual | `#e8a838` | dashed, 2px |
| Weak/optional | `#8a8a8a` | dotted, 1px |

---

## Text Length Optimization

- **CRITICAL:** Keep node labels concise to prevent text cutoff in diagram boxes
- **REQUIRED:** Remove file extensions from names in diagrams (e.g., `execution_pipeline` not `execution_pipeline.groovy`)
- **REQUIRED:** Truncate long edge labels (e.g., `QT-SECURITY/ECG2_SECURITY_EXEC` not `QT-SECURITY/ECG2_SECURITY_EXECUTION`)
- **REQUIRED:** Shorten descriptive text while preserving meaning
- Recommended: Keep node text under 30 characters per line, edge labels under 25 characters
- Use abbreviations for common terms: "Config", "Exec", "Auth", "Mgmt", "Svc", "DB"
- Break long text into multiple lines using `<br/>` tags when needed
- Prioritize essential information over complete names in constrained diagram space

---

## Object Ownership Diagrams

Use member names as link text, not legend descriptions.

Copy the legend below once per document, then create ownership diagrams as needed:

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal'}}}%%
graph LR
    A[Class A]
    B[Class B]
    C[Class C]
    D[Class D]

    A -->|member_b_| B
    A -->|member_d_| D
    A --o|member_c_| C
    D -.->|borrowed_q_| Q

    linkStyle 0 stroke:#5a5a5a,stroke-width:2px
    linkStyle 1 stroke:#5a5a5a,stroke-width:2px
    linkStyle 2 stroke:#4a90d9,stroke-width:2px
    linkStyle 3 stroke:#5a5a5a,stroke-width:2px

    classDef default fill:#c8d5e2,stroke:#7898b0,stroke-width:1px
```

### 3 Ownership Dimensions (visual encoding: line style + arrow end + color)

1. **Lifetime Management** — destruction responsibility:
   - **Owns:** `unique_ptr` / `shared_ptr` / manual delete → solid lines
   - **Borrows:** raw pointer / `weak_ptr` → dotted lines (`-.->`)

2. **Object Lifetime** — creation patterns:
   - **Permanent:** init-time, program lifetime → arrow end `>`
   - **Temporary:** request/task creation → circle end `o`

3. **Type Polymorphism** — member type analysis:
   - **Non-polymorphic:** concrete type, no virtual dispatch → dark gray stroke (`#5a5a5a`)
   - **Polymorphic:** base/interface type with virtual functions → blue stroke (`#4a90d9`)

**Analysis:** Find member variables (pointers, references, smart pointers, containers). Check
change/creation patterns. Exclude PImpl without runtime dispatch.

---

## Flat Peer Subgraph Diagrams

For diagrams where **multiple peer-level subgraphs** each represent a distinct semantic domain
(not nested hierarchy), use **color-coordinated groups**: the subgraph container uses the base
color at **40% alpha** (`66` suffix), and child nodes use the same base color at **100% opacity**.

### Color-Coordinated Group Palette

Each group shares a base color. The container gets alpha-transparent fill; nodes get solid fill:

| Group | Container Fill | Container Stroke | Node Fill | Node Stroke |
|-------|---------------|-----------------|-----------|-------------|
| Green | `#34a87066` | `#1e88508C` | `#34a870` | `#1e8850` |
| Blue | `#4a90d966` | `#2c6cb08C` | `#4a90d9` | `#2c6cb0` |
| Orange | `#e8a83866` | `#c088288C` | `#e8a838` | `#c08828` |
| Purple | `#8e6aad66` | `#6e4a8d8C` | `#8e6aad` | `#6e4a8d` |
| Blue-gray | `#5a7a9066` | `#3e5e748C` | `#5a7a90` | `#3e5e74` |
| Red | `#d0605066` | `#a848388C` | `#d06050` | `#a84838` |

### Flat Peer Template

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal'}}}%%
flowchart TD
    subgraph GRP_A["Group A"]
        A1["Node A1"]
        A2["Node A2"]
    end

    subgraph GRP_B["Group B"]
        B1["Node B1"]
        B2["Node B2"]
    end

    A1 -->|connects| B1
    A2 -.->|fallback| B2

    style GRP_A fill:#34a87066,stroke:#1e88508C,stroke-width:2px
    style GRP_B fill:#4a90d966,stroke:#2c6cb08C,stroke-width:2px

    classDef grpA fill:#34a870,stroke:#1e8850,stroke-width:2px
    classDef grpB fill:#4a90d9,stroke:#2c6cb0,stroke-width:2px
    class A1,A2 grpA
    class B1,B2 grpB

    linkStyle 0 stroke:#34a870,stroke-width:2px
    linkStyle 1 stroke:#4a90d9,stroke-width:2px,stroke-dasharray:5 5
```

Rules:

- **Every subgraph** MUST have a `style` directive with alpha-transparent fill
- Node `classDef` uses the **same base color** as its parent subgraph container (at 100% opacity)
- Edge `linkStyle` colors should match the source or target subgraph color family
- Maximum **6 color groups** per diagram for visual clarity

---

## Flat Peer Subgraph Diagrams — Border Only

A lighter variant of flat peer subgraphs where **only colored borders** differentiate groups —
no background fills on containers or nodes. This produces a minimal, clean appearance where
nodes inherit the page background and colored strokes provide all semantic grouping.

**When to use:** Prefer border-only when diagrams have many nodes and filled backgrounds feel
visually heavy, or when maximum text readability is needed (text sits directly on the page
background).

### Text Color for Transparent Fills

With `fill:none`, the Mermaid renderer cannot auto-compute a contrasting text color because
there is no opaque fill to measure against. Text defaults to dark, which is unreadable on dark
backgrounds. The solution: **explicitly set a balanced mid-tone text color** that provides
sufficient contrast against both light (`#ffffff`) and dark (`#0d1117`) backgrounds.

| Variable | Value | vs White | vs Dark | Role |
|----------|-------|----------|---------|------|
| `primaryTextColor` | `#6b7b8b` | 4.35:1 | 4.35:1 | Subgraph titles, default text |
| `color` in `classDef` | `#6b7b8b` | 4.35:1 | 4.35:1 | Node label text |

> **Exception to the "no explicit `color:#`" rule:** The border-only variant REQUIRES explicit
> `color:#6b7b8b` in `classDef` and `primaryTextColor` in `themeVariables` because transparent
> fills break the renderer's automatic text color computation. This is the only variant where
> explicit text color is permitted.

### Border-Only Group Palette

Each group is identified by stroke color alone. Containers and nodes share the same stroke.
Fills are explicitly `none` (transparent):

| Group | Container Stroke | Node Stroke | Stroke Width |
|-------|-----------------|-------------|--------------|
| Green | `#34a870` | `#34a870` | 2px |
| Blue | `#4a90d9` | `#4a90d9` | 2px |
| Orange | `#e8a838` | `#e8a838` | 2px |
| Purple | `#8e6aad` | `#8e6aad` | 2px |
| Blue-gray | `#5a7a90` | `#5a7a90` | 2px |
| Red | `#d06050` | `#d06050` | 2px |

### Border-Only Flat Peer Template

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal', 'primaryTextColor': '#6b7b8b'}}}%%
flowchart TD
    subgraph GRP_A["Group A"]
        A1["Node A1"]
        A2["Node A2"]
    end

    subgraph GRP_B["Group B"]
        B1["Node B1"]
        B2["Node B2"]
    end

    A1 -->|connects| B1
    A2 -.->|fallback| B2

    style GRP_A fill:none,stroke:#34a870,stroke-width:2px,color:#6b7b8b
    style GRP_B fill:none,stroke:#4a90d9,stroke-width:2px,color:#6b7b8b

    classDef grpA fill:none,stroke:#34a870,stroke-width:2px,color:#6b7b8b
    classDef grpB fill:none,stroke:#4a90d9,stroke-width:2px,color:#6b7b8b
    class A1,A2 grpA
    class B1,B2 grpB

    linkStyle 0 stroke:#34a870,stroke-width:2px
    linkStyle 1 stroke:#4a90d9,stroke-width:2px,stroke-dasharray:5 5
```

Rules:

- **All fills are `none`** — both subgraph `style` directives and node `classDef` use `fill:none`
- **All `classDef` MUST include `color:#6b7b8b`** — required for node label readability on both
  light and dark backgrounds (transparent fills break auto text color computation)
- **All subgraph `style` directives MUST include `color:#6b7b8b`** — required for subgraph title
  readability; `primaryTextColor` alone does not override subgraph label color
- **The init directive MUST include `'primaryTextColor': '#6b7b8b'`** — covers edge labels and
  any other text not styled by `classDef` or subgraph `style`
- Stroke colors use the **medium-tone base colors** (45–75% lightness) for visibility on both
  light and dark backgrounds
- Edge `linkStyle` colors should match the source or target group's stroke color
- Maximum **6 color groups** per diagram for visual clarity

---

## Basic Template (Non-Hierarchical, No Subgraphs)

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal'}}}%%
graph LR
    A["Component A"] -->|data flow| B["Component B"]
    B -.->|fallback| C["Component C"]
    C ==>|critical| D["Component D"]

    classDef primary fill:#4a90d9,stroke:#2c6cb0,stroke-width:2px
    classDef secondary fill:#34a870,stroke:#1e8850,stroke-width:2px
    class A,B primary
    class C,D secondary

    linkStyle 0 stroke:#4a90d9,stroke-width:2px
    linkStyle 1 stroke:#d06050,stroke-width:2px,stroke-dasharray:5 5
    linkStyle 2 stroke:#34a870,stroke-width:3px
```

## Hierarchical Template (4 Levels)

```text
%%{init: {'theme':'base', 'themeVariables': {'fontFamily': 'Arial, sans-serif', 'fontSize': '13px', 'fontWeight': 'normal'}}}%%
graph TD
    subgraph L1["Outer Container"]
        subgraph L2["Section"]
            subgraph L3["Module"]
                N1["Node A"]
                N2["Node B"]
            end
        end
    end

    N1 -->|connects| N2

    style L1 fill:#5888a833,stroke:#3c6c904D,stroke-width:2px
    style L2 fill:#5888a866,stroke:#3c6c908C,stroke-width:2px
    style L3 fill:#5888a8A6,stroke:#3c6c90CC,stroke-width:2px

    classDef L4 fill:#5888a8,stroke:#3c6c90,stroke-width:2px
    class N1,N2 L4
```

---

## PDF Export

Use **Markdown Preview Enhanced → Puppeteer (Chromium)** for PDF export. Puppeteer renders
in a full Chromium browser, so Mermaid blocks execute natively — no pre-rendering needed.

- **Do NOT use Prince for documents containing Mermaid diagrams.** Prince is a CSS-to-PDF
  engine that does not execute JavaScript; Mermaid blocks appear as raw text
- The Puppeteer export renders against a **light background** by default — alpha-transparent
  container fills (`#RRGGBBAA`) will composite as the light-mode palette
- All three rendering targets (VS Code preview, GitHub, Puppeteer PDF) use Chromium engines,
  ensuring consistent Mermaid rendering across all outputs

---

## Limitations

- **HEX only** — 6-digit (`#RRGGBB`) or 8-digit with alpha (`#RRGGBBAA`). No CSS color names,
  no `rgba()`, no HTML/CSS/SVG/gradients/external styles
- **8-digit hex** (`#RRGGBBAA`) required for hierarchy containers — supported by all modern
  browsers, GitHub's Mermaid renderer, VS Code (Chromium), and Prince 12+
- Global theme via `%%{init: { "themeVariables": {...} }}%%` for font configuration
- **NO inline comments** (`%%comment%%`) in GitHub renderer — use separate comment blocks if needed
- **MUST** have blank line after closing ` ``` ` fence before any following text
- Subgraph nesting is limited to 3 levels deep (+ nodes = 4 visual levels)
- `linkStyle` indices are 0-based and count edges in source order
- `style` directive is the most reliable way to color subgraphs (preferred over `classDef` + `class` for subgraphs)
- GitHub, VS Code Markdown Preview Enhanced, and Prince may have minor rendering differences — test across all three targets
