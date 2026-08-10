// HTTP seam: every page's requests go through here.

import { getToken } from './auth';

export const API_BASE = 'http://localhost:8000';

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Core request helper: prefixes API_BASE and throws on non-2xx, using the
 * backend's `.detail` as the error message and exposing `.status`. */
export async function request(path, options = {}) {
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
