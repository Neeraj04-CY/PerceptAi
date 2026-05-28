# PerceptAI — Product Requirements

## Original Problem Statement
Build a premium landing page for PerceptAI (perception infrastructure for autonomous AI agents) followed by a comprehensive, dark-mode dashboard. Stack: Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui patterns + Framer Motion + Recharts. Connects to external Railway backend at `https://perceptai-production.up.railway.app/api/v1/` for sessions, stats, and usage.

**Theme:** Dark-only (`#050505`), single accent `#00FF85`. Fonts: Bebas Neue / Inter / JetBrains Mono. Glassmorphism, 1px white/10 borders, generous whitespace.

## Architecture
```
/app/frontend/
├── app/
│   ├── layout.tsx                    # global fonts + metadata
│   ├── page.tsx                      # landing
│   ├── signin/, signup/              # auth pages with animated terminals
│   └── dashboard/
│       ├── layout.tsx                # Sidebar + Topbar + CommandPaletteProvider
│       ├── page.tsx                  # Run Task
│       ├── overview/                 # Command center
│       ├── analytics/                # Recharts trends + outcomes + quota
│       ├── sessions/ + [id]/         # List + detailed timeline
│       ├── scheduled/                # localStorage CRON drafts
│       ├── playbook/                 # Template gallery
│       ├── keys/                     # API keys table
│       └── settings/                 # Profile, preferences, notifications, security, danger
├── components/
│   ├── ui/                           # button, glass-card, page-header, metric-card, switch, input, etc.
│   ├── landing/                      # hero, ticker, comparison, pricing, footer
│   ├── auth/                         # animated terminal + auth forms
│   └── dashboard/
│       ├── sidebar.tsx + topbar.tsx
│       ├── command-palette*.tsx      # Cmd+K global palette
│       ├── analytics/, overview/, sessions/, scheduled/, playbook/, keys/, run/, settings/
└── lib/
    ├── api.ts                        # External Railway API client
    ├── auth.ts                       # JWT token + cookie sync
    ├── motion.ts                     # Framer Motion variants
    ├── scheduled-tasks.ts            # localStorage CRUD
    ├── playbook-templates.ts         # mock template catalog
    └── settings.ts                   # localStorage UserSettings
```

## Implemented
**Landing (Phase 1):**
- Sticky glass navbar, hero with grid + radial green glow, animated terminal card
- Brand ticker, How It Works, comparison table, 3-tier pricing, footer
- Fully responsive, data-testid coverage on every interactive element

**Auth (Phase 2):**
- /signin and /signup with animated terminal logs, JWT token storage in localStorage + cookie

**Dashboard (Phase 3):**
- Sidebar (collapsible), Topbar (runtime indicator, env badge, Cmd+K search, notifications)
- /dashboard — Run Task orchestrator (instruction input + execution timeline + terminal logs)
- /dashboard/overview — Command center with progress bars, activity, quota
- /dashboard/sessions — List view backed by Railway API with skeleton/error/empty states
- /dashboard/sessions/[id] — Detail page: timeline, charts, JSON viewer, AI summary
- /dashboard/scheduled — Schedule drafts with localStorage persistence
- /dashboard/playbook — Template gallery cards
- /dashboard/keys — API keys table with copy/revoke + create modal
- /dashboard/analytics (Feb 2026) — Recharts area chart, donut quota, outcomes split, recent sessions
- /dashboard/settings (Feb 2026) — Profile (display name, email, account ID), Preferences (env, density, beta), Notifications (5 toggles), Security (2FA, sessions), Danger zone (clear local data, sign out)
- Global Cmd+K palette with recent sessions, navigation, actions

## Backlog (P1)
- Replace localStorage mocks (Scheduled Tasks, Playbook templates, Recent Sessions cache, Settings) with real backend endpoints once Railway supports them
- Real billing/upgrade flow for Overview "Upgrade →" links
- Wire `density` and `defaultEnv` settings to actually affect tables/forms across dashboard

## Backlog (P2)
- Testimonial / logo wall on landing
- Interactive product demo embed
- SEO sitemap, robots.txt, OG image
- 2FA enrollment QR + recovery codes flow
- Light theme toggle (currently dark-only)
- Animated number counters on metrics
- Blog / changelog pages

## Notes for handoff
- Supervisor `frontend` runs `yarn start` → `next dev -p 3000 -H 0.0.0.0`. After significant changes to `.next` directory, restart frontend: `sudo supervisorctl restart frontend`.
- Auth: JWT stored in both `localStorage` AND `document.cookie` (`perceptai_token`) — keep these in sync.
- DO NOT modify `lib/api.ts` URL or auth token shape without confirming with user.
- All settings persist to `localStorage["perceptai_settings"]`. Email mirrored in `localStorage["perceptai_email"]` (set by auth flow).
- No backend usage in `/app/backend`; this is a frontend-only repo connected to external Railway backend.
