import { ApiError } from '../accounts/api';

export type PortfolioStatus = 'Active' | 'Archived';
export interface PortfolioInput { name: string; owner: string; product_area: string; description: string; status: PortfolioStatus }
export interface Portfolio extends PortfolioInput { id: string; application_count: number }
export interface PortfolioPage { items: Portfolio[]; total: number; page: number; page_size: number }

const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send a portfolio request through the authenticated API. */
async function request<T>(token: string, path = '', method = 'GET', body?: PortfolioInput): Promise<T> {
  const response = await fetch(`${base}/api/v1/portfolios${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'This could not be saved. Try again.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const portfoliosApi = {
  list: (token: string, search: string, status: string, page: number) => request<PortfolioPage>(token, `?${new URLSearchParams({ search, status, page: String(page) })}`),
  get: (token: string, id: string) => request<Portfolio>(token, `/${encodeURIComponent(id)}`),
  create: (token: string, body: PortfolioInput) => request<Portfolio>(token, '', 'POST', body),
  update: (token: string, id: string, body: PortfolioInput) => request<Portfolio>(token, `/${encodeURIComponent(id)}`, 'PUT', body),
  archive: (token: string, id: string) => request<Portfolio>(token, `/${encodeURIComponent(id)}/archive`, 'POST'),
  remove: (token: string, id: string) => request<void>(token, `/${encodeURIComponent(id)}`, 'DELETE'),
};
