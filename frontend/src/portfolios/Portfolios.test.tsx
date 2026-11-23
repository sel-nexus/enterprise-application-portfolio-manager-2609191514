import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Portfolios from './Portfolios';
import { portfoliosApi } from './api';
import type { Account } from '../accounts/api';
import { reportingApi } from '../reporting/api';

vi.mock('./api', () => ({ portfoliosApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), archive: vi.fn(), remove: vi.fn() } }));
vi.mock('../reporting/api', () => ({ reportingApi: { report: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }) } }));
const account: Account = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard' };
const portfolio = { id: '1', name: 'Payments', owner: 'Alex', product_area: 'Finance', description: '', status: 'Active' as const, application_count: 1 };
afterEach(() => { cleanup(); vi.resetAllMocks(); });
beforeEach(() => { vi.mocked(reportingApi.report).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }); });

describe('portfolio inventory', () => {
  it('shows details and blocks delete confirmation when applications remain', async () => {
    vi.mocked(portfoliosApi.list).mockResolvedValue({ items: [portfolio], total: 1, page: 1, page_size: 25 });
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
