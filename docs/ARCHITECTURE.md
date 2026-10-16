# Production architecture – Team Selection Platform

## 1. Target architecture
```
HR system (Workday/SAP) ─┐
Project/PSA (Jira, Planview) ─┼─► Ingestion (CDC/API, Airflow) ─► Raw zone (object storage, immutable)
Skills/LMS, calendars ───┘                                     │
                                                    Airflow: validate, normalise (taxonomy service), dedupe
                                                               ▼
                                   Curated warehouse (Postgres / Snowflake)  ──► reject/quarantine tables + DQ reports
                                                               ▼  (nightly + event-driven refresh of availability)
                         Serving store: Postgres (+ pgvector later) / Redis cache of eligible-employee views
                                                               ▼
 Manager UI / Teams bot ─► API gateway (SSO/OIDC, rate-limit) ─► Recommendation service (FastAPI, stateless)
                                                               │  deterministic: filter → score → assemble
                                                               ├─► Explanation service ─► LLM gateway (Anthropic / Azure) 
                                                               └─► Audit store (requests, results, decisions, model/prompt versions)
```
Principle: **batch (Airflow) prepares data; real-time (FastAPI) only reads it.** The scoring engine is a pure library, so it can be reused in batch simulations (what-if staffing, backtesting).

## 2. Scalability
- API is stateless → horizontal scaling on Kubernetes (HPA on CPU/latency). Today's full-table load per request is replaced by SQL pre-filtering (role, availability, experience as indexed predicates) and a cached in-memory snapshot refreshed on ETL completion.
- Thousands–tens of thousands of employees: scoring is O(candidates × requirements) in-process, milliseconds; no ML in the critical path.
- LLM call is the slow part (seconds): make it async/optional (`explain_with_ai=false`, or return the result first and stream the explanation); cache by hash of the payload.
- Taxonomy (technologies/roles/aliases) moves to a managed table with versioning and a review queue for unknown terms (the ETL currently rejects them).
- Later: semantic skill matching with embeddings (e.g. "Flink" ≈ "Spark Streaming") as an *additional* soft signal, still explained deterministically.

## 3. Data security & GDPR
- Legal basis & purpose limitation: staffing decisions based on legitimate interest/employment contract; DPIA required (profiling of employees). Document that the tool supports, not replaces, human decisions (GDPR Art. 22: no solely automated decision with significant effect → manager approval step is mandatory and logged).
- Data minimisation: only fields needed for matching; no sensitive categories (health, union, ethnicity, age, gender) are ingested or used. Test fairness: monitor score distributions by location/seniority/part-time status.
- LLM receives pseudonymised payload (employee_id, no names/emails). Contract with LLM vendor: no training on data, EU region, DPA signed; or run via private endpoint (Azure OpenAI / Bedrock / Vertex) in the EU.
- Access control: SSO + RBAC (managers see only own org units / need-to-know), column-level security for HR fields, row-level security by business unit; secrets in Vault/KMS; encryption at rest (TDE/KMS) and in transit (TLS/mTLS).
- Data subject rights: employees can request access to their profile and the recommendations they appeared in; retention policy (e.g. recommendations 12–24 months), erasure/anonymisation job; audit log immutable.

## 4. Observability
- Metrics (Prometheus/OpenTelemetry): request latency p50/p95, eligible-count per request, empty-team rate, LLM latency/cost/fallback rate, ETL duration, reject ratio per entity.
- Data quality: Great Expectations/dbt tests in Airflow (freshness, uniqueness, ranges, % unknown technologies); DAG fails → alert (Slack/PagerDuty) and the previous snapshot keeps serving.
- Tracing: request_id propagated API → engine → LLM; structured JSON logs without PII.
- Business KPIs: acceptance rate (manager decision == recommendation), override reasons, time-to-staff; drift alerts when acceptance drops.

## 5. AI governance
- Deterministic core: eligibility and scores are reproducible from (request, data snapshot, engine version) – stored in the audit table. LLM output never feeds back into scores.
- Guardrails: constrained prompt, pseudonymised JSON in, validation of output (must reference all members), template fallback, no tool use, prompt injection surface minimal (free text from users is not placed in the prompt – only structured fields).
- Versioning & change control: engine weights, taxonomy, prompt and model id are versioned; changes go through review + offline backtesting on past staffing decisions; golden-set regression tests on explanations.
- Human oversight: recommendation + "alternatives" + mandatory manager decision; overrides with comments are collected and used to recalibrate weights (not to train on personal data without review).
- Risk classification: employment-related AI is high-risk under the EU AI Act → transparency to employees, human oversight, logging, bias testing, conformity documentation; involve works council/legal where required.

## 6. Reliability
- Idempotent, re-runnable ETL; transactional swap of the serving data (already: single-transaction rebuild); blue/green tables in production.
- Quality gate before publish; stale-data banner in API (`/health` exposes snapshot age).
- LLM is a soft dependency: timeouts, retries with backoff, circuit breaker, fallback template → core recommendation always available.
- HA: ≥2 API replicas across AZs, managed Postgres with PITR backups, RPO ≤ 24h for warehouse / ≤ 5 min for audit store, RTO ≤ 1h. SLO e.g. 99.5% availability, p95 < 1.5 s without LLM.

## 7. Deployment
- Containers (Docker) → Kubernetes/AKS/EKS; Helm charts; Airflow on managed service (MWAA/Cloud Composer) or Helm chart.
- CI/CD (GitHub Actions/GitLab CI): lint (ruff), types (mypy), unit + contract tests, data-quality tests on synthetic dataset, image scan, SBOM; deploy dev → staging (anonymised prod copy) → prod with canary + automatic rollback.
- IaC (Terraform), environment parity, config via env/secret store, feature flags for LLM explanations and new scoring versions (shadow mode: compute both, compare).

## 8. Roadmap
1. MVP (this repo) → 2. real sources + taxonomy service + auth + Postgres → 3. UI for managers (what-if, constraints editing, compare candidates) → 4. calibration from decision feedback, embeddings for skill similarity, fairness dashboard → 5. integration with PSA tools (auto-booking after approval).
