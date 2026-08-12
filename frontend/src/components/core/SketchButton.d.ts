export interface SketchButtonProps {
  /** primary = terracotta emphasis; secondary = ink on paper. */
  variant?: 'primary' | 'secondary';
  size?: 'sm' | 'md';
  /** Mirrors the wobble to the opposite angle, so two adjacent buttons never match. */
  alt?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit';
  children: React.ReactNode;
  /** Anything else is forwarded to the underlying <button> (aria-*, data-*). */
  [prop: string]: unknown;
}
