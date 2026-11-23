import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Administration from './Administration';
import { adminApi } from './api';

vi.mock('./api', async original => ({ ...(await original<typeof import('./api')>()), adminApi: { users: vi.fn(), portfolios: vi.fn(), roles: vi.fn(), settings: vi.fn(), saveInterval: vi.fn(), audit: vi.fn() } }));
const account = { id: '1', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard' as const };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('allows an administrator to save the review interval', async () => {
  vi.mocked(adminApi.users).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.portfolios).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.settings).mockResolvedValue({ days: 90 });
  vi.mocked(adminApi.saveInterval).mockResolvedValue({ days: 45 });
  render(<Administration token="token" account={account} />);
  await userEvent.click(screen.getByRole('button', { name: 'Settings' }));
  const input = await screen.findByLabelText('Days');
  await userEvent.clear(input); await userEvent.type(input, '45');
  await userEvent.click(screen.getByRole('button', { name: 'Save interval' }));
  expect(await screen.findByText('Review interval saved.')).toBeInTheDocument();
  expect(adminApi.saveInterval).toHaveBeenCalledWith('token', 45);
});

it('shows auditors only audit and refuses other roles', async () => {
  vi.mocked(adminApi.audit).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  const { rerender } = render(<Administration token="token" account={{ ...account, role: 'auditor' }} />);
  expect(screen.queryByRole('button', { name: 'Users' })).not.toBeInTheDocument();
  expect(await screen.findByText('No audit entries match.')).toBeInTheDocument();
  rerender(<Administration token="token" account={{ ...account, role: 'engineer' }} />);
  expect(screen.getByText('You cannot open administration.')).toBeInTheDocument();
});
