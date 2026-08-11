# SketchButton

Five hand-drawn button treatments that extend `Button`'s `sketch` shape. Use when a
button should read as drawn or pressed onto the page rather than as UI chrome —
practice screens, results, anywhere the sketchbook voice is doing the work.

For ordinary app chrome (nav, forms, modals) keep using `Button`.

## Treatments

| `treatment` | Reads as | Use for |
|---|---|---|
| `double` | A line traced twice, second pass off-register | The strongest primary action on a screen |
| `stamp` | Dashed ink, typewriter caps, set askew; straightens on hover | Confirmations, "mark as done", low-frequency actions |
| `marker` | A rough highlighter block behind the label, no border | Secondary actions in a dense screen — the quietest of the five |
| `torn` | A strip torn from the page | Pairs with `Card variant="torn"`; good next to torn surfaces |
| `pinned` | Sketch outline plus the sticky-note pushpin, tilted | Board-like layouts using `Card variant="sticky"` |

## Rules

- One treatment per screen. Mixing `double` and `pinned` in the same view reads as two
  different design systems; pick one and use `variant` to separate primary from secondary.
- `alt` mirrors the tilt and wobble to the opposite angle. Set it on the second of any two
  adjacent buttons so they don't sit at matching angles.
- No new colours: `primary` is `--accent-primary`, `secondary` is ink on `--surface-raised`,
  and `marker` uses `--accent-warning` / `--accent-secondary` washes already in the palette.
- Press always settles flush or down — never a scale-down, matching the rest of the system.
- No icons. These are text-label buttons, consistent with the system's icon restraint.

## Example

```jsx
<SketchButton treatment="double" onClick={start}>Start Recording</SketchButton>
<SketchButton treatment="double" variant="secondary" alt onClick={replay}>Play again</SketchButton>
```
