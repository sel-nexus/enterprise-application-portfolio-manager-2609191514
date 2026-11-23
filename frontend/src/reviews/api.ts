import { ApiError } from '../accounts/api';

export interface ReviewInput { date: string; health: number; quality: number; automation_coverage: number; unit_test_coverage: number; open_defects: number; open_critical_defects: number; risk: 'Low' | 'Medium' | 'High'; note: string }
export interface Review extends ReviewInput { id: string; application_id: string; recorder_id: string; recorder_name: string; created_at: string }
export interface History { items: Review[]; total: number; page: number; page_size: number; interval: number; assigned_reviewer_id: string | null; assigned_reviewer_name: string | null }
export interface DueRow { application_id: string; application_name: string; portfolio_id: string; portfolio_name: string; last_review: string | null; days_since_review: number | null; assigned_reviewer_id?: string | null; assigned_reviewer_name: string | null; risk: string | null; standing: string }
export interface Queue { items: DueRow[]; total: number; page: number; page_size: number; interval: number; due_count: number; chart: { portfolio_id: string; portfolio_name: string; current: number; due: number }[] }
export interface Reviewer { id: string; name: string }
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Send a scoped review request. */
async function request<T>(token: string, path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${base}/api/v1/reviews${path}`, { method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'This could not be saved. Try again.');
  }
  return response.json() as Promise<T>;
}
export const reviewsApi = {
  due: (token: string, params: URLSearchParams) => request<Queue>(token, `/due?${params}`),
  history: (token: string, id: string, page = 1) => request<History>(token, `/applications/${encodeURIComponent(id)}?page=${page}`),
  record: (token: string, id: string, data: ReviewInput) => request<Review>(token, `/applications/${encodeURIComponent(id)}`, 'POST', data),
  eligible: (token: string, id: string) => request<Reviewer[]>(token, `/applications/${encodeURIComponent(id)}/eligible-reviewers`),
  assign: (token: string, id: string, reviewer_id: string | null) => request<{ reviewer_id: string | null; reviewer_name: string | null }>(token, `/applications/${encodeURIComponent(id)}/assignment`, 'PUT', { reviewer_id }),
};
