import React from 'react';

// Headphones confirmation before the first shadow take of the session
// (PRD §5 / Edge Case 3).
export default function HeadphonesModal({ show, onConfirm, onCancel }) {
  if (!show) return null;

  return (
    <div className="auth-overlay" onClick={onCancel}>
      <div
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Headphones check"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="auth-header">
          <h2 className="auth-title">Headphones on? 🎧</h2>
          <p className="auth-sub">
            Shadowing plays the native clip while you record — use headphones
            so your mic only hears you
          </p>
        </div>
        <div className="controls" style={{ justifyContent: 'center' }}>
          <button className="btn-primary" onClick={onConfirm}>
            I'm wearing headphones
          </button>
          <button onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
