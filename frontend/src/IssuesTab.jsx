import { useEffect, useState } from "react";
import { api } from "./api";
import IssueDetail from "./IssueDetail";

export const STATUSES = ["backlog", "in_progress", "review", "done"];
export const PRIORITIES = ["low", "medium", "high", "urgent"];
const PAGE_SIZE = 10;

export default function IssuesTab({ ctx }) {
  const { withToken, run } = ctx;
  const [projects, setProjects] = useState([]);
  const [members, setMembers] = useState([]);
  const [filters, setFilters] = useState({ project_id: "", status: "", assignee_id: "", label: "", priority: "", q: "", sort: "created_at", order: "desc" });
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState({ items: [], total: 0 });
  const [openId, setOpenId] = useState(null);

  // Loaded once: used by the filters, the create form and the assign dropdown.
  useEffect(() => {
    run(async () => {
      setProjects(await withToken(api.listProjects));  // GET /projects
      setMembers(await withToken(api.listMembers));    // GET /workspace/members
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const load = (newOffset = offset) =>
    run(async () => {
      setOffset(newOffset);
      setPage(await withToken((t) => api.listIssues(t, { ...filters, limit: PAGE_SIZE, offset: newOffset }))); // GET /issues?...
    });

  // Reload page 1 whenever a filter changes.
  useEffect(() => {
    load(0);
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  const setFilter = (field) => (e) => setFilters({ ...filters, [field]: e.target.value });

  if (openId) {
    return <IssueDetail ctx={ctx} issueId={openId} members={members} onBack={() => { setOpenId(null); load(); }} />;
  }

  return (
    <>
      <CreateIssue ctx={ctx} projects={projects} members={members} onCreated={() => load(0)} />

      <div className="card">
        <h2>Issues</h2>
        <div className="filters">
          <input placeholder="Search title or description" value={filters.q} onChange={setFilter("q")} />
          <select value={filters.project_id} onChange={setFilter("project_id")}>
            <option value="">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.key}</option>)}
          </select>
          <select value={filters.status} onChange={setFilter("status")}>
            <option value="">Any status</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.assignee_id} onChange={setFilter("assignee_id")}>
            <option value="">Anyone</option>
            {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
          </select>
          <select value={filters.priority} onChange={setFilter("priority")}>
            <option value="">Any priority</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input placeholder="Label" value={filters.label} onChange={setFilter("label")} />
          <select value={filters.sort} onChange={setFilter("sort")}>
            <option value="created_at">Sort: created</option>
            <option value="updated_at">Sort: updated</option>
            <option value="due_date">Sort: due date</option>
            <option value="priority">Sort: priority</option>
          </select>
          <select value={filters.order} onChange={setFilter("order")}>
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </div>

        <table>
          <thead>
            <tr><th>Key</th><th>Title</th><th>Status</th><th>Priority</th><th>Assignee</th><th>Due</th><th>Labels</th></tr>
          </thead>
          <tbody>
            {page.items.map((i) => (
              <tr key={i.id} className="clickable" onClick={() => setOpenId(i.id)}>
                <td><b>{i.key}</b></td>
                <td>{i.title}</td>
                <td><span className={`badge ${i.status}`}>{i.status}</span></td>
                <td>{i.priority}</td>
                <td>{i.assignee?.full_name ?? "—"}</td>
                <td>{i.due_date ?? "—"}</td>
                <td>{i.labels.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {page.items.length === 0 && <p>No issues match.</p>}

        <div className="pager">
          <button disabled={offset === 0} onClick={() => load(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <span>
            {page.total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <button disabled={offset + PAGE_SIZE >= page.total} onClick={() => load(offset + PAGE_SIZE)}>Next</button>
        </div>
      </div>
    </>
  );
}

function CreateIssue({ ctx, projects, members, onCreated }) {
  const { withToken, run } = ctx;
  const empty = { project_id: "", title: "", description: "", priority: "medium", due_date: "", assignee_id: "", labels: "" };
  const [form, setForm] = useState(empty);
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  function submit(e) {
    e.preventDefault();
    const body = {
      title: form.title,
      description: form.description || null,
      priority: form.priority,
      due_date: form.due_date || null,
      assignee_id: form.assignee_id || null,
      labels: form.labels.split(",").map((l) => l.trim()).filter(Boolean),
    };
    run(async () => {
      const issue = await withToken((t) => api.createIssue(t, form.project_id, body)); // POST /projects/{id}/issues
      setForm({ ...empty, project_id: form.project_id });
      onCreated();
      return issue;
    }, "Issue created");
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>New issue</h2>
      <select value={form.project_id} onChange={set("project_id")} required>
        <option value="">Choose a project…</option>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.key} · {p.name}</option>)}
      </select>
      <input placeholder="Title" value={form.title} onChange={set("title")} />
      <input placeholder="Description (optional)" value={form.description} onChange={set("description")} />
      <div className="row">
        <select value={form.priority} onChange={set("priority")}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <input type="date" value={form.due_date} onChange={set("due_date")} />
        <select value={form.assignee_id} onChange={set("assignee_id")}>
          <option value="">Unassigned</option>
          {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
        </select>
      </div>
      <input placeholder="Labels, comma separated (e.g. bug, frontend)" value={form.labels} onChange={set("labels")} />
      <button type="submit">Create issue</button>
    </form>
  );
}
