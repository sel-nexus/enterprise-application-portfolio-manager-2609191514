import { ApiError } from '../accounts/api';

export interface PortfolioRow {
  id: string; name: string; owner: string; product_area: string; status: string;
  applications: number; quality: number | null; health: number | null;
  open_critical_defects: number; applications_at_risk: number; reviews_due: number;
}
export interface DashboardData {
  quality: number | null; health: number | null; automation_coverage: number | null;
  open_critical_defects: number; applications_at_risk: number; applications: number; portfolios: number;
  groups: PortfolioRow[]; portfolio_options: { id: string; name: string }[]; product_areas: string[];
}
export type ReportRow = Record<string, string | number | null>;
export interface ReportPage { items: ReportRow[]; total: number; page: number; page_size: number }
const base = import.meta.env.VITE_API_BASE_URL || '';

/** Fetch a scoped reporting resource or raise an API error. */
async function request(token: string, path: string): Promise<Response> {
  const response = await fetch(`${base}/api/v1/reporting${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new ApiError(response.status, 'This page could not be loaded');
  return response;
}

export const reportingApi = {
  dashboard: async (token: string, params: URLSearchParams): Promise<DashboardData> => (await request(token, `/dashboard?${params}`)).json(),
  report: async (token: string, kind: 'applications' | 'portfolios', params: URLSearchParams): Promise<ReportPage> => (await request(token, `/${kind}?${params}`)).json(),
  export: async (token: string, kind: 'applications' | 'portfolios', params: URLSearchParams): Promise<void> => {
    const blob = await (await request(token, `/${kind}/export?${params}`)).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `${kind}.csv`; link.click();
    URL.revokeObjectURL(url);
  },
};

export const applicationColumns: [string, string][] = [['name', 'Name'], ['portfolio', 'Portfolio'], ['product_area', 'Product area'], ['criticality', 'Criticality'], ['tier', 'Tier'], ['lifecycle', 'Lifecycle'], ['business_owner', 'Business owner'], ['technology_owner', 'Technology owner'], ['inventory_owner', 'Inventory owner'], ['assigned_reviewer', 'Assigned reviewer'], ['health', 'Health'], ['quality', 'Quality'], ['automation_coverage', 'Automation coverage'], ['unit_test_coverage', 'Unit-test coverage'], ['open_defects', 'Open defects'], ['open_critical_defects', 'Open critical defects'], ['risk', 'Risk'], ['last_review_date', 'Last review date'], ['review_standing', 'Review standing'], ['depends_on', 'Depends on']];
export const portfolioColumns: [string, string][] = [['name', 'Name'], ['owner', 'Owner'], ['product_area', 'Product area'], ['status', 'Status'], ['applications', 'Applications'], ['quality', 'Quality'], ['health', 'Health'], ['open_critical_defects', 'Open critical defects'], ['applications_at_risk', 'Applications at risk'], ['reviews_due', 'Reviews due']];
