// JWT storage + login/register. localStorage is the pragmatic MVP choice
// (documented XSS caveat in the implementation plan §1.3); revisit with
// httpOnly cookies if this ever handles more sensitive data.

import { request } from './client';

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
