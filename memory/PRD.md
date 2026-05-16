# PerceptAI — Landing Page PRD

## Original Problem Statement
Build ONLY the landing page for PerceptAI (perception infrastructure for autonomous AI agents).

**Stack (locked by user):** Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui patterns + Framer Motion.
**Theme:** Dark-only (#050505), single accent #00FF85. Fonts: Bebas Neue / Inter / JetBrains Mono.
**Style:** Glassmorphism, 1px borders, generous whitespace, premium SaaS (Linear / Vercel / Browser Use vibe).
**Goal:** Static marketing site only — no LLM/backend integration. User will export to GitHub and deploy on Vercel.

## Architecture
```
/app/frontend/
├── app/
│   ├── layout.tsx            # next/font: Bebas, Inter, JetBrains Mono
│   ├── page.tsx              # composes landing sections
│   └── globals.css           # tailwind + design tokens + bg-grid/glow/noise utils
├── components/
│   ├── ui/
│   │   ├── button.tsx        # cva-driven variants (primary / secondary / ghost / outline)
│   │   └── card.tsx
│   └── landing/
│       ├── navbar.tsx
│       ├── hero.tsx
│       ├── terminal-card.tsx     # animated mock execution logs
│       ├── ticker.tsx
│       ├── section-heading.tsx
│       ├── how-it-works.tsx
│       ├── comparison.tsx
│       ├── pricing.tsx
│       ├── footer.tsx
│       └── motion-utils.tsx      # FadeUp + stagger variants
├── lib/utils.ts                  # cn() helper
├── tailwind.config.ts            # accent token, font vars, ticker/pulse keyframes
├── next.config.js
├── tsconfig.json
└── package.json                  # script: yarn start → next dev -p 3000 -H 0.0.0.0
```

## Implemented
- Sticky glass navbar with scroll-state pill and mobile sheet
- Full-viewport hero: grid overlay + radial green glow + noise, sequential Framer Motion entrance, CTA pair, metrics strip
- Floating terminal glass card with live-streaming mock execution log
- Infinite scrolling brand ticker (CSS keyframes, edge mask)
- "How It Works" — 3-column stagger with iconography and code snippets
- Capability comparison table (PerceptAI vs DIY stack vs Legacy obs) with check/dash/string cells
- Three-tier pricing with highlighted Pro plan and per-card stagger
- Footer with brand block, link columns, social icons, status indicator
- Fully responsive (mobile-first), max-width 1280, data-testid coverage on all interactive elements

## What's Deferred (P1/P2 backlog)
- P1: Testimonial / customer logo wall section with quotes
- P1: Interactive product demo embed (video or live sandbox)
- P1: SEO — sitemap, robots.txt, OG image asset
- P2: Light theme toggle (currently dark-only by spec)
- P2: Animated number counters on metrics row
- P2: i18n for hero copy
- P2: Blog / changelog pages

## Notes for handoff
- Supervisor `frontend` program runs `yarn start` → `next dev -p 3000 -H 0.0.0.0`.
  When deploying to Vercel locally, scripts already include `build` and `serve`.
- `REACT_APP_BACKEND_URL` left in `frontend/.env` (unused — kept for Emergent preview ingress compatibility).
- No backend usage; FastAPI `/app/backend` is untouched and irrelevant to this landing page.
