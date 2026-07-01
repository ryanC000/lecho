import React, { useEffect, useState } from 'react';
import { login, register } from '../utils/auth';

/**
 * AuthModal — real login / register popup, wired to the FastAPI backend.
 * On success it stores the JWT (via utils/auth) and closes.
 */
export default function AuthModal({ open, mode = 'login', onClose, onSwitchMode }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const isRegister = mode === 'register';

  // Reset fields whenever the modal opens or the mode changes.
  useEffect(() => {
    if (open) {
      setForm({ name: '', email: '', password: '', confirm: '' });
      setError(null);
    }
  }, [open, mode]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (isRegister && form.password !== form.confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      if (isRegister) {
        // Register, then immediately log in to obtain a token.
        await register(form.email, form.password);
      }
      await login(form.email, form.password);
      onClose();
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogle = () => {
    // TODO: Firebase / OAuth provider sign-in.
    console.log('[mockup] continue with Google');
  };

  return (
    <div className="auth-overlay" onClick={onClose}>
      <div
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-label={isRegister ? 'Create an account' : 'Log in'}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="auth-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <div className="auth-header">
          <h2 className="auth-title">{isRegister ? 'Create your account' : 'Welcome back'}</h2>
          <p className="auth-sub">
            {isRegister
              ? 'Start echoing back the language you love'
              : 'Pick up where you left off'}
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {isRegister && (
            <label className="auth-field">
              <span>Name</span>
              <input
                type="text"
                autoComplete="name"
                placeholder="Camille Dubois"
                value={form.name}
                onChange={update('name')}
                required
              />
            </label>
          )}

          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={update('email')}
              required
            />
          </label>

          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              placeholder="••••••••"
              value={form.password}
              onChange={update('password')}
              required
            />
          </label>

          {isRegister && (
            <label className="auth-field">
              <span>Confirm password</span>
              <input
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                value={form.confirm}
                onChange={update('confirm')}
                required
              />
            </label>
          )}

          {!isRegister && (
            <button type="button" className="auth-link auth-forgot">
              Forgot password?
            </button>
          )}

          {error && <div className="alert-error">{error}</div>}

          <button type="submit" className="btn-primary auth-submit" disabled={submitting}>
            {submitting ? 'Please wait…' : isRegister ? 'Create account' : 'Log in'}
          </button>
        </form>

        <div className="auth-divider">
          <span>or</span>
        </div>

        <button type="button" className="auth-google" onClick={handleGoogle}>
          <svg className="auth-google-icon" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.89 2.68-6.62z" />
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
            <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
          </svg>
          Continue with Google
        </button>

        <p className="auth-switch">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            type="button"
            className="auth-link"
            onClick={() => onSwitchMode(isRegister ? 'login' : 'register')}
          >
            {isRegister ? 'Log in' : 'Sign up'}
          </button>
        </p>
      </div>
    </div>
  );
}
