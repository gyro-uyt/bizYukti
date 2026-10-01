# BizYukti: Demand. Space. Opportunity.

A three-sided local marketplace, built from the BizYukti UI/UX PRD v2.0.

- **Residents** publish and support requests for businesses their area is missing.
- **Owners** list vacant shops, offices, plots and warehouses, and see which local demand each one fits.
- **Businesses** see where verified demand and available space overlap, with competition and access side by side.

Every match and opportunity explains itself in plain language.

> The bundled data is synthetic and illustrative (Gwalior). Area statistics such as footfall, competitors and access are demo values.

## Quick start

### Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:3000
```

The API container runs migrations, seeds the demo data if the database is empty, and starts on `:8000`. The worker and scheduler run alongside it.

### Without Docker

Requirements: Postgres 16 with PostGIS 3.4, pgvector and pg_trgm; Redis 7; Python 3.12; Node 22.

```bash
cp .env.example .env
cd backend && pip install -r requirements.txt && alembic upgrade head && python -m app.seed --reset
uvicorn app.main:app --reload --port 8000        # API
python -m app.worker.worker                       # background jobs (or set TASKS_EAGER=true)
cd ../frontend && npm install && npm run dev      # web on :3000, proxies /api and /media to API_ORIGIN
```

### Demo personas

These work while `OTP_DEV_ECHO=true`: the one-time code is shown on screen.

| Persona | Sign in with | What to look at |
|---|---|---|
| Resident Asha | 9800000001 | R1 nearby demand, 202 reward points, supported requests |
| Owner Rajesh | 9800000002 | P1 with an 850 sq ft shop whose top demand is pharmacy; P3 matches |
| Business Neha (CareWell Pharmacy) | 9800000003 | B1 ranked pharmacy areas, B2 Gol Pahadiya, B3 map |
| Admin | admin@bizyukti.in (email) | A1 review queue, KPIs, team inbox |

The flagship demand is "Pharmacy near Gol Pahadiya": 184 verified supporters, 12 matched spaces and 3 interested businesses.

## Architecture

```
Browser ── Next.js 16 (App Router, React 19, Leaflet) ──/api,/media rewrite──▶ FastAPI (Python 3.12)
                                                                                 ├─ Postgres 16 + PostGIS + pgvector + pg_trgm
                                                                                 ├─ Redis (rate limits, RQ queue)
                                                                                 └─ RQ worker + scheduler (matching, rewards unlock, notifications, freshness)
Production: Caddy (automatic HTTPS) ─▶ web:3000, api:8000
```

### Backend (`backend/app`)

- **API:** 58 endpoints under `/api/v1`.
  - Auth is phone or email OTP with rate limits and lockout. Sessions use a short-lived access token plus a rotating httpOnly refresh cookie.
- **Geo:** PostGIS geography columns with GiST indexes.
  - A demand belongs to exactly one area, so area aggregates never double count.
- **Trust rules:**
  - Support counts only from verified residents within 5 km, one per device.
  - Risk scoring holds suspicious demand for review.
  - Photos are checked for blur (variance of Laplacian) and duplicates (dHash), and location metadata is stripped.
  - Owners re-confirm availability every 30 days.
  - Ownership documents and KYB go through the admin queue, and documents are kept in private storage.
- **Rewards:** points stay pending until the action is verified, and can be reversed. Redemptions issue voucher codes.
- **AI:** optional. Request wording, categorisation and similar-request detection use Anthropic when `ANTHROPIC_API_KEY` is set, otherwise built-in rules.
- **Tests:** `make test` runs 15 pytest tests covering units, auth and end-to-end flows. Alembic `check` reports no schema drift.

### Frontend (`frontend/src`)

- **Design system:** `app/globals.css` implements the PRD tokens.
  - Colours: blue #0004ED, pink #FB2462, orange #FD9833 and green #7AF444, with accessible ink variants for text.
  - Geometry: 0–8px radius and 44–52px controls.
  - Type: the PRD scale, set in Anek Latin (self-hosted).
- **Brand:** the logo and hero motif are original artwork (a pin teardrop with ripple rings). No third-party assets are used.
- **Accessibility:**
  - Focus rings, a skip link and labelled map regions and pins.
  - Shapes plus text, not colour alone: circles for demand and diamonds for space.
  - Focus-trapped modals, live toasts and reduced-motion support.

## PRD traceability

| PRD screen | Route | Screen file | Main endpoints |
|---|---|---|---|
| R1 Resident home | `/home` | `screens/home.tsx` (ResidentHome) | `GET /demands`, `/rewards`, `/demands/mine` |
| R2 Request flow (4 steps) | `/demands/new` | `screens/demand-new.tsx` | `POST /demands/assist`, `POST /demands` (409 duplicate prompt), `/geo/reverse` |
| R3 Request detail | `/demands/[id]` | `screens/demand-detail.tsx` | `GET /demands/{id}`, `POST/DELETE /support`, `/share`, `/interest`, `/fulfil`, `/close` |
| R4 Rewards | `/rewards` | `screens/rewards.tsx` | `GET /rewards`, `POST /rewards/redeem` |
| P1 Owner home | `/home` (owner role) | `screens/home.tsx` (OwnerHome) | `GET /properties/mine`, `POST /properties/{id}/confirm` |
| P2 Add property (5 steps) | `/properties/new`, `/properties/[id]/edit` | `screens/property-form.tsx` | `POST/PATCH /properties`, media upload, `/suggest-type`, `/geo/demand-context`, `/publish`, `/verification` |
| P3 Demand matches | `/properties/[id]/matches` | `screens/property-matches.tsx` | `GET /properties/{id}/matches`, `/matches/{id}/offer`, `POST /inquiries` |
| B1 Opportunity home | `/home` (business role) | `screens/home.tsx` (BusinessHome) | `GET /opportunities` |
| B2 Area detail | `/opportunities/[areaId]` | `screens/opportunity.tsx` | `GET /opportunities/areas/{id}`, `/saved`, `POST /inquiries` (space or market brief) |
| B3 Opportunity map | `/map` | `screens/map.tsx` | `GET /map/layers` |
| A1 Admin review | `/admin` | `screens/admin.tsx` | `/admin/queue`, `/admin/verifications/{id}/decide`, `/document`, `/admin/stats` |

Supporting screens: landing `/`, sign-in `/login`, onboarding `/onboarding`, explore `/explore`, post chooser `/post`, space detail `/properties/[id]`, messages `/inquiries` and `/inquiries/[id]`, saved `/saved`, notifications `/notifications`, profile `/profile`, and legal `/legal/privacy` and `/legal/terms`.

## KPIs (PRD section 14)

`/admin` → KPIs shows the north-star metric, the section 14 KPIs, 30-day retention by role, totals, and client events from the last 7 days. The north star is verified demands with at least one matched space and one interested business.

Client events go through an allow-list at `POST /events`.

## Environment variables

See `.env.example`; every variable is commented there. `NEXT_PUBLIC_*` values and `API_ORIGIN` are baked into the web build, so the Dockerfiles take them as build arguments.

## Deploying to production

```bash
cp .env.example .env   # set ENV=production, SECRET_KEY, SITE_DOMAIN, POSTGRES_PASSWORD, SMS/SMTP, S3, tiles
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Migrations run once in the `migrate` service. Seeding is refused when `ENV=production`.

### Launch checklist

- [ ] `ENV=production`, a long random `SECRET_KEY`, and `OTP_DEV_ECHO=false`.
- [ ] Production cookies are Secure, which requires HTTPS through Caddy.
- [ ] A real SMS provider (DLT-registered sender and templates for India) and SMTP configured.
- [ ] `STORAGE_BACKEND=s3`, with separate public and private buckets for ownership documents.
- [ ] A commercial map tile provider set in `NEXT_PUBLIC_MAP_TILE_URL`. The OpenStreetMap public tile servers aren't for production traffic under their tile usage policy.
- [ ] `ADMIN_EMAILS` set to your team, and `NEXT_PUBLIC_DEMO_ACCOUNTS=0`.
- [ ] Legal review of `/legal/*`, which is template text, including against India's DPDP Act 2023. Appoint a grievance officer.
- [ ] Replace the synthetic area statistics (footfall, competitors, access) with real data sources before using them for business decisions.
- [ ] Postgres backups, uptime monitoring on `/health` and `/api/v1/ready`, and optionally OpenTelemetry (`pip install -r requirements-otel.txt`).

## Verification status of this build

- **Passing:**
  - Backend: 15/15 tests.
  - Frontend: `tsc --noEmit` is clean and `next build` succeeds for all 23 routes.
  - Smoke test against the seeded database:
    - All routes return 200 and the API and media work through the web proxy.
    - OTP sign-in and refresh-cookie rotation work.
    - Share previews show live supporter counts.
- **Partially done:** headless-browser visual QA. Landing, sign-in, R1 and R3 rendered at desktop and mobile sizes without errors.
- **Open item:** in one automated run, the first input on `/demands/new` wasn't found in time. Check the R2 flow manually in a browser before launch.

## Roadmap

These are deliberately out of scope for v1:

- Native mobile apps.
- Payments for promoted listings.
- Hindi localisation (copy is centralised in the screens for translation).
- Real footfall and competition data feeds.
