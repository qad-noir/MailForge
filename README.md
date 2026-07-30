# MailForge

MailForge is a production-oriented MVP for permission-based email campaigns through the
SendGrid Web API. It deliberately refuses to treat unknown consent as permission and is not
designed for scraped, purchased, harvested, or unverified lists.

## Acceptable use

Use this application only for recipients who explicitly opted in and whose consent source and
date can be recorded. Do not use mailbox probing, list scraping, address harvesting, purchased
lists, or unsolicited bulk email. Operators remain responsible for applicable privacy,
anti-spam, and data-retention law.

## Architecture and guarantees

FastAPI and Typer share services backed by async SQLAlchemy and PostgreSQL. A short-lived
scheduler creates unique campaign-recipient rows. Sender workers claim rows using
`FOR UPDATE SKIP LOCKED`. The queue boundary is an abstract interface so another backend can
replace PostgreSQL without changing campaign rules.

Campaign rate control serializes allocation of each campaign's next send slot under a row lock.
This spreads submissions steadily and coordinates multiple workers, but each allocation adds a
database transaction. Redis token buckets are the recommended upgrade at very high throughput.

Delivery is practical at-least-once, not mathematically exactly-once. Database uniqueness stops
duplicate queue entries and claims stop simultaneous work. A process can still die after
SendGrid accepts a request but before the database commits its message ID; retrying then can
duplicate a message because SendGrid Mail Send has no general idempotency key. Keep stale
timeouts conservative, monitor attempt records, and reconcile ambiguous provider submissions.

## Local setup

Copy `.env.example` to `.env`, replace both local secrets, and then run:

```bash
docker compose up --build
```

The API is at `http://localhost:8000`; OpenAPI is at `/docs`. Administrative requests require
`Authorization: Bearer <ADMIN_API_TOKEN>`.

For a local Python environment:

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Start processes separately:

```bash
python -m app.workers.sender --worker-id worker-1 --batch-size 100 --poll-interval 2
python -m app.workers.scheduler
python -m app.workers.scheduler --loop --interval 30
```

The one-shot scheduler exits after due campaigns and is appropriate for cron.

## CLI examples

```bash
mailforge contacts import leads.csv --email-column email --consent-column consent_status
mailforge campaign create --name "August Product Update" --subject "Your August update" \
  --html-template app/templates/example.html --text-template app/templates/example.txt \
  --from-name "Company Name" --from-email updates@example.com --timezone Africa/Lagos \
  --rate 3000 --batch-size 100
mailforge campaign preview CAMPAIGN_ID --recipient test@example.com
mailforge campaign test-send CAMPAIGN_ID --recipient test@example.com
mailforge campaign schedule CAMPAIGN_ID --start-at "2026-08-01 09:00"
mailforge campaign status CAMPAIGN_ID
mailforge campaign pause CAMPAIGN_ID
mailforge campaign resume CAMPAIGN_ID
mailforge campaign cancel CAMPAIGN_ID
mailforge campaign report CAMPAIGN_ID --export report.csv
```

Every imported row must contain `opted_in` in its consent column. Suppressed and unsubscribed
contacts are not reactivated by import. Both campaign templates must contain the literal
`{{ unsubscribe_url }}` placeholder.

## Quality checks

```bash
ruff format --check .
ruff check .
mypy app
pytest
```

Tests mock provider calls and never contact SendGrid.

## Railway deployment

Create one PostgreSQL database and three services from this repository. Share all environment
variables between services and use the database's async-compatible `DATABASE_URL`.

- API: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Worker: `python -m app.workers.sender`
- Cron: `python -m app.workers.scheduler`, scheduled every minute

Run `alembic upgrade head` as a pre-deploy/release command. Configure SendGrid Event Webhook to
POST to `https://<api-domain>/webhooks/sendgrid/events`, enable signed event webhooks, and place
the public verification key in `SENDGRID_WEBHOOK_VERIFICATION_KEY`. Configure a custom domain
and HTTPS before distributing unsubscribe links.

Required production variables are `DATABASE_URL`, `APP_BASE_URL`, `APP_ENV=production`,
`ADMIN_API_TOKEN`, `UNSUBSCRIBE_SIGNING_SECRET`, `SENDGRID_API_KEY`,
`SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME`, and
`SENDGRID_WEBHOOK_VERIFICATION_KEY`. The remaining settings are documented in `.env.example`.

## Current limitations and extension points

- Webhook events are persisted synchronously for a quick, bounded batch; a future inbox queue can
  acknowledge first and process separately.
- The PostgreSQL rate gate is campaign-level. A future `RateLimiter` adapter should add
  per-domain token buckets.
- Audience selection is currently all active opted-in contacts; segmentation belongs in a
  dedicated audience specification.
- Suppression synchronization is local-first; provider suppression reconciliation should be
  added operationally.
- Authentication is a single administrative bearer token. Use OIDC/RBAC and tenant isolation
  before multi-user hosting.
- The initial migration creates the complete metadata schema; future revisions should use
  explicit Alembic operations.
