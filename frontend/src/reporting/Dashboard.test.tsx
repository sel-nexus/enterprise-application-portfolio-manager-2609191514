import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import Reports from './Reports';
import { reportingApi } from './api';

vi.mock('./api', async importOriginal => ({ ...(await importOriginal<typeof import('./api')>()), reportingApi: { dashboard: vi.fn(), report: vi.fn(), export: vi.fn() } }));
const account = { id: 'u', name: 'Reader', email: 'reader@example.com', role: 'read_only', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard' as const };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('renders cards and updates the dashboard filter', async () => {
  vi.mocked(reportingApi.dashboard).mockResolvedValue({ quality: 80, health: 70, automation_coverage: 60, open_critical_defects: 2, applications_at_risk: 1, applications: 1, portfolios: 1, groups: [{ id: 'p', name: 'Finance', owner: 'Owner', product_area: 'Finance', status: 'Active', applications: 1, quality: 80, health: 70, open_critical_defects: 2, applications_at_risk: 1, reviews_due: 0 }], portfolio_options: [{ id: 'p', name: 'Finance' }], product_areas: ['Finance'] });
  render(<MemoryRouter><Dashboard token="t" account={account} /></MemoryRouter>);
  expect(await screen.findByText('Average quality')).toBeInTheDocument();
  expect(screen.getAllByText('80').length).toBeGreaterThan(0);
  await userEvent.selectOptions(screen.getByLabelText('Risk'), 'High');
  expect(await screen.findByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  expect(vi.mocked(reportingApi.dashboard).mock.calls.at(-1)?.[1].get('risk')).toBe('High');
});

it('shows an empty report without an export action', async () => {
  vi.mocked(reportingApi.report).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  render(<MemoryRouter initialEntries={['/reports?report=applications']}><Reports token="t" account={account} /></MemoryRouter>);
  expect(await screen.findByText('Nothing to report for the portfolios you can see.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
});
