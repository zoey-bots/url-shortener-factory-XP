# URL Shortener Service

A small FastAPI + SQLite service that shortens long HTTP(S) URLs, redirects
short codes with `302`, and records click analytics. It runs directly on the
host from a Python 3.12 virtual environment (no containers) and ships with a
unit + API test suite.

- `POST /api/links` — create a short link (authenticated)
- `GET /{code}` — public redirect
- `GET /api/links/{code}` — link metadata (authenticated)
- `GET /api/links/{code}/stats` — click analytics (authenticated)
- `DELETE /api/links/{code}` — delete the link and its analytics (authenticated)
- `GET /health` — public health check

## Requirements

- Python **3.12**
- A POSIX shell or Windows `cmd.exe` / PowerShell
- No Docker, no external services, no outbound network calls

All dependencies are pinned in `requirements.txt`, including transitive
packages.

## Setup

Run these commands from the repository root.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation for the current session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Windows (cmd.exe)

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### POSIX (Linux / macOS)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The `pip install -r requirements.txt` step succeeds from a clean checkout
without any manual fixes.

## Configuration

The service reads **only** these three process environment variables. There
are no config files, CLI flags, or extra settings.

| Variable | Default | Meaning |
| --- | --- | --- |
| `BASE_URL` | `http://localhost:8000` | Public origin used to build `short_url` values and to detect self-links. |
| `DATABASE_PATH` | `./links.db` | SQLite database file. Relative paths are resolved from the process CWD. |
| `API_KEYS` | *(empty)* | Comma-separated API keys. Whitespace is trimmed and empty entries are ignored. Empty configuration **fails closed**: every `/api/*` request is rejected with `401`. |

Set them in the same shell that starts `uvicorn`.

PowerShell:

```powershell
$env:BASE_URL = "http://localhost:8000"
$env:DATABASE_PATH = ".\links.db"
$env:API_KEYS = "replace-with-a-long-random-key"
```

cmd.exe:

```bat
set BASE_URL=http://localhost:8000
set DATABASE_PATH=.\links.db
set API_KEYS=replace-with-a-long-random-key
```

POSIX:

```bash
export BASE_URL="http://localhost:8000"
export DATABASE_PATH="./links.db"
export API_KEYS="replace-with-a-long-random-key"
```

Generate a key without committing it:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`API_KEYS` may hold several keys, e.g. `key-one,key-two`; each key has its own
rate-limit budget. Only a SHA-256 hash of the key is stored in SQLite.

`.env.example` is a **template only**. The application does **not** load
`.env` files automatically. Export the variables in your shell or process
manager before starting the server, and never commit real secrets.

## Run the service

From the repository root, with the virtual environment active and the
environment variables exported:

```bash
uvicorn app.main:app --port 8000
```

The service listens on `http://localhost:8000`. Interactive docs are at
`/docs` and `/redoc` (the OpenAPI document is at `/openapi.json`); those paths
are reserved so they can never become short-code aliases.

### Multiple workers

The SQLite layer is safe across processes on one host:

```bash
uvicorn app.main:app --port 8000 --workers 4
```

All workers must receive the same `DATABASE_PATH`, `BASE_URL` and `API_KEYS`.
On Windows, uvicorn starts workers with the spawn method; export the variables
before launching rather than relying on shell changes made afterwards.

## Run the tests

```bash
pytest
```

or, if the `pytest` script is not on `PATH`:

```bash
python -m pytest
```

The suite uses `pytest.ini` (`pythonpath = .`, `testpaths = tests`). Every test
creates its own temporary SQLite database and a fresh application instance,
so no server, network access, or environment variables are required. The
suite includes isolated unit tests for the validation/configuration/storage
helpers and real API-level tests through `fastapi.testclient` with the
application lifespan entered.

## API conventions

All non-success responses use one JSON envelope:

```json
{"error": {"code": "nonblank-machine-code", "message": "nonblank explanation"}}
```

`code` is stable and machine-readable; `message` is human-readable. This
applies to `401`, `404`, `405`, `409`, `410`, `422`, `429`, `500` and every
other error status.

Every `/api/*` request requires:

```http
X-API-Key: <one of the configured keys>
```

Missing or invalid keys return `401` **before** routing or body validation,
including for unknown `/api/*` paths. Redirects and `GET /health` are public.

In the examples below, `$API_KEYS` is a shell variable containing the key
(use `$env:API_KEYS` in PowerShell and the literal key in cmd.exe). On
Windows, invoke `curl.exe` to use the built-in curl rather than the PowerShell
`curl` alias.

## Endpoints and examples

### Health check (public)

```bash
curl -s http://localhost:8000/health
```

```json
{"status": "ok"}
```

### Create a short link — `POST /api/links`

Body fields:

- `url` — required JSON **string**, absolute `http`/`https` URL, at most 2048 characters.
- `custom_alias` — optional string, 3–32 ASCII letters/digits/`-`/`_`.
- `expires_at` — optional ISO 8601 string with a timezone offset.

```bash
curl -i -X POST http://localhost:8000/api/links \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEYS" \
  -d '{"url":"https://example.com/some/long/path"}'
```

```json
{
  "code": "aB3xY9Q",
  "short_url": "http://localhost:8000/aB3xY9Q",
  "url": "https://example.com/some/long/path",
  "created_at": "2026-10-26T12:00:00+00:00",
  "expires_at": null
}
```

With an alias and an expiry:

```bash
curl -i -X POST http://localhost:8000/api/links \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEYS" \
  -d '{"url":"https://example.com/sale","custom_alias":"spring-sale","expires_at":"2026-12-31T23:59:59+00:00"}'
```

PowerShell equivalent:

```powershell
$headers = @{ "X-API-Key" = $env:API_KEYS }
$body = @{ url = "https://example.com/some/long/path" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/links `
  -Headers $headers -ContentType "application/json" -Body $body
```

The success status is `201`. `created_at` and `expires_at` are returned in UTC
with `+00:00`; `expires_at` is `null` when omitted. The original URL text is
preserved exactly as submitted.

### Redirect — `GET /{code}` (public)

```bash
curl -i http://localhost:8000/aB3xY9Q
```

```http
HTTP/1.1 302 Found
location: https://example.com/some/long/path
```

- Unknown code → `404` (`not_found`).
- Expired code → `410` (`link_expired`).
- Every successful `302` records exactly one click.
- `404` and `410` never record a click.

### Link metadata — `GET /api/links/{code}`

```bash
curl -s http://localhost:8000/api/links/aB3xY9Q \
  -H "X-API-Key: $API_KEYS"
```

Returns the same fields as creation. Metadata remains readable for expired
links (only the redirect returns `410`). Unknown/deleted codes return `404`.

### Click analytics — `GET /api/links/{code}/stats`

```bash
curl -s http://localhost:8000/api/links/aB3xY9Q/stats \
  -H "X-API-Key: $API_KEYS"
```

```json
{
  "total_clicks": 4,
  "clicks_per_day": [
    {"date": "2026-10-20", "clicks": 0},
    {"date": "2026-10-21", "clicks": 0},
    {"date": "2026-10-22", "clicks": 1},
    {"date": "2026-10-23", "clicks": 0},
    {"date": "2026-10-24", "clicks": 0},
    {"date": "2026-10-25", "clicks": 1},
    {"date": "2026-10-26", "clicks": 2}
  ],
  "top_referrers": [
    {"referrer": "https://news.example/story", "clicks": 2},
    {"referrer": "direct", "clicks": 1},
    {"referrer": "https://blog.example/post", "clicks": 1}
  ]
}
```

- `total_clicks` counts all recorded clicks for the link.
- `clicks_per_day` is always exactly the last 7 **UTC calendar days**, oldest
  first, including today, with zero-filled days.
- `top_referrers` is the top 5 by click count, descending (ties by referrer
  text). A missing or blank `Referer` header is bucketed as `direct`.

### Delete — `DELETE /api/links/{code}`

```bash
curl -i -X DELETE http://localhost:8000/api/links/aB3xY9Q \
  -H "X-API-Key: $API_KEYS"
```

Returns `204` with an empty body. The code and its analytics are removed, so
the short URL and stats return `404` afterwards. Deleting an unknown code
returns `404`.

### Rate limit example

After 60 authenticated creation requests for one key within a rolling 60
seconds, further creation requests return:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 37
```

```json
{"error": {"code": "rate_limited", "message": "Rate limit exceeded. Try again later."}}
```

## Behaviour and policy details

### Short codes

Auto-generated codes are exactly 7 characters from the base62 alphabet
(`a-z`, `A-Z`, `0-9`) drawn from Python's `secrets` CSPRNG. They are not
derived from sequence IDs or creation order. Codes are unique (enforced by the
primary key); a collision is retried with a new random code, and 10 failed
attempts return `500 code_generation_failed`.

### URL validation

- The JSON value must be a string; numbers, booleans, objects, arrays and
  `null` are rejected with `422` (no coercion).
- Only absolute `http` and `https` URLs are accepted.
- Maximum length is 2048 characters.
- The URL must have a hostname and, when a port is present, a valid port.
- Embedded credentials (`user:pass@host`) are rejected.
- Whitespace and control characters are rejected.
- Validation is structural (`urllib.parse`), not prefix matching. The original
  text is stored and redirected unchanged.
- A URL whose normalized hostname equals the `BASE_URL` hostname is rejected,
  regardless of scheme, port, letter case or a trailing dot. A URL that merely
  contains `localhost` in its path/query is allowed.

### Custom aliases and reserved paths

- 3–32 characters, ASCII letters, digits, `-`, `_` only.
- Reserved case-insensitively: `api`, `docs`, `health`, `redoc`,
  `openapi.json` (the dot is already outside the allowed character set).
- An alias already in use returns `409 alias_taken`; a requested alias is
  never silently ignored or replaced.
- Alias uniqueness is exact/case-sensitive at the database level.

### Duplicate URLs

Submitting a URL that was already shortened **without** an alias creates a
new, independent random code. Each such link keeps its own analytics. If a
`custom_alias` is supplied, that exact alias is used or the request fails with
`409` when taken.

### Expiration

`expires_at` must be an ISO 8601 timestamp with a timezone offset
(`Z` or `+HH:MM`). Naive or malformed timestamps return `422`. Past timestamps
are accepted: creation returns `201`, and the redirect immediately returns
`410`. Values are normalized to UTC. Metadata stays readable after expiry.

### Rate limiting

- `POST /api/links` is limited to **60 authenticated requests per rolling 60
  seconds per API key**.
- The check-and-insert is one SQLite `BEGIN IMMEDIATE` transaction, so
  concurrent threads/workers cannot overshoot the limit.
- Events live in SQLite; restarting the process does **not** reset the window.
- Exceeding the limit returns `429` with a numeric `Retry-After` header (whole
  seconds) and the standard error envelope.
- Unauthenticated (`401`) requests never reach the limiter.
- Health checks, redirects, metadata and stats are unrestricted. Only key
  identity hashes are stored, never raw keys.

### Authentication

`X-API-Key` must exactly match one of the keys in `API_KEYS`. Keys are
compared in constant time. Empty `API_KEYS` fails closed. Every `/api/*`
path — including unknown paths — is authenticated before routing and body
parsing.

## SQLite, persistence and multi-worker limits

- One SQLite file at `DATABASE_PATH`; relative paths resolve from the process
  working directory.
- WAL journal mode, `busy_timeout`/connection timeout of 5 seconds, foreign
  keys enabled, and `synchronous = NORMAL`.
- Every operation opens a short-lived connection and closes it explicitly.
  Create, delete, redirect+click and rate-limit check are wrapped in
  transactions; redirect reads and the click insert share one short write
  transaction so a delete/recreate race cannot charge a click to the wrong
  link.
- Schema creation uses `IF NOT EXISTS` inside an immediate transaction, so
  several worker processes can start simultaneously.
- Links, clicks and rate-limit windows persist across restarts in the same
  file. Deleting the database file resets all of them.
- WAL permits concurrent readers with one writer. This design is for a single
  host with a local disk; SQLite on a network filesystem is not supported, and
  the service is not a distributed deployment.

## Project layout

```text
app/            FastAPI application and SQLite persistence (do not edit here)
tests/          Unit and API tests (all use temporary databases)
pytest.ini      pytest configuration
requirements.txt  Pinned runtime + test dependencies
.env.example    Environment-variable template (not auto-loaded)
README.md       This document
```

## Security notes

- No real secrets are committed; `.env.example` contains placeholders only.
- Raw API keys are never stored in SQLite and never echoed in responses.
- Error messages never include stack traces or internal exception details.
- Redirects do not fetch the destination URL and make no external network
  calls.
- The service is intended for trusted localhost/single-host use, not as a
  hardened public multi-tenant deployment.
