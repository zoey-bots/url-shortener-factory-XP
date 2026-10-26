# URL Shortener Service: Specification

## 1. Overview
Build a small HTTP service that shortens long URLs, redirects visitors from the short code to the original URL, and tracks basic click analytics. The service must be runnable with a single command and ship with its own tests.

## 2. Technical Constraints
- Language: Python 3.12
- Framework: FastAPI
- Storage: SQLite (single file, path configurable via `DATABASE_PATH`)
- Configuration via environment variables only (`BASE_URL`, `DATABASE_PATH`, `API_KEYS`)
- No containers: must run directly on the host from a Python virtual environment
- Dependencies pinned in `requirements.txt`
- `uvicorn app.main:app --port 8000` starts the service
- Tests use `pytest`

## 3. Functional Requirements

### FR-1 Create a short link
`POST /api/links`

Request body (JSON):
- `url` (string, required)
- `custom_alias` (string, optional)
- `expires_at` (string, optional)

Success: `201 Created` with `code`, `short_url`, `url`, `created_at`, `expires_at`.

### FR-2 Redirect
`GET /{code}` redirects to the original URL with `302`.
- Unknown code: `404`
- Expired link: `410`

### FR-3 Code generation
- Auto-generated codes are 7 characters, base62 (`a-z A-Z 0-9`).
- Codes must be unique.
- Codes must not be guessable from creation order (no sequential IDs).

### FR-4 URL validation
- Only `http` and `https` schemes are accepted.
- Maximum URL length is 2048 characters.
- Invalid input returns `422` with a clear error message.
- The service must not allow links that point back to itself.

### FR-5 Custom aliases
- 3 to 32 characters: letters, digits, hyphen, underscore.
- An alias that is already taken returns `409 Conflict`.
- Aliases must not collide with reserved paths (`api`, `docs`, `health`).

### FR-6 Link details
`GET /api/links/{code}` returns the link's metadata.

### FR-7 Delete a link
`DELETE /api/links/{code}` returns `204`. The short URL stops working afterward.

### FR-8 Authentication
- All `/api/*` endpoints require an `X-API-Key` header matching one of the configured keys.
- Missing or invalid key returns `401`.
- Redirects (`GET /{code}`) and `GET /health` are public.

### FR-9 Click analytics (stretch)
Every successful redirect is recorded. `GET /api/links/{code}/stats` returns:
- total clicks
- clicks per day for the last 7 days
- top 5 referrers

Recording a click must not noticeably slow down the redirect.

### FR-10 Rate limiting
The link creation endpoint should be rate limited to prevent abuse. Exceeding the limit returns `429`.

### FR-11 Duplicate URLs
Submitting a URL that has already been shortened should be handled sensibly.

### FR-12 Health check
`GET /health` returns `200` with `{"status": "ok"}`.

## 4. Non-Functional Requirements
- Redirects should be fast.
- The service must be safe to run with several workers.
- Errors return JSON in a consistent shape.
- No secrets committed to the repository.

## 5. Deliverables
1. Source code in a clear module structure
2. Automated test suite (unit and API-level)
3. `requirements.txt` with pinned versions
4. `README.md` with setup, configuration, and API examples
5. `.env.example`

## 6. Acceptance Criteria
- From a clean checkout, creating a venv and running `pip install -r requirements.txt` succeeds.
- `uvicorn app.main:app --port 8000` starts the service with no manual fixes.
- `pytest` passes from a clean checkout.
- Every functional requirement above has at least one test that would fail if the behavior were removed.
- The README instructions work exactly as written.

## 7. Out of Scope
- User accounts, registration, or a web UI
- Custom domains
- Link editing after creation
- Distributed deployment
