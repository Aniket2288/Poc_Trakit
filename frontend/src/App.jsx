import { useRef, useState } from "react";
import { api } from "./api";
import AuditTab from "./AuditTab";
import IssuesTab from "./IssuesTab";
import ProjectsTab from "./ProjectsTab";

export default function App() {
  // Tokens are kept in memory only: a page reload logs you out, which is fine for this demo.
  const [tokens, setTokens] = useState(null);
  const tokensRef = useRef(null);
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState("issues");
  const [message, setMessage] = useState(null); // { type: "error" | "info", text }

  function saveTokens(newTokens) {
    tokensRef.current = newTokens;
    setTokens(newTokens);
  }

  // Calls an API that needs the access token. If the token has expired, swap the
  // refresh token for a new pair (POST /auth/refresh) and try once more.
  async function withToken(call) {
    try {
      return await call(tokensRef.current.access_token);
    } catch (e) {
      if (e.status !== 401 || e.message !== "Token has expired") throw e;
      const fresh = await api.refresh(tokensRef.current.refresh_token);
      saveTokens(fresh);
      return await call(fresh.access_token);
    }
  }

  // Runs an action and shows its error (or a success text) at the top of the page.
  async function run(action, successText) {
    setMessage(null);
    try {
      const result = await action();
      if (successText) setMessage({ type: "info", text: successText });
      return result;
    } catch (e) {
      const id = e.requestId ? ` (request id ${e.requestId})` : "";
      setMessage({ type: "error", text: `${e.status ?? ""} ${e.message}${id}` });
    } finally {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  async function afterLogin(newTokens) {
    saveTokens(newTokens);
    setMe(await withToken(api.me));
  }

  const logout = () =>
    run(async () => {
      await api.logout(tokensRef.current.refresh_token);
      saveTokens(null);
      setMe(null);
    });

  const ctx = { withToken, run, me };

  return (
    <main>
      <h1>TrackIt</h1>
      {message && <p className={message.type}>{message.text}</p>}

      {!tokens ? (
        <AuthForms onAuth={(call) => run(async () => afterLogin(await call()))} />
      ) : !me ? (
        <p>Loading…</p>
      ) : (
        <>
          <div className="card topbar">
            <span>
              <b>{me.user.full_name}</b> · {me.role} · <code title="Workspace ID">{me.workspace_id}</code>
            </span>
            <button onClick={logout}>Log out</button>
          </div>
          <nav className="tabs">
            {["issues", "projects", "audit"].map((name) => (
              <button key={name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}>
                {name === "audit" ? "Audit log" : name[0].toUpperCase() + name.slice(1)}
              </button>
            ))}
          </nav>
          {tab === "issues" && <IssuesTab ctx={ctx} />}
          {tab === "projects" && <ProjectsTab ctx={ctx} />}
          {tab === "audit" && <AuditTab ctx={ctx} />}
        </>
      )}
    </main>
  );
}

function AuthForms({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", workspace_name: "", workspace_id: "" });
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  function submit(e) {
    e.preventDefault();
    if (mode === "login") {
      const body = { email: form.email, password: form.password };
      if (form.workspace_id.trim()) body.workspace_id = form.workspace_id.trim();
      onAuth(() => api.login(body));
    } else {
      const { email, password, full_name, workspace_name } = form;
      onAuth(() => api.signup({ email, password, full_name, workspace_name }));
    }
  }

  return (
    <form onSubmit={submit} className="card">
      <h2>{mode === "login" ? "Log in" : "Sign up"}</h2>
      {mode === "signup" && <input placeholder="Full name" value={form.full_name} onChange={set("full_name")} />}
      {mode === "signup" && <input placeholder="Workspace name" value={form.workspace_name} onChange={set("workspace_name")} />}
      <input placeholder="Email" type="email" value={form.email} onChange={set("email")} />
      <input placeholder="Password" type="password" value={form.password} onChange={set("password")} />
      {mode === "login" && (
        <input placeholder="Workspace ID (optional — to join a workspace you were added to)" value={form.workspace_id} onChange={set("workspace_id")} />
      )}
      <button type="submit">{mode === "login" ? "Log in" : "Sign up"}</button>
      <button type="button" className="link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
        {mode === "login" ? "No account? Sign up" : "Have an account? Log in"}
      </button>
    </form>
  );
}
