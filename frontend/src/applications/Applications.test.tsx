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

vi.mock('./api', () => ({ applicationsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), lifecycle: vi.fn(), remove: vi.fn() } }));
vi.mock('../portfolios/api', () => ({ portfoliosApi: { list: vi.fn() } }));
vi.mock('../reviews/api', () => ({ reviewsApi: { history: vi.fn() } }));
const account: Account = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'applications' };
const portfolio = { id: 'p', name: 'Finance', owner: 'Morgan', product_area: 'Finance', description: '', status: 'Active' as const, application_count: 1 };
const application = { id: 'a', name: 'Payments', portfolio_id: 'p', portfolio_name: 'Finance', description: '', product_area: 'Finance', business_owner: 'Alex', technology_owner: '', inventory_owner: '', criticality: 'High' as const, tier: 1, technology_stack: 'Python', lifecycle: 'Active' as const };
const portfolioPage = { items: [portfolio], total: 1, page: 1, page_size: 25 };
beforeEach(() => { vi.mocked(reviewsApi.history).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, interval: 90, assigned_reviewer_id: null, assigned_reviewer_name: null }); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('renders a scoped list and sends filters to the API', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue(portfolioPage);
  vi.mocked(applicationsApi.list).mockResolvedValue({ items: [application], total: 1, page: 1, page_size: 25 });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications']}><Applications token="token" account={account} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/applications/a');
  await user.selectOptions(screen.getByLabelText('Criticality'), 'High');
  await waitFor(() => expect(vi.mocked(applicationsApi.list).mock.calls.at(-1)?.[1].get('criticality')).toBe('High'));
  await user.selectOptions(screen.getByLabelText('Lifecycle'), 'Retired');
  await waitFor(() => expect(vi.mocked(applicationsApi.list).mock.calls.at(-1)?.[1].get('lifecycle')).toBe('Retired'));
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
