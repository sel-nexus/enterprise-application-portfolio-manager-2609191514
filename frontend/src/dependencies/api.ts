import { ApiError } from '../accounts/api';

export type Relationship = 'Calls' | 'Receives data from' | 'Needs at runtime';
export interface DependencyInput { from_application_id: string; to_application_id: string; relationship: Relationship; note: string }
export interface Dependency extends DependencyInput { id: string; from_name: string; from_portfolio_id: string; to_name: string; portfolio_id: string; portfolio_name: string }
export interface DependencyPage {
  items: Dependency[]; total: number; page: number; page_size: number;
  chart: { application_id: string; application_name: string; count: number }[];
  unlinked_count: number; portfolios: { id: string; name: string }[];
}
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send an authenticated dependency request. */
async function request<T>(token: string, path = '', method = 'GET', body?: DependencyInput): Promise<T> {
  const response = await fetch(`${base}/api/v1/dependencies${path}`, {
    method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'This could not be saved. Try again.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const dependenciesApi = {
  list: (token: string, params: URLSearchParams) => request<DependencyPage>(token, `?${params}`),
  create: (token: string, body: DependencyInput) => request<Dependency>(token, '', 'POST', body),
  remove: (token: string, id: string) => request<void>(token, `/${encodeURIComponent(id)}`, 'DELETE'),
};
