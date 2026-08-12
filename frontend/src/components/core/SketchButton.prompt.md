# SketchButton

The app's action button: an ink outline traced twice, the second pass drawn just off
register. Use it for text-label actions — record, submit, confirm, navigate.

Not for segmented controls, icon buttons, or link-styled buttons. Those keep their own
classes in `index.css` (`.speed-btn`, `.filter-pill`, `.mode-btn`, `.play-pause-btn`,
`.auth-close`, `.auth-link`), because they need selected state, an icon, or a link look
that this component deliberately does not provide.

## Props

| Prop | Values | Notes |
|---|---|---|
| `variant` | `primary` (default), `secondary` | Filled terracotta, or an ink outline on paper |
| `size` | `sm`, `md` (default) | `sm` for the navbar and dense list rows |
| `alt` | boolean | Mirrors the wobble to the opposite angle |
| `disabled` | boolean | Renders at 0.5 opacity |
| `type` | `button` (default), `submit` | |

Any other prop (`aria-*`, `data-*`) is forwarded to the underlying `<button>`.

## Rules

- Set `alt` on the second of any two adjacent buttons so their outlines don't sit at
  matching angles.
- No icons. These are text-label buttons.
- Press settles down and flush — never a scale-down.
- The colours come from `--accent-primary` / `--text-primary` / `--text-on-accent`,
  aliased onto the app palette at the top of `index.css`. Add no new ones.

## Example

```jsx
<SketchButton onClick={start}>Start Recording</SketchButton>
<SketchButton variant="secondary" alt onClick={back}>Back to Dashboard</SketchButton>
```
