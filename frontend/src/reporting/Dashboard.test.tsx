import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import Reports from './Reports';
import { reportingApi } from './api';

vi.mock('./api', async importOriginal => ({ ...(await importOriginal<typeof import('./api')>()), reportingApi: { dashboard: vi.fn(), report: vi.fn(), export: vi.fn() } }));
const account = { id: 'u', name: 'Reader', email: 'reader@example.com', role: 'read_only', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard' as const };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('updates dashboard cards and portfolio charts when the risk filter changes and clears', async () => {
  const unfiltered = {
    quality: 80, health: 70, automation_coverage: 60, open_critical_defects: 4,
    applications_at_risk: 3, applications: 5, portfolios: 1,
    groups: [{ id: 'p', name: 'Finance', owner: 'Owner', product_area: 'Finance', status: 'Active', applications: 5, quality: 80, health: 70, open_critical_defects: 4, applications_at_risk: 3, reviews_due: 0 }],
    portfolio_options: [{ id: 'p', name: 'Finance' }], product_areas: ['Finance'],
  };
  const highRisk = {
    ...unfiltered, quality: 40, health: 30, automation_coverage: 20,
    open_critical_defects: 2, applications_at_risk: 1, applications: 1,
    groups: [{ ...unfiltered.groups[0], applications: 1, quality: 40, health: 30, open_critical_defects: 2, applications_at_risk: 1 }],
  };
  vi.mocked(reportingApi.dashboard).mockImplementation(async (_token, params) =>
    params.get('risk') === 'High' ? highRisk : unfiltered,
  );
  const user = userEvent.setup();
  render(<MemoryRouter><Dashboard token="t" account={account} /></MemoryRouter>);

  expect(await screen.findByText('80', { selector: 'strong' })).toBeInTheDocument();
  expect(within(screen.getByText('Quality by portfolio').closest('section')!).getByText('80')).toBeInTheDocument();
  expect(within(screen.getByText('Applications at risk by portfolio').closest('section')!).getByText('3')).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Risk'), 'High');
  expect(await screen.findByText('40', { selector: 'strong' })).toBeInTheDocument();
  expect(within(screen.getByText('Average health').closest('section')!).getByText('30')).toBeInTheDocument();
  expect(within(screen.getByText('Applications').closest('section')!).getByText('1')).toBeInTheDocument();
  expect(within(screen.getByText('Quality by portfolio').closest('section')!).getByText('40')).toBeInTheDocument();
  expect(within(screen.getByText('Applications at risk by portfolio').closest('section')!).getByText('1')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  expect(await screen.findByText('80', { selector: 'strong' })).toBeInTheDocument();
  expect(screen.getByLabelText('Risk')).toHaveValue('All');
  expect(within(screen.getByText('Quality by portfolio').closest('section')!).getByText('80')).toBeInTheDocument();
  expect(within(screen.getByText('Applications at risk by portfolio').closest('section')!).getByText('3')).toBeInTheDocument();
});

it('shows an empty report without an export action', async () => {
  vi.mocked(reportingApi.report).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  render(<MemoryRouter initialEntries={['/reports?report=applications']}><Reports token="t" account={account} /></MemoryRouter>);
  expect(await screen.findByText('Nothing to report for the portfolios you can see.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
});
