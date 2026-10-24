import { useEffect, useState } from "react";
import { api } from "./api";

export default function ProjectsTab({ ctx }) {
  const { withToken, run } = ctx;
  const [projects, setProjects] = useState([]);
  const [members, setMembers] = useState([]);
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");

  const reload = () =>
    run(async () => {
      setProjects(await withToken(api.listProjects));        // GET /projects
      setMembers(await withToken(api.listMembers));           // GET /workspace/members
    });

  useEffect(() => {
    reload();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const act = (call, text) => run(async () => { await withToken(call); await reload(); }, text);

  return (
    <>
      <div className="card">
        <h2>Projects</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act((t) => api.createProject(t, { key, name }));  // POST /projects
            setKey("");
            setName("");
          }}
        >
          <input placeholder="Key (e.g. TRK)" value={key} onChange={(e) => setKey(e.target.value)} />
          <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <button type="submit">Create project</button>
        </form>

        {projects.length === 0 && <p>No projects yet.</p>}
        <ul>
          {projects.map((p) => (
            <li key={p.id}>
              <b>{p.key}</b> {p.name}
              <span className="row-actions">
                <button
                  className="small"
                  onClick={() => {
                    const newName = window.prompt("New name", p.name);
                    if (newName) act((t) => api.updateProject(t, p.id, { name: newName })); // PATCH /projects/{id}
                  }}
                >
                  Rename
                </button>
                <button className="small danger" onClick={() => act((t) => api.deleteProject(t, p.id))}>  {/* DELETE /projects/{id} */}
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Members</h2>
        <ul>
          {members.map((m) => (
            <li key={m.user_id}>
              {m.full_name} ({m.email}) · <b>{m.role}</b>
            </li>
          ))}
        </ul>
        <p className="hint">Add someone who has signed up. They then log in with the Workspace ID shown at the top.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act((t) => api.addMember(t, { email: memberEmail, role: memberRole }), `${memberEmail} added as ${memberRole}`); // POST /workspace/members
            setMemberEmail("");
          }}
        >
          <input placeholder="Their email" type="email" value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} />
          <select value={memberRole} onChange={(e) => setMemberRole(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
          <button type="submit">Add member</button>
        </form>
      </div>
    </>
  );
}
