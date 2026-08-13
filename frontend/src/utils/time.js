const DAY_MS = 24 * 60 * 60 * 1000;

/** Coarse "time ago" label for the dashboard: "2h ago", "yesterday", a weekday name, or a date. */
export function relativeTime(dateInput) {
  const date = new Date(dateInput);
  const diffMin = Math.round((Date.now() - date.getTime()) / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const dayDiff = Math.floor((startOfToday - date) / DAY_MS);
  if (dayDiff <= 1) return 'yesterday';
  if (dayDiff < 7) return date.toLocaleDateString(undefined, { weekday: 'long' });
  return date.toLocaleDateString();
}
