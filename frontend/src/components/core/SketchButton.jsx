import React from 'react';

// Irregular radii that read as a hand-drawn, wobbly ink outline.
const SKETCH_RADIUS = '14px 26px 12px 22px / 22px 12px 24px 14px';
const SKETCH_RADIUS_ALT = '22px 12px 24px 14px / 14px 26px 12px 22px';

const sizeStyle = {
  sm: { padding: '8px 16px', fontSize: 'var(--text-micro)' },
  md: { padding: '11px 22px', fontSize: 'var(--text-small)' },
};

/**
 * The app's action button: an ink outline traced twice, the second pass drawn
 * just off register. `alt` mirrors the wobble so adjacent buttons never match.
 */
export function SketchButton({
  variant = 'primary',
  size = 'md',
  alt = false,
  disabled = false,
  onClick,
  type = 'button',
  children,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const primary = variant === 'primary';
  const line = primary ? 'var(--accent-primary)' : 'var(--text-primary)';

  const on = {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => { setHover(false); setActive(false); },
    onMouseDown: () => setActive(true),
    onMouseUp: () => setActive(false),
  };

  return (
    <button type={type} disabled={disabled} onClick={onClick} {...on} {...rest} style={{
      position: 'relative',
      fontFamily: 'var(--font-hand)',
      fontWeight: 700,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      transition: 'transform 0.15s ease, background 0.15s ease',
      // The app styles the bare `button` element globally; drop its hover shadow.
      boxShadow: 'none',
      ...(sizeStyle[size] || sizeStyle.md),
      background: primary ? 'var(--accent-primary)' : 'transparent',
      color: primary ? 'var(--text-on-accent)' : 'var(--text-primary)',
      border: `2px solid ${line}`,
      borderRadius: alt ? SKETCH_RADIUS_ALT : SKETCH_RADIUS,
      transform: active ? 'translate(2px,2px)' : hover ? 'translate(-1px,-1px)' : 'translate(0,0)',
    }}>
      <span aria-hidden style={{
        position: 'absolute', inset: -5,
        border: `2px solid ${line}`,
        borderRadius: alt ? SKETCH_RADIUS : SKETCH_RADIUS_ALT,
        opacity: primary ? 0.4 : 0.28,
        transform: alt ? 'rotate(0.8deg)' : 'rotate(-0.7deg)',
        pointerEvents: 'none',
      }} />
      {children}
    </button>
  );
}
