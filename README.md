# TrackIt

TrackIt is a small issue-tracking application, similar to a simplified version of Jira.

A company can create a workspace. Inside a workspace, there can be multiple projects. Each project can have multiple issues & users can add comments to those issues.

Every user belongs to a workspace and has one of three roles:

- Admin– can manage the workspace and its projects.
- Member – can work on projects and issues.
- Viewer – can only view information.

The backend is being built using:

- FastAPI – for creating the APIs
- SQLAlchemy 2 – for working with the database
- Alembic – for managing database changes/migrations
- PostgreSQL – as the database

## How the Project is Organized

The code is separated into different folders, and each folder has a specific responsibility:

```text
app/
│
├── api/            → Handles API requests and responses
├── services/       → Contains the application's business rules
├── repositories/   → Handles database queries
├── models/         → Defines database tables
├── schemas/        → Defines API request and response formats
└── core/           → Shared configuration and common functionality
```

The basic flow of a request is:

```text
Client
  ↓
API
  ↓
Service
  ↓
Repository
  ↓
Database
```

### api/ — Handles HTTP requests

The api layer is responsible for handling HTTP requests.

For example, when someone sends:

```text
POST /projects
```

---

### services — Contains the business logic

The services gives the rules and validations

For example -->

- A viewer cannot create a project
- An issue cannot directly move from Backlog → Done.
- Only certain users can delete a project.

These rules belong in the service layer.

The service layer doesn't care whether the request came from an API, a background task, or a test. It only handles the application's rules.

### repositories — Talks to the database

The repository layer is responsible for database queries.

For example, instead of writing SQL directly inside a service, the service can simply call:

```text
get_user_by_email(email)
```

The repository handles the actual database query.

it also managed databases operations

---

### models — Represents database tables

Models describe how our database tables look.

For example, we might have:

```text
User
Workspace
Project
Issue
Comment
```

A SQLAlchemy model defines the columns and relationships for these tables.

---

### schemas — Defines API data

Schemas define what data the API accepts and returns.

For example, when creating a user, the API might receive:

```json
{
    "email": "user@example.com",
    "password": "mypassword"
}
```

The schema validates that this data has the correct format.

Schemas are kept separate from database models intentionally.

For example, the `User` database table might contain:

- id
- email
- password_hash
- created_at

But when we return a user through the API, we should never return the password hash.

Keeping models and schemas separate helps prevent database fields from accidentally being exposed through the API.

---

### core — Shared application setup

The core folder contains common functionality used throughout the application.

For example:

- Application configuration
- Environment variables
- Password hashing
- Authentication/token handling
- Database session setup
- Global error handling

Think of this as the **shared infrastructure** of the application.

## Why are we using this structure?

The main reason is to keep responsibilities separate.

For example, we don't want this:

```text
API route
  ↓
Business logic
  ↓
SQL query
  ↓
Database
```

all inside one huge function.

Instead, we keep each responsibility in its own place:

```text
API
 ↓
Service
 ↓
Repository
 ↓
Database
```

This means the code may have a few more files, but it becomes easier to:

- Understand
- Test
- Maintain
- Change
- Debug
- Add new features