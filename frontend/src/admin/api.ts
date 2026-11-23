import { ApiError } from '../accounts/api';

export interface Person { id: string; name: string; email: string; role: string; portfolio_ids: string[]; vendor_staff?: boolean; manager?: string; active: boolean; last_sign_in: string | null }
export interface PersonInput { name: string; email: string; role: string; portfolio_ids: string[]; vendor_staff: boolean; manager: string }
export type Permissions = Record<'view' | 'create' | 'edit' | 'delete' | 'export' | 'administer', boolean>;
export interface Role { name: string; description: string; permissions: Permissions }
export interface AuditEntry { id: string; when: string; who: string; action: string; record: string; summary: string }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send a protected administration request. */
async function request<T>(token: string, path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${base}/api/v1${path}`, { method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'This could not be saved. Try again.');
  }
  return response.json() as Promise<T>;
}
export const adminApi = {
  users: (token: string, page = 1) => request<Page<Person>>(token, `/admin/users?page=${page}`),
  create: (token: string, data: PersonInput & { temporary_password: string }) => request<Person>(token, '/admin/users', 'POST', data),
  update: (token: string, id: string, data: PersonInput) => request<Person>(token, `/admin/users/${id}`, 'PUT', data),
  deactivate: (token: string, id: string) => request<Person>(token, `/admin/users/${id}/deactivate`, 'POST'),
  roles: (token: string) => request<Role[]>(token, '/admin/roles'),
  saveRole: (token: string, role: Role) => request<Role>(token, `/admin/roles/${role.name}`, 'PUT', { description: role.description, permissions: role.permissions }),
  settings: (token: string) => request<{ days: number }>(token, '/admin/settings'),
  saveInterval: (token: string, days: number) => request<{ days: number }>(token, '/reviews/interval', 'PUT', { days }),
  audit: (token: string, params: URLSearchParams) => request<Page<AuditEntry>>(token, `/admin/audit?${params}`),
  portfolios: (token: string) => request<Page<{ id: string; name: string }>>(token, '/portfolios?status=All&page_size=100'),
  exportAudit: async (token: string, params: URLSearchParams) => {
    const response = await fetch(`${base}/api/v1/admin/audit/export?${params}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new ApiError(response.status, 'Export failed.');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = url; link.download = 'audit.csv'; link.click(); URL.revokeObjectURL(url);
  },
};
