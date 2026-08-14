import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch } from './client';
import { setToken, getToken, logout } from './auth';

vi.mock('./client', () => ({ apiFetch: vi.fn(), request: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('logout', () => {
  it('revokes server-side then clears the token', async () => {
    setToken('a-token');
    apiFetch.mockResolvedValue({});

    await logout();

    expect(apiFetch).toHaveBeenCalledWith('/auth/logout', { method: 'POST' });
    expect(getToken()).toBeNull();
  });

  it('clears the token even when the endpoint is unreachable', async () => {
    setToken('a-token');
    apiFetch.mockRejectedValue(new Error('Failed to fetch'));

    await expect(logout()).resolves.toBeUndefined();
    expect(getToken()).toBeNull();
  });
});
