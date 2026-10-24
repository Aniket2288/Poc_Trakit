import { useEffect, useState } from "react";
import { api } from "./api";

const PAGE_SIZE = 20;

export default function AuditTab({ ctx }) {
  const { withToken, run, me } = ctx;
  const [entityType, setEntityType] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState({ items: [], total: 0 });

  const load = (newOffset) =>
    run(async () => {
      setOffset(newOffset);
      setPage(await withToken((t) => api.auditLogs(t, { entity_type: entityType, limit: PAGE_SIZE, offset: newOffset }))); // GET /audit-logs
    });

  useEffect(() => {
    load(0);
  }, [entityType]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="card">
      <h2>Audit log</h2>
      {me.role !== "admin" && <p className="hint">Only admins can read the audit log, so this will show a 403.</p>}
      <select value={entityType} onChange={(e) => setEntityType(e.target.value)}>
        <option value="">Everything</option>
        {["workspace", "membership", "project", "issue", "comment", "attachment"].map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <table>
        <thead>
          <tr><th>When</th><th>Action</th><th>Before</th><th>After</th></tr>
        </thead>
        <tbody>
          {page.items.map((e) => (
            <tr key={e.id}>
              <td>{new Date(e.created_at).toLocaleString()}</td>
              <td><b>{e.action}</b></td>
              <td><code>{e.before ? JSON.stringify(e.before) : "—"}</code></td>
              <td><code>{e.after ? JSON.stringify(e.after) : "—"}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        <button disabled={offset === 0} onClick={() => load(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
        <span>{page.total} entries</span>
        <button disabled={offset + PAGE_SIZE >= page.total} onClick={() => load(offset + PAGE_SIZE)}>Next</button>
      </div>
    </div>
  );
}
