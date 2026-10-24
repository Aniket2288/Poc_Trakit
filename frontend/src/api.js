// Every call the UI makes to the backend lives in this file.
// UI action -> function here -> exact endpoint.

export const BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function request(method, path, { body, token, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  // JSON bodies get a Content-Type; file uploads (FormData) let the browser set its own multipart header.
  if (body) headers["Content-Type"] = "application/json";

  const res = await fetch(BASE_URL + path, {
    method,
    headers,
    body: form ?? (body ? JSON.stringify(body) : undefined),
  });

  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) {
    // The backend always sends errors as {"error": {"code", "message", "details", "request_id"}}
    const err = new Error(data.error?.message || "Request failed");
    err.status = res.status;
    err.requestId = data.error?.request_id;
    throw err;
  }
  return data;
}

const query = (params) => {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined));
  return new URLSearchParams(clean).toString();
};

export const api = {
  // Auth
  signup: (body) => request("POST", "/auth/signup", { body }),                                   // Sign up button
  login: (body) => request("POST", "/auth/login", { body }),                                     // Log in button
  refresh: (refresh_token) => request("POST", "/auth/refresh", { body: { refresh_token } }),     // automatic, when access token expires
  logout: (refresh_token) => request("POST", "/auth/logout", { body: { refresh_token } }),       // Log out button
  me: (token) => request("GET", "/me", { token }),                                               // after login

  // Projects and members
  listProjects: (token) => request("GET", "/projects", { token }),                               // Projects tab, issue form
  getProject: (token, id) => request("GET", `/projects/${id}`, { token }),                       // Details button
  createProject: (token, body) => request("POST", "/projects", { token, body }),                 // Create project button
  updateProject: (token, id, body) => request("PATCH", `/projects/${id}`, { token, body }),      // Rename button
  deleteProject: (token, id) => request("DELETE", `/projects/${id}`, { token }),                 // Delete button
  listMembers: (token) => request("GET", "/workspace/members", { token }),                       // assignee dropdowns
  addMember: (token, body) => request("POST", "/workspace/members", { token, body }),            // Add member button

  // Issues
  listIssues: (token, params) => request("GET", `/issues?${query(params)}`, { token }),          // Issues tab: filters, search, sort, pages
  getIssue: (token, id) => request("GET", `/issues/${id}`, { token }),                           // clicking an issue
  createIssue: (token, projectId, body) => request("POST", `/projects/${projectId}/issues`, { token, body }), // Create issue button
  updateIssue: (token, id, body) => request("PATCH", `/issues/${id}`, { token, body }),          // Save button on an issue
  assignIssue: (token, id, assignee_id) => request("POST", `/issues/${id}/assign`, { token, body: { assignee_id } }), // Assign dropdown
  transitionIssue: (token, id, status) => request("POST", `/issues/${id}/transition`, { token, body: { status } }),   // status buttons

  // Comments and attachments
  listComments: (token, issueId) => request("GET", `/issues/${issueId}/comments`, { token }),
  addComment: (token, issueId, body) => request("POST", `/issues/${issueId}/comments`, { token, body: { body } }),    // Comment button
  editComment: (token, id, body) => request("PATCH", `/comments/${id}`, { token, body: { body } }),                   // Edit button
  commentHistory: (token, id) => request("GET", `/comments/${id}/history`, { token }),                                // History button
  listAttachments: (token, issueId) => request("GET", `/issues/${issueId}/attachments`, { token }),
  uploadAttachment: (token, issueId, file) => {                                                                       // Upload button
    const form = new FormData();
    form.append("file", file);
    return request("POST", `/issues/${issueId}/attachments`, { token, form });
  },

  // Audit log (admin)
  auditLogs: (token, params) => request("GET", `/audit-logs?${query(params)}`, { token }),        // Audit log tab
};
