import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Portfolios from './Portfolios';
import { portfoliosApi } from './api';
import type { Account } from '../accounts/api';
import { reportingApi } from '../reporting/api';
import { applicationsApi } from '../applications/api';

vi.mock('./api', () => ({ portfoliosApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), archive: vi.fn(), remove: vi.fn() } }));
vi.mock('../reporting/api', () => ({ reportingApi: { report: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }) } }));
vi.mock('../applications/api', () => ({ applicationsApi: { list: vi.fn() } }));
const account: Account = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard', permissions: { view: true, create: true, edit: true, delete: true, export: true, administer: true } };
const portfolio = { id: '1', name: 'Payments', owner: 'Alex', product_area: 'Finance', description: '', status: 'Active' as const, application_count: 1 };
afterEach(() => { cleanup(); vi.resetAllMocks(); });
beforeEach(() => { vi.mocked(reportingApi.report).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }); vi.mocked(applicationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 }); });

it('separately applies create, edit, delete, and portfolio scope', async () => {
  vi.mocked(portfoliosApi.list).mockResolvedValue({ items: [portfolio], total: 1, page: 1, page_size: 25 });
  const restricted = { ...account, permissions: { ...account.permissions!, create: false, edit: false, delete: false } };
  const { rerender } = render(<Portfolios token="token" account={restricted} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Payments' }));
  for (const name of ['New portfolio', 'Edit', 'Archive', 'Delete']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
  rerender(<Portfolios token="token" account={{ ...account, role: 'portfolio_leader', portfolio_ids: ['other'] }} />);
  expect(screen.getByRole('button', { name: 'New portfolio' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  rerender(<Portfolios token="token" account={{ ...account, role: 'portfolio_leader', portfolio_ids: ['1'] }} />);
  expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
});

describe('portfolio inventory', () => {
  it('shows details and blocks delete confirmation when applications remain', async () => {
    vi.mocked(portfoliosApi.list).mockImplementation(async (_token, search) => search && search !== 'Alex' ? { items: [], total: 0, page: 1, page_size: 25 } : { items: [portfolio], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<Portfolios token="token" account={account} />);
    await user.click(await screen.findByRole('button', { name: 'Payments' }));
    expect(screen.getByRole('region', { name: 'Portfolio details' })).toHaveTextContent('Finance');
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(screen.getByText('Move or delete the applications first, or archive the portfolio instead.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.type(screen.getByLabelText('Search name or owner'), 'Alex');
    await waitFor(() => expect(portfoliosApi.list).toHaveBeenLastCalledWith('token', 'Alex', 'Active', 1));
    expect(await screen.findByRole('button', { name: 'Payments' })).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Search name or owner'));
    await user.type(screen.getByLabelText('Search name or owner'), 'Missing');
    expect(await screen.findByText('No portfolio matches that search.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Payments' })).not.toBeInTheDocument();
  });

  it('creates a portfolio and retains input on a failed save', async () => {
    vi.mocked(portfoliosApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    vi.mocked(portfoliosApi.create).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(portfolio);
    const user = userEvent.setup();
    render(<Portfolios token="token" account={account} />);
    await user.click(await screen.findByRole('button', { name: 'New portfolio' }));
    await user.type(screen.getByLabelText('Name'), 'Payments');
    await user.type(screen.getByLabelText('Owner'), 'Alex');
    await user.type(screen.getByLabelText('Product area'), 'Finance');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This could not be saved. Try again.');
    expect(screen.getByLabelText('Name')).toHaveValue('Payments');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Portfolio saved.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers retry on load failure and hides write actions for read-only users', async () => {
    vi.mocked(portfoliosApi.list).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ items: [portfolio], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<Portfolios token="token" account={{ ...account, role: 'read_only' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await user.click(await screen.findByRole('button', { name: 'Payments' }));
    expect(screen.queryByRole('button', { name: 'New portfolio' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });
});
