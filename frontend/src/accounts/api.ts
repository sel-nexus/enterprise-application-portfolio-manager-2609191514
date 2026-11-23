/** Account API contract shared by sign-in and account controls. */
export interface Account {
  id: string;
  name: string;
  email: string;
  role: string;
  portfolio_ids: string[];
  last_sign_in: string | null;
  landing_page: Landing;
}
export type Landing = 'dashboard' | 'applications' | 'reviews_due';
export interface Session { access_token: string; token_type: 'bearer'; must_change_password: boolean }
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send an authenticated or public JSON request and preserve API errors. */
async function request<T>(path: string, method = 'GET', body?: unknown, token?: string): Promise<T> {
  const response = await fetch(`${base}/api/v1/accounts${path}`, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'This could not be saved. Try again.');
  }
  return response.json() as Promise<T>;
}
export const api = {
  login: (email: string, password: string) => request<Session>('/login', 'POST', { email, password }),
  me: (token: string) => request<Account>('/me', 'GET', undefined, token),
  password: (token: string, current_password: string, new_password: string, confirm_password: string) => request<Session>('/password', 'PUT', { current_password, new_password, confirm_password }, token),
  preferences: (token: string, landing_page: Landing) => request<Account>('/preferences', 'PUT', { landing_page }, token),
  logout: (token: string) => request<{ message: string }>('/logout', 'POST', undefined, token),
};
