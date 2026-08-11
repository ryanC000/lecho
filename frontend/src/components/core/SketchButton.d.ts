export interface SketchButtonProps {
  /** double = second off-register outline; stamp = dashed ink set askew; marker = highlighter block, no border; torn = ripped-strip edge; pinned = sketch outline + pushpin. */
  treatment?: 'double' | 'stamp' | 'marker' | 'torn' | 'pinned';
  /** primary = terracotta emphasis; secondary = ink on paper. */
  variant?: 'primary' | 'secondary';
  size?: 'sm' | 'md' | 'lg';
  /** Mirrors the wobble/tilt to the opposite angle, so two adjacent buttons never match. */
  alt?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit';
  children: React.ReactNode;
}
