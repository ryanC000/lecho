import React, { useEffect, useRef, useState } from 'react';
import { login, loginWithGoogle, register } from '../api/auth';
import { SketchButton } from './core/SketchButton';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GIS_SRC = 'https://accounts.google.com/gsi/client';

/** Load the Google Identity Services script once, resolving when it is ready. */
function loadGoogleScript() {
  const existing = document.querySelector(`script[src="${GIS_SRC}"]`);
  if (existing) return existing._loaded;

  const script = document.createElement('script');
  script.src = GIS_SRC;
  script.async = true;
  script._loaded = new Promise((resolve, reject) => {
    script.onload = resolve;
    script.onerror = () => reject(new Error('Could not reach Google.'));
  });
  document.head.appendChild(script);
  return script._loaded;
}

/**
 * AuthModal — real login / register popup, wired to the FastAPI backend.
 * On success it stores the JWT (via api/auth) and closes.
 */
export default function AuthModal({ open, mode = 'login', onClose, onSwitchMode }) {
  const [form, setForm] = useState({ email: '', password: '', confirm: '' });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const googleSlot = useRef(null);

  const isRegister = mode === 'register';

  // Fields reset by remounting: App keys this component on open + mode.

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Render Google's official button into the slot once the modal is open.
  useEffect(() => {
    if (!open || !GOOGLE_CLIENT_ID) return;
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled || !googleSlot.current) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async ({ credential }) => {
            setError(null);
            try {
              await loginWithGoogle(credential);
              onClose();
            } catch (err) {
              setError(err.message || 'Google sign-in failed.');
            }
          },
        });
        window.google.accounts.id.renderButton(googleSlot.current, {
          theme: 'outline',
          size: 'large',
          width: 320,
          text: isRegister ? 'signup_with' : 'continue_with',
        });
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => { cancelled = true; };
  }, [open, isRegister, onClose]);

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

          {error && <div className="alert-error">{error}</div>}

          <SketchButton type="submit" disabled={submitting}>
            {submitting ? 'Please wait…' : isRegister ? 'Create account' : 'Log in'}
          </SketchButton>
        </form>

        {/* No client ID configured (see .env.example) — hide rather than show a dead button. */}
        {GOOGLE_CLIENT_ID && (
          <>
            <div className="auth-divider">
              <span>or</span>
            </div>
            <div className="auth-google-slot" ref={googleSlot} />
          </>
        )}

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
