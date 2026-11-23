import { ApiError } from '../accounts/api';

export type Criticality = 'Low' | 'Medium' | 'High' | 'Critical';
export type Lifecycle = 'Active' | 'Deprecated' | 'Retired';
export interface ApplicationInput {
  name: string; description: string; portfolio_id: string; product_area: string;
  business_owner: string; technology_owner: string; inventory_owner: string;
  criticality: Criticality; tier: number; technology_stack: string;
}
export interface Application extends ApplicationInput { id: string; portfolio_name: string; lifecycle: Lifecycle }
export interface ApplicationPage { items: Application[]; total: number; page: number; page_size: number }
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send an authenticated inventory request. */
async function request<T>(token: string, path = '', method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${base}/api/v1/applications${path}`, {
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

export const applicationsApi = {
  list: (token: string, params: URLSearchParams) => request<ApplicationPage>(token, `?${params}`),
  get: (token: string, id: string) => request<Application>(token, `/${encodeURIComponent(id)}`),
  create: (token: string, body: ApplicationInput) => request<Application>(token, '', 'POST', body),
  update: (token: string, id: string, body: ApplicationInput) => request<Application>(token, `/${encodeURIComponent(id)}`, 'PUT', body),
  lifecycle: (token: string, id: string, lifecycle: Lifecycle) => request<Application>(token, `/${encodeURIComponent(id)}/lifecycle`, 'PUT', { lifecycle }),
  remove: (token: string, id: string) => request<void>(token, `/${encodeURIComponent(id)}`, 'DELETE'),
};
