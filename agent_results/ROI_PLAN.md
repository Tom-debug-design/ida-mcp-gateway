# ROI Plan — API resale

Job ID: unknown  
Generated: 2026-01-11T20:32:31Z

## Input
- Goal: Lag ROI-plan som kan gi inntekt raskt
- Timeframe: 48 timer (plan) / 30 dager (første inntekt)
- Market: Global
- Budget: 0
- Legal scope: EU
- Risk tolerance: Lav
- Target customer: Små SaaS/solopreneurs
- Deliverable: ROI plan

---

## 1) Tilbud (det vi selger)

**Produkt:** "AI-funksjon inn i ditt SaaS"

**Kjerne:** Du tilbyr en "white-label AI-backend" som kunden kan kalle via API (chat/support/analyse),
slik at de slipper å bygge LLM-stack selv.

**Pakker (enkelt og brutalt):**
- Starter: €49/mnd — 5k requests/mnd, basis-modell, standard rate limit
- Pro: €149/mnd — 25k requests/mnd, logging + enklere "guardrails"
- Agency: €399/mnd — 100k requests/mnd, 3 kunder/prosjekter, prioritet + SLA-light

**Upsell (lav friksjon):**
- Setup-fee: €199–€499 for integrasjon (engangs)
- Custom prompt + tone: €99/mnd
- Compliance/PII mode: €99/mnd (EU-friendly)

---

## 2) MVP i repoet (hva du faktisk trenger)

**Minimum:**
- 1 endpoint: `/chat` eller `/support_reply`
- API key auth
- Logging: request_count + basic cost estimate
- Simple dashboard/CSV export (senere)

**Teknisk stack forslag (lav friksjon):**
- FastAPI + uvicorn
- 1 provider (OpenAI først)
- SQLite eller JSON-logg (start billig)

---

## 3) Første 3 kundekanaler (0-budsjett)

1. LinkedIn: SaaS-founders + indiehackers (målrettet DM)
2. Cold e-post: finn 30 små SaaS (1–10 ansatte) → enkel pitch
3. Discord/communities: indie/saas communities → post "done-for-you AI API"

---

## 4) Outreach-melding (kort)

**Subject:** "Jeg kan gi deg AI-support i produktet ditt på 24t"

Hei {{navn}},

Jeg lager en liten "white-label AI API" som du kan plugge inn i ditt SaaS for chat/support,
uten å bygge LLM-stack selv.

Hvis du vil, kan jeg sette opp en demo i ditt miljø på 24–48t.

Vil du at jeg sender en 2-min demo + pris?

---

## 5) 72t plan (praktisk)

- Dag 1: Velg 1 usecase (support reply) + endpoint + API key
- Dag 2: Lag demo landing + 20–30 outreach (LinkedIn/e-post)
- Dag 3: Book 2 calls, tilby "setup-fee" + månedspakke

---

## 6) Suksesskriterie

- 30 kontakter → 3 svar → 1 betalt pilot
- Mål: €49–€149 første måned → bevis → skaler outreach
