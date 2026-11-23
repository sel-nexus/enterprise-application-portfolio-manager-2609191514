import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Account } from '../accounts/api';
import type { Review, ReviewInput } from '../reviews/api';
import Applications from './Applications';
import ApplicationRecord from './ApplicationRecord';
import Portfolios from '../portfolios/Portfolios';
import Reports from '../reporting/Reports';

const account: Account = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'administrator', permissions: { view: true, create: true, edit: true, delete: true, export: true, administer: true }, portfolio_ids: [], last_sign_in: null, landing_page: 'applications' };
const portfolio = { id: 'p', name: 'Finance', owner: 'Morgan', product_area: 'Finance', description: '', status: 'Active', application_count: 1 };
const application = { id: 'a', name: 'Payments', portfolio_id: 'p', portfolio_name: 'Finance', description: '', product_area: 'Finance', business_owner: 'Alex', technology_owner: 'Sam', inventory_owner: 'Lee', criticality: 'High', tier: 1, technology_stack: 'Python', lifecycle: 'Active' };
const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25 });

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('renders the saved latest review in the application, inventory, portfolio and both reports', async () => {
  const today = new Date();
  const date = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  let latest: Review = { id: 'old', application_id: 'a', recorder_id: 'u', recorder_name: 'Admin', created_at: `${date}T00:00:00Z`, date, health: 10, quality: 20, automation_coverage: 30, unit_test_coverage: 40, open_defects: 2, open_critical_defects: 1, risk: 'Low', note: 'Old' };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    const path = url.pathname;
    let result: unknown;
    if (path === '/api/v1/reviews/applications/a' && init?.method === 'POST') {
      const values = JSON.parse(String(init.body)) as ReviewInput;
      latest = { ...latest, ...values, id: 'new' };
      result = latest;
    } else if (path === '/api/v1/reviews/applications/a') {
      result = { ...page([latest]), interval: 90, assigned_reviewer_id: null, assigned_reviewer_name: null };
    } else if (path === '/api/v1/applications/a') result = application;
    else if (path === '/api/v1/applications') result = page([application]);
    else if (path === '/api/v1/portfolios') result = page([portfolio]);
    else if (path === '/api/v1/dependencies') result = { ...page([]), chart: [], unlinked_count: 1, portfolios: [] };
    else if (path === '/api/v1/reporting/applications') result = page([{ ...application, portfolio: 'Finance', ...latest, id: 'a', last_review_date: latest.date, review_standing: 'Current', assigned_reviewer: null, depends_on: 0 }]);
    else if (path === '/api/v1/reporting/portfolios') result = page([{ ...portfolio, applications: 1, quality: latest.quality, health: latest.health, open_critical_defects: latest.open_critical_defects, applications_at_risk: latest.risk === 'High' ? 1 : 0, reviews_due: 0 }]);
    else throw new Error(`Unexpected request: ${path}`);
    return new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={account} />} /></Routes></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Latest review' });
  expect(screen.getByText('10', { selector: 'dd' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Record a review' }));
  const form = within(screen.getByRole('dialog'));
  for (const [label, value] of [['Health', '80'], ['Quality', '90'], ['Automation coverage', '70'], ['Unit-test coverage', '65'], ['Open defects', '9'], ['Open critical defects', '4']]) {
    await user.type(form.getByLabelText(label), value);
  }
  await user.selectOptions(form.getByLabelText('Risk'), 'High');
  await user.click(form.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Review recorded')).toBeInTheDocument();
  const reviewSection = screen.getByRole('heading', { name: 'Latest review' }).closest('section')!;
  expect(await within(reviewSection).findByText('90')).toBeInTheDocument();
  expect(within(reviewSection).getByText('80')).toBeInTheDocument();
  expect(within(reviewSection).getByText('High')).toBeInTheDocument();
  expect(within(reviewSection).queryByText('20')).not.toBeInTheDocument();

  cleanup();
  render(<MemoryRouter initialEntries={['/applications']}><Applications token="token" account={account} /></MemoryRouter>);
  const appRow = (await screen.findByRole('link', { name: 'Payments' })).closest('tr')!;
  expect(within(appRow).getByText('80')).toBeInTheDocument();
  expect(within(appRow).getByText('70')).toBeInTheDocument();
  expect(within(appRow).getByText('4')).toBeInTheDocument();
  expect(within(appRow).getByText('High', { selector: 'td:last-child' })).toBeInTheDocument();

  cleanup();
  render(<MemoryRouter><Portfolios token="token" account={account} /></MemoryRouter>);
  await user.click(await screen.findByRole('button', { name: 'Finance' }));
  const detail = screen.getByRole('region', { name: 'Portfolio details' });
  expect(await within(detail).findByText(/Health 80.*High/)).toBeInTheDocument();
  expect(within(detail).getByText('90')).toBeInTheDocument();
  expect(within(detail).getByText('4')).toBeInTheDocument();

  cleanup();
  render(<MemoryRouter initialEntries={['/reports?report=applications']}><Reports token="token" account={account} /></MemoryRouter>);
  const appReportRow = (await screen.findByRole('link', { name: 'Payments' })).closest('tr')!;
  for (const value of ['80', '90', '70', '65', '9', '4']) expect(within(appReportRow).getByText(value)).toBeInTheDocument();
  expect(within(appReportRow).getAllByText('High')).toHaveLength(2);

  cleanup();
  render(<MemoryRouter initialEntries={['/reports?report=portfolios']}><Reports token="token" account={account} /></MemoryRouter>);
  const portfolioReportRow = (await screen.findByRole('link', { name: 'Finance' })).closest('tr')!;
  for (const value of ['80', '90', '4']) expect(within(portfolioReportRow).getByText(value)).toBeInTheDocument();
});
