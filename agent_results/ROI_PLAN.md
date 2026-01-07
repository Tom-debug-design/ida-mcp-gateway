# ROI PLAN — IDA

## Mål
Bygge 3 parallelle inntektsmotorer med lavest mulig initial innsats og raskest mulig validering.

## Prioritet
1. API Resale
2. Market Signal Aggregation
3. Arbitrage Engine

---

## Engine 1 — API Resale (START HER)

### Formål
Pakk og videreselg strukturerte finance- og nyhetsdata via eget API.

### Repo-aksjoner
- Opprett mappe: /engines/api_resale/
- Definer API-wrappere rundt eksterne datakilder
- Logg alle forespørsler og responser

### KPI
- Tid til første betalende bruker
- API-kall per dag
- Kost vs inntekt

---

## Engine 2 — Market Signal Aggregation

### Formål
Aggregere globale markedssignaler til ett normalisert datasett.

### Repo-aksjoner
- Opprett mappe: /engines/signal_aggregator/
- Ingest data fra flere markeder
- Normaliser output til standard format

---

## Engine 3 — Arbitrage Engine

### Formål
Identifisere prisavvik mellom markeder.

### Repo-aksjoner
- Opprett mappe: /engines/arbitrage/
- Detekter kryss-marked-avvik
- Logg alle funn
