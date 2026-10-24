import { useEffect, useState } from "react";
import { api, BASE_URL } from "./api";
import { PRIORITIES, STATUSES } from "./IssuesTab";

export default function IssueDetail({ ctx, issueId, members, onBack }) {
  const { withToken, run, me } = ctx;
  const [issue, setIssue] = useState(null);
  const [comments, setComments] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [history, setHistory] = useState({}); // comment id -> earlier versions
  const [newComment, setNewComment] = useState("");

  const reload = () =>
    run(async () => {
      setIssue(await withToken((t) => api.getIssue(t, issueId)));                  // GET /issues/{id}
      setComments(await withToken((t) => api.listComments(t, issueId)));           // GET /issues/{id}/comments
      setAttachments(await withToken((t) => api.listAttachments(t, issueId)));     // GET /issues/{id}/attachments
    });

  useEffect(() => {
    reload();
  }, [issueId]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = (call, text) => run(async () => { await withToken(call); await reload(); }, text);

  if (!issue) return <p>Loading…</p>;

  return (
    <>
      <button className="link" onClick={onBack}>← Back to issues</button>

      <div className="card">
        <h2>
          {issue.key} · {issue.title}
        </h2>
        {issue.description && <p>{issue.description}</p>}
        <p>
          Priority <b>{issue.priority}</b> · Due <b>{issue.due_date ?? "—"}</b> · Labels <b>{issue.labels.join(", ") || "—"}</b>
        </p>

        {/* Every status is a button on purpose: the SERVER decides what is allowed, and a bad move shows its 422. */}
        <h3>Status</h3>
        <div className="statuses">
          {STATUSES.map((s) => (
            <button
              key={s}
              className={issue.status === s ? `badge ${s} current` : "small"}
              onClick={() => act((t) => api.transitionIssue(t, issue.id, s), `Moved to ${s}`)}  // POST /issues/{id}/transition
            >
              {s}
            </button>
          ))}
        </div>

        <h3>Assignee</h3>
        <select
          value={issue.assignee?.id ?? ""}
          onChange={(e) => act((t) => api.assignIssue(t, issue.id, e.target.value || null), "Assigned. The worker will email them.")} // POST /issues/{id}/assign
        >
          <option value="">Unassigned</option>
          {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
        </select>

        <h3>Priority</h3>
        <select value={issue.priority} onChange={(e) => act((t) => api.updateIssue(t, issue.id, { priority: e.target.value }))}> {/* PATCH /issues/{id} */}
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      <div className="card">
        <h2>Comments</h2>
        {comments.length === 0 && <p>No comments yet.</p>}
        {comments.map((c) => (
          <div key={c.id} className="comment">
            <p>
              <b>{c.author.full_name}</b> {c.edited_at && <span className="hint">(edited)</span>}
            </p>
            <p>{c.body}</p>
            {c.author.id === me.user.id && (
              <button
                className="small"
                onClick={() => {
                  const body = window.prompt("Edit comment", c.body);
                  if (body) act((t) => api.editComment(t, c.id, body)); // PATCH /comments/{id}
                }}
              >
                Edit
              </button>
            )}
            {c.edited_at && (
              <button
                className="small"
                onClick={() => run(async () => {
                  const versions = await withToken((t) => api.commentHistory(t, c.id));  // GET /comments/{id}/history
                  setHistory({ ...history, [c.id]: versions });
                })}
              >
                History
              </button>
            )}
            {history[c.id] && (
              <ul className="hint">
                {history[c.id].map((v, i) => (
                  <li key={i}>
                    {new Date(v.created_at).toLocaleString()}: “{v.body}”
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act((t) => api.addComment(t, issue.id, newComment)); // POST /issues/{id}/comments
            setNewComment("");
          }}
        >
          <input placeholder="Write a comment" value={newComment} onChange={(e) => setNewComment(e.target.value)} />
          <button type="submit">Comment</button>
        </form>
      </div>

      <div className="card">
        <h2>Attachments</h2>
        <ul>
          {attachments.map((a) => (
            <li key={a.id}>
              {/* A signed link: it works without a login, but only for 5 minutes. */}
              <a href={BASE_URL + a.download_url} target="_blank" rel="noreferrer">{a.original_name}</a>{" "}
              <span className="hint">({a.content_type}, {Math.ceil(a.size_bytes / 1024)} KB)</span>
            </li>
          ))}
        </ul>
        <p className="hint">PNG, JPEG, GIF, PDF or text, up to 5 MB.</p>
        <input
          type="file"
          onChange={(e) => {
            const file = e.target.files[0];
            if (file) act((t) => api.uploadAttachment(t, issue.id, file), `${file.name} uploaded`); // POST /issues/{id}/attachments
            e.target.value = "";
          }}
        />
      </div>
    </>
  );
}
