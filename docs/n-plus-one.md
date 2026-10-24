# N+1 query on `GET /issues`: found, fixed, measured

## What an N+1 is

The list query returns N issues (1 query). Then, while building the response, the code touches a
relationship on each issue (`issue.labels`), and SQLAlchemy lazily runs **one more query per issue**.
1 + N queries. It's invisible with 3 rows in development and slow with 100 rows in production.

## How it was found

Every request logs a `db_queries` count (`app/core/middleware.py`), and `LOG_SQL=true` logs each
statement with its `request_id`. The list endpoint's count grew with the page size: the sign of an N+1.

`python -m scripts.count_issue_list_queries --show-sql` measures it. Same data (every issue has labels
and the same assignee and project), before and after.

## Before (commit `fb5166c`, branch `feat/worker`)

| Issues on the page | SQL queries |
|---|---|
| 5 | 9 |
| 25 | 29 |
| 50 | 54 |

Always **4 + N**. The statements for 5 issues:

```
SELECT count(*) ... FROM issues ...                      -- total, for pagination
SELECT issues.* ... LIMIT 100                            -- the page
SELECT projects.* WHERE projects.id = ...                -- lazy: issue.project (once, then cached)
SELECT users.* WHERE users.id = ...                      -- lazy: issue.assignee (once per distinct user)
SELECT labels.* FROM labels, issue_labels WHERE ...      -- lazy: issue.labels  <- once PER ISSUE
SELECT labels.* FROM labels, issue_labels WHERE ...
SELECT labels.* FROM labels, issue_labels WHERE ...
SELECT labels.* FROM labels, issue_labels WHERE ...
SELECT labels.* FROM labels, issue_labels WHERE ...
```

Project and assignee only cost one query each here because every issue shares them and SQLAlchemy's
identity map caches them. With 50 different assignees it would be 50 more queries.

## The fix (`app/repositories/issue_repository.py`, `list_issues`)

```python
query = query.options(
    selectinload(Issue.labels),     # one query: ... WHERE issue_labels.issue_id IN (<ids on this page>)
    joinedload(Issue.assignee),     # LEFT JOIN users in the main query
    joinedload(Issue.project),      # LEFT JOIN projects in the main query
)
```

- `selectinload` for a **collection** (labels): a JOIN would repeat each issue once per label and
  break `LIMIT`, so a second `IN (...)` query is better.
- `joinedload` for a **single object** (assignee, project): one row per issue, so a JOIN is free.

## After

| Issues on the page | SQL queries |
|---|---|
| 5 | 3 |
| 25 | 3 |
| 50 | 3 |

Constant. `tests/test_observability.py::test_issue_list_query_count_does_not_grow_with_issue_count`
keeps it that way: it fails if anyone removes the eager loading.
