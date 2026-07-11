// Central API base + JWT storage. localStorage is the pragmatic MVP choice
// (documented XSS caveat in the implementation plan §1.3); revisit with
// httpOnly cookies if this ever handles more sensitive data.

export const API_BASE = 'http://localhost:8000';

const TOKEN_KEY = 'lecho_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
  window.dispatchEvent(new Event('lecho-auth-changed'));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event('lecho-auth-changed'));
}

export function isLoggedIn() {
  return !!getToken();
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Core request helper: prefixes API_BASE and throws on non-2xx, using the
 * backend's `.detail` as the error message and exposing `.status`. */
async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch { /* non-JSON error body */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res;
}

/** fetch() wrapper that attaches the bearer token. Throws on non-2xx. */
export async function apiFetch(path, options = {}) {
  return request(path, {
    ...options,
    headers: { ...(options.headers || {}), ...authHeaders() },
  });
}

/** Unauthenticated GET that resolves to parsed JSON — used by router loaders. */
export async function apiGet(path) {
  const res = await request(path);
  return res.json();
}

/** POST /auth/register — backend expects JSON {email, password}. */
export async function register(email, password) {
  const res = await request('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return res.json();
}

/** POST /auth/login — backend uses OAuth2 form fields (username/password). */
export async function login(email, password) {
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);
  const res = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  });
  const data = await res.json();
  setToken(data.access_token);
  return data;
}
