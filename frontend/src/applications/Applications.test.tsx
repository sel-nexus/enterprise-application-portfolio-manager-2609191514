import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Account } from '../accounts/api';
import { portfoliosApi } from '../portfolios/api';
import Applications from './Applications';
import ApplicationRecord from './ApplicationRecord';
import { applicationsApi } from './api';
import { reviewsApi } from '../reviews/api';
import { dependenciesApi } from '../dependencies/api';
import Reports from '../reporting/Reports';
import { reportingApi } from '../reporting/api';

vi.mock('./api', () => ({ applicationsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), lifecycle: vi.fn(), remove: vi.fn() } }));
vi.mock('../portfolios/api', () => ({ portfoliosApi: { list: vi.fn() } }));
vi.mock('../reviews/api', () => ({ reviewsApi: { history: vi.fn() } }));
vi.mock('../dependencies/api', () => ({ dependenciesApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() } }));
vi.mock('../reporting/api', async original => ({ ...(await original<typeof import('../reporting/api')>()), reportingApi: { report: vi.fn(), export: vi.fn() } }));
const account: Account = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'applications', permissions: { view: true, create: true, edit: true, delete: true, export: true, administer: true } };
const portfolio = { id: 'p', name: 'Finance', owner: 'Morgan', product_area: 'Finance', description: '', status: 'Active' as const, application_count: 1 };
const application = { id: 'a', name: 'Payments', portfolio_id: 'p', portfolio_name: 'Finance', description: '', product_area: 'Finance', business_owner: 'Alex', technology_owner: '', inventory_owner: '', criticality: 'High' as const, tier: 1, technology_stack: 'Python', lifecycle: 'Active' as const };
const portfolioPage = { items: [portfolio], total: 1, page: 1, page_size: 25 };
beforeEach(() => { vi.mocked(reviewsApi.history).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, interval: 90, assigned_reviewer_id: null, assigned_reviewer_name: null }); vi.mocked(dependenciesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, chart: [], unlinked_count: 0, portfolios: [] }); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('requires effective create and export permissions in the application list', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue(portfolioPage);
  vi.mocked(applicationsApi.list).mockResolvedValue({ items: [application], total: 1, page: 1, page_size: 25 });
  const restricted = { ...account, permissions: { ...account.permissions!, create: false, export: false } };
  const { rerender } = render(<MemoryRouter><Applications token="token" account={restricted} /></MemoryRouter>);
  await screen.findByRole('link', { name: 'Payments' });
  expect(screen.queryByRole('button', { name: 'New application' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  rerender(<MemoryRouter><Applications token="token" account={account} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: 'New application' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  rerender(<MemoryRouter><Applications token="token" account={{ ...account, permissions: undefined }} /></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'New application' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
});

it('renders a scoped list and sends filters to the API', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue(portfolioPage);
  vi.mocked(applicationsApi.list).mockImplementation(async (_token, params) => params.get('lifecycle') === 'Retired' ? { items: [], total: 0, page: 1, page_size: 25 } : { items: [application], total: 1, page: 1, page_size: 25 });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications']}><Applications token="token" account={account} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/applications/a');
  await user.selectOptions(screen.getByLabelText('Criticality'), 'High');
  await waitFor(() => expect(vi.mocked(applicationsApi.list).mock.calls.at(-1)?.[1].get('criticality')).toBe('High'));
  await user.selectOptions(screen.getByLabelText('Lifecycle'), 'Retired');
  await waitFor(() => expect(vi.mocked(applicationsApi.list).mock.calls.at(-1)?.[1].get('lifecycle')).toBe('Retired'));
  expect(await screen.findByText('No applications match.')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Payments' })).not.toBeInTheDocument();
});

it('retains form values after failure and opens the saved record', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue(portfolioPage);
  vi.mocked(applicationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(applicationsApi.create).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(application);
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications']}><Routes><Route path="/applications" element={<Applications token="token" account={account} />} /><Route path="/applications/:applicationId" element={<p>Saved record</p>} /></Routes></MemoryRouter>);
  await user.click(screen.getByRole('button', { name: 'New application' }));
  await user.type(screen.getByLabelText('Name'), 'Payments');
  await user.selectOptions(await within(screen.getByRole('dialog')).findByLabelText('Portfolio'), 'p');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This could not be saved. Try again.');
  expect(screen.getByLabelText('Name')).toHaveValue('Payments');
  expect(screen.queryByLabelText('Quality')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Saved record')).toBeInTheDocument();
});

it('hides write actions for read-only users and displays load failure', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue(portfolioPage);
  vi.mocked(applicationsApi.list).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ items: [application], total: 1, page: 1, page_size: 25 });
  const user = userEvent.setup();
  render(<MemoryRouter><Applications token="token" account={{ ...account, role: 'read_only' }} /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('link', { name: 'Payments' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'New application' })).not.toBeInTheDocument();
});

it('updates lifecycle and requests delete confirmation', async () => {
  vi.mocked(applicationsApi.get).mockResolvedValue(application);
  vi.mocked(applicationsApi.lifecycle).mockResolvedValue({ ...application, lifecycle: 'Retired' });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={account} />} /></Routes></MemoryRouter>);
  await user.click(await screen.findByRole('button', { name: 'Change lifecycle' }));
  await user.click(screen.getByRole('radio', { name: /Retired/ }));
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Lifecycle changed.')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Delete' }));
  expect(screen.getByRole('dialog')).toHaveTextContent('its reviews, and its dependency links');
});

it('honors each effective permission on the record and embedded dependencies', async () => {
  vi.mocked(applicationsApi.get).mockResolvedValue(application);
  const restricted = { ...account, permissions: { ...account.permissions!, create: true, edit: false, delete: false } };
  const { rerender } = render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={restricted} />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole('button', { name: 'Record a review' })).toBeInTheDocument();
  await screen.findByRole('heading', { name: 'Depends on' });
  for (const name of ['Edit details', 'Change lifecycle', 'Assign reviewer', 'Delete', 'Add dependency', 'Remove']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
  rerender(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={{ ...restricted, permissions: { ...restricted.permissions, create: false, edit: true } }} />} /></Routes></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'Record a review' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Edit details' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add dependency' })).toBeInTheDocument();
});

it('hides report export when stored permissions deny it and permits allowed roles', async () => {
  vi.mocked(reportingApi.report).mockResolvedValue({ items: [{ id: 'a', name: 'Payments' }], total: 1, page: 1, page_size: 25 });
  const restricted = { ...account, permissions: { ...account.permissions!, export: false } };
  const { rerender } = render(<MemoryRouter initialEntries={['/reports?report=applications']}><Reports token="token" account={restricted} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Payments' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
  rerender(<MemoryRouter initialEntries={['/reports?report=applications']}><Reports token="token" account={account} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
  expect(reportingApi.export).toHaveBeenCalled();
});

it('does not expose record actions outside a scoped engineer portfolio or without permissions', async () => {
  vi.mocked(applicationsApi.get).mockResolvedValue(application);
  const scoped = { ...account, role: 'engineer', portfolio_ids: ['other'] };
  const { rerender } = render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={scoped} />} /></Routes></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Depends on' });
  for (const name of ['Record a review', 'Edit details', 'Change lifecycle', 'Assign reviewer', 'Delete', 'Add dependency']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
  rerender(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={{ ...account, permissions: undefined }} />} /></Routes></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Record a review' })).not.toBeInTheDocument();
});

it('renders malicious application description as inert text', async () => {
  const malicious = '<img src=x onerror="window.pwned=true">';
  vi.mocked(applicationsApi.get).mockResolvedValue({ ...application, description: malicious });
  const { container } = render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:applicationId" element={<ApplicationRecord token="token" account={account} />} /></Routes></MemoryRouter>);
  expect(await screen.findByText(malicious)).toBeInTheDocument();
  expect(container.querySelector('img')).toBeNull();
});
