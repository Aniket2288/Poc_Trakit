# Week 2 demo guide

One section per demo topic: what to **show**, what to **say**, and where the code is.
Paths are clickable in most editors.

## How to run everything

```bash
# Option A: all in Docker (API, worker, beat, Postgres, Redis, MailHog)
docker compose up --build              # API http://localhost:8000, emails http://localhost:8025

# Option B: locally (your Postgres on 5011, your Redis on 6379)
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload                                        # terminal 1
celery -A app.worker.celery_app worker --loglevel=INFO --pool=solo   # terminal 2 (emails print here)
cd frontend && npm run dev                                           # terminal 3, then http://localhost:5173
pytest                                                               # 136 tests
```

---

## 1. End to end: create issue → assign → worker sends email → audit log entry

**Show** (UI with the Network tab open, worker log beside it):
1. Issues tab → New issue → **Create issue** → `POST /projects/{id}/issues` → 201.
2. Open it → choose an assignee → `POST /issues/{id}/assign` → 200.
3. The worker log (or MailHog) shows `EMAIL to=... You were assigned TRK-1` and `result=sent`.
4. Audit log tab → `issue.created`, then `issue.assigned` with before `{"assignee_id": null}` and after.

**Each hop:**

| Hop | What happens | Code |
|---|---|---|
| Browser → API | `fetch` with `Authorization: Bearer <token>` | `frontend/src/api.js` (`assignIssue`) |
| Middleware | Request id assigned, query counter started | `app/core/middleware.py` |
| Router | `require_role(admin, member)` → 403 for viewers | `app/api/issues.py` |
| Service | Checks the assignee is in the workspace, changes the row, writes the audit row, **commits once** | `app/services/issue_service.py:103` |
| After commit | Puts `send_assignment_email(<audit id>)` on Redis | `issue_service.py:115`, `app/services/jobs.py` |
| Worker | Takes the job, loads the event, checks it isn't stale, sends once | `app/worker/tasks.py`, `app/services/notification_service.py:22` |
| Email | Console log locally; SMTP → MailHog in Docker | `app/services/email_service.py` |

**Say:** "The job is enqueued only *after* the commit. Before it, the worker could pick up the job and
not find the assignment yet. The job carries the audit event's id, so it describes one specific
assignment, and it can tell when it's out of date."

---

## 2. The state machine

**Show:** open an issue in Backlog, click **done** → red message:
`422 Cannot move an issue from Backlog to Done. Allowed next: In Progress.` Then click **in_progress** → works.

**Code:** `ALLOWED_TRANSITIONS` at `app/services/issue_service.py:17`, `check_transition` at `:32`.

```
Backlog ⇄ In Progress ⇄ Review → Done
               ↑                  │
               └──── reopen ──────┘
```

**Say:**
- "The rules are one dictionary: for each status, the statuses you may go to next. Anything else
  raises `InvalidTransitionError`, which the global handler turns into 422 with `invalid_transition`."
- "**Why 422 and not 400?** The JSON is valid. The request is understood but breaks a business rule."
- "**Why in the service?** It's a rule of the business, not of HTTP. A background job or an import
  script changing status gets the same check."
- "The status can only change through `/transition`. `PATCH /issues/{id}` doesn't accept `status`,
  so there's no way around it."
- "A rejected move writes no audit row, because nothing was committed."
- Tests: `tests/test_issues.py` checks all 16 status pairs.

---

## 3. N+1: find it in the logs, fix it, count again

Full write-up with the SQL: **`docs/n-plus-one.md`**.

**Show:**
```bash
python -m scripts.count_issue_list_queries --show-sql
```
To show the "before" live, put back the pre-fix repository file, run the script, then restore it:
`git checkout fb5166c -- app/repositories/issue_repository.py` → run → `git checkout HEAD -- app/repositories/issue_repository.py`.
Or run the API with `LOG_SQL=true` and watch one `SELECT labels` line per issue, all with the same `request_id`.

| Issues | Before | After |
|---|---|---|
| 5 | 9 | 3 |
| 25 | 29 | 3 |
| 50 | 54 | 3 |

**Say:** "Lazy loading ran one query per issue for its labels. `selectinload` loads all labels in one
`IN (...)` query, and `joinedload` brings assignee and project in through a JOIN. A test fails if
the count ever grows with the number of issues again."
Code: `app/repositories/issue_repository.py:77`.

---

## 4. Pagination: why offset

**We use offset** (`?limit=20&offset=40`), with a stable sort (`ORDER BY <column>, id`).

| | Offset | Cursor ("give me 20 after this one") |
|---|---|---|
| Jump to page 7 | Yes | No, only next/previous |
| Total count ("41–60 of 300") | Easy | Extra query or none |
| Sort by any column | Easy | Each sort needs its own cursor format |
| Deep pages | Slower: Postgres still reads the skipped rows | Fast at any depth (uses an index) |
| Rows added or removed while paging | Can skip or repeat a row | Stable |

**Say:** "An issue tracker shows 'page 3 of 15' and lets you sort by priority or due date. Lists are
per workspace, so they stay small, and offset's weaknesses don't bite. For an infinite activity
feed with millions of rows, I'd use a cursor on `(created_at, id)`. Adding `id` to every sort means
equal values can't make pages overlap."

---

## 5. The worker: receiving jobs, crashes, retries, idempotency

**How a job arrives:** `send_assignment_email.delay(id)` writes a message to a Redis list. The worker
(`celery -A app.worker.celery_app worker`) blocks on that list, takes a message, and runs the function.

**If it crashes mid-job:** `task_acks_late=True` (`app/worker/celery_app.py:12`) means the message is
only removed **after** the job finishes. A crash leaves it unacknowledged, so Redis hands it to a worker
again. `worker_prefetch_multiplier=1` means a worker holds only one job at a time.

**Retries:** `RETRY_POLICY` (`app/worker/tasks.py:14`): only for temporary errors (mail server down,
connection lost), waiting 2s, 4s, 8s … up to 10 min with random jitter, 5 times at most. A bug (say a
`KeyError`) is not retried, because retrying wouldn't fix it.

**Why idempotency matters:** because of acks_late and retries, **a job can run more than once**.
Without protection, a user would get two or three identical emails. `send_once`
(`notification_service.py:67`):
1. insert a `sent_emails` row with a unique key (`assignment:<audit id>`, or `overdue-digest:<user>:<date>`)
2. if the key exists → already sent → skip
3. send, then commit. If sending fails, roll back, so the retry can send.

**Honest limit:** a crash *after* sending but *before* commit sends twice. That's "at least once".
Exactly-once isn't possible with an outside mail server; the window is tiny.

**Stale jobs:** if the issue is reassigned while the job waits, the old job sees the assignee changed
and skips (`notification_service.py:34`). The new assignment has its own job.

**Daily digest:** `celery beat` adds `send_overdue_digest` to the queue at 09:00 IST (`beat_schedule`).
Run exactly **one** beat process, or the digest is queued twice (it still sends once, thanks to the key).

Tests: `tests/test_worker.py` (14 tests: duplicates, stale jobs, failure then retry, the digest, the config).

---

## 6. CORS: what the browser actually does

- The UI runs on `http://localhost:5173` and the API on `http://127.0.0.1:8000`. Different port means
  a **different origin**, so the browser applies the same-origin policy.
- For a "simple" request the browser sends it, then **refuses to let JavaScript read the response**
  unless it carries `Access-Control-Allow-Origin: http://localhost:5173`.
- Our requests send `Authorization` and JSON, which are not "simple", so the browser first sends a
  **preflight**: `OPTIONS /issues` with `Origin` and `Access-Control-Request-Headers: authorization,content-type`.
  The API answers with the allowed origin, methods and headers. Only then is the real request sent.
  You can see these `OPTIONS` requests in the Network tab.
- **CORS is enforced by the browser, not the server.** curl and Postman ignore it. It stops other
  websites' JavaScript from using a logged-in user's browser against our API. It is not authentication.
- Code: `app/main.py` (`CORSMiddleware`, origins from `CORS_ORIGINS`). We list exact origins, never
  `*`, and `X-Request-ID` and `Retry-After` are exposed so the UI can read them.

---

## 7. Deployment (not deployed this week, by agreement)

What it would look like, so you can explain it:

```
Internet ──HTTPS:443──▶ Nginx ──HTTP──▶ api:8000 (uvicorn)
                          │               worker, beat ──▶ Redis, Postgres
                          └── serves nothing else; the UI is on Vercel/Netlify
```

- **Nginx's job:** the only thing open to the internet. It terminates TLS, redirects HTTP to HTTPS,
  limits body size (`client_max_body_size 6m`, matching our 5 MB upload limit), applies timeouts, and
  forwards requests to uvicorn with `X-Forwarded-For $remote_addr` (overwriting what the client sent).
- **Where TLS terminates:** at Nginx (Let's Encrypt certificate). Nginx → API is plain HTTP inside the
  private Docker network, which nobody outside can reach.
- **Environment variables:** a `.env` file on the server (never in Git; `.env.example` lists the names)
  is read by Docker Compose (`env_file` and `${...}`) and passed into each container. `app/core/config.py`
  reads them through pydantic-settings, with types checked at startup, so a missing `JWT_SECRET_KEY`
  stops the app from starting instead of failing later.
- **Rolling back a bad deploy:** each release is an image tagged with its git commit. To roll back,
  point Compose at the previous tag and `docker compose up -d`. Migrations: release in two steps, so
  the old code still works with the new schema (add columns first, remove them in a later release),
  or run `alembic downgrade -1` if the new migration is the problem.
- **Real client IP:** `--proxy-headers` makes uvicorn trust `X-Forwarded-For`, so rate limiting sees
  the user's IP, not Nginx's. Uvicorn must trust it **only from Nginx**. Otherwise anyone can send a
  fake header and dodge the rate limit (we saw exactly this while testing).

---

## 8. Transactions

**Where the boundary is:** one request = one session (`get_db`, `app/core/database.py:25`). The
**service** calls `db.commit()` exactly once, at the end of a successful operation. Repositories only
`flush()` (send SQL, get ids) and never commit.

**On an exception:** the service never reaches `commit()`. `get_db` closes the session, which rolls
back everything, including the audit row. That's why a change and its audit entry are all-or-nothing
(test: `test_failed_change_writes_no_audit_row`).

**Race conditions and how they're handled:**
1. **Two issues created at once in the same project.** Both could read "last number is 4" and both
   take 5. Fixed with one atomic `UPDATE projects SET issue_counter = issue_counter + 1 ... RETURNING`
   (`issue_repository.py:24`): Postgres locks the row, so the second waits and gets 6. A
   `UNIQUE (project_id, number)` constraint is the safety net.
2. **The same refresh token used twice at once.** `get_for_update` takes a row lock
   (`refresh_token_repository.py:19`), so only one rotation wins.
3. **Two signups with the same email.** The check-then-insert has a gap; the unique index catches the
   second one, and the service turns the `IntegrityError` into 409 (`auth_service.py:37`).
4. **Two workers sending the same email.** The unique `idempotency_key`: the second insert waits for
   the first and then fails.

**Fact to know:** Postgres `now()` is the transaction's **start** time. Every row written in one
transaction gets the same `created_at`. (It bit us in the tests; edit-history timestamps now come
from Python.)

---

## 9. Async in FastAPI

- **`def` endpoint:** FastAPI runs it in a **threadpool** (about 40 threads), so a slow call blocks only
  that thread. All our endpoints are `def`, because SQLAlchemy here is synchronous (psycopg).
- **`async def` endpoint:** runs **on the event loop itself**. One loop serves every request, so
  anything blocking inside it (a sync DB query, `time.sleep`, `requests.get`, reading a big file, argon2
  hashing) **freezes every other request** until it finishes.
- **The rule:** use `async def` only if everything inside is awaited (an async DB driver, `httpx.AsyncClient`).
  Otherwise use `def`. Mixing a sync DB call into `async def` is the classic mistake.
- **When to use a threadpool by hand:** inside an `async def`, wrap blocking work with
  `await run_in_threadpool(fn, ...)`. CPU-heavy work (big image processing) belongs in the worker, not
  the web process.
- **Middleware** is `async` (Starlette), and that's fine because it only does tiny non-blocking work.
- Request ids still reach `def` endpoints, because FastAPI copies `contextvars` into the thread.

---

## 10. Security review: five attacks and their defences

| Attack | What they'd try | What stops it | Where |
|---|---|---|---|
| **SQL injection** | `q=' OR 1=1 --` in search | Every query uses SQLAlchemy with bound parameters, never string-built SQL. `%` and `_` in search are escaped too | `issue_repository.py` (`_escape_like`) |
| **IDOR across workspaces** | Take another company's issue id and call `GET /issues/<id>` | Every lookup filters `workspace_id` **from the token**, never from the request. Other workspaces get **404**, which doesn't even confirm the id exists | `get_in_workspace` in every repository; `tests/test_projects.py::test_other_workspace_cannot_read_or_delete_404` |
| **Token theft** | Steal an access or refresh token | Access tokens live 15 minutes. Refresh tokens rotate, and **reusing an old one revokes all the user's tokens**. Tokens are kept in memory in the UI (not localStorage). In production: HTTPS only | `auth_service.refresh` |
| **Brute force** | Try thousands of passwords on `/auth/login` | 10 tries per minute per IP (429 + Retry-After). Argon2 makes each guess slow. Same message for wrong email and wrong password, and a dummy hash so timing matches too | `app/core/rate_limit.py`, `auth_service.login` |
| **File upload abuse** | Upload a 2 GB file, an `.exe` renamed `.png`, an HTML file with a script, or `../../etc/passwd` as the name | Reads at most 5 MB + 1 byte. Type detected **from the bytes**, allow-list only. Stored under a random name, not the user's. Downloaded with `Content-Disposition: attachment` and `nosniff`, so the browser won't run it. Links are signed and expire in 5 minutes | `app/core/storage.py`, `app/api/comments.py` |

Also worth mentioning: secrets only in `.env`, password hashes never in any response schema, a
consistent error envelope that never leaks stack traces, and an audit log of every change.

---

## 11. Random-file test: one line per file

| File | In one sentence |
|---|---|
| `app/main.py` | Creates the app, adds middleware (CORS, request context) and error handlers, includes every router |
| `app/core/config.py` | All settings, read from environment variables / `.env` with types checked at startup |
| `app/core/database.py` | Engine (connection pool), session factory, `get_db` per request, and the SQL query counter hook |
| `app/core/security.py` | Argon2 password hashing; creating and checking access and refresh JWTs |
| `app/core/exceptions.py` | The error classes (401/403/404/409/422/429) and the handlers that build the error envelope |
| `app/core/middleware.py` | Request id, query count, one JSON access-log line per request |
| `app/core/logging.py` | JSON log formatter; every line carries the request id |
| `app/core/request_context.py` | `contextvars` holding the request id and query counter for the current request |
| `app/core/rate_limit.py` | Fixed-window per-IP limit on `/auth/*`, counted in Redis, fails open if Redis is down |
| `app/core/storage.py` | File type detection from bytes, safe file names, local disk storage, signed download links |
| `app/api/deps.py` | `get_current_user` (checks the token, no DB) and `require_role` (403 for the wrong role) |
| `app/api/*.py` | Routers: read the request, call one service function, return a response schema |
| `app/services/issue_service.py` | Issue rules: state machine, assignee must be a member, audit, enqueue email after commit |
| `app/services/audit_service.py` | Adds an audit row to the current transaction; `snapshot` turns a model into JSON |
| `app/services/notification_service.py` | What the jobs do: assignment email, overdue digest, `send_once` idempotency |
| `app/services/jobs.py` | Puts jobs on the queue; never fails the request if Redis is down |
| `app/worker/celery_app.py` | Celery config: Redis broker, acks_late, prefetch 1, the 09:00 schedule |
| `app/worker/tasks.py` | Thin Celery wrappers with the retry policy, each opening its own DB session |
| `app/repositories/*.py` | All SQL lives here: queries, filters, eager loading, the atomic counter |
| `app/models/*.py` | SQLAlchemy tables; enums, constraints, indexes, foreign keys with `ondelete` |
| `app/schemas/*.py` | Pydantic shapes: requests are validated, responses only expose listed fields |
| `migrations/versions/*.py` | One schema change each, reviewed by hand (the enum drops in `downgrade`) |
| `tests/conftest.py` | Test DB created and migrated once; each test in a rolled-back transaction; Redis and the queue faked |
