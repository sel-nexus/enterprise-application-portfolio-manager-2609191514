import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Administration from './Administration';
import { adminApi } from './api';

vi.mock('./api', async original => ({ ...(await original<typeof import('./api')>()), adminApi: { users: vi.fn(), portfolios: vi.fn(), create: vi.fn(), update: vi.fn(), roles: vi.fn(), saveRole: vi.fn(), settings: vi.fn(), saveInterval: vi.fn(), audit: vi.fn() } }));
const account = { id: '1', name: 'Admin', email: 'admin@example.com', role: 'administrator', portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard' as const, permissions: { view: true, create: true, edit: true, delete: true, export: true, administer: true } };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('separates administer from audit view and fails closed without permissions', async () => {
  vi.mocked(adminApi.users).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.portfolios).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.audit).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  const { rerender } = render(<Administration token="token" account={{ ...account, permissions: { ...account.permissions, administer: false } }} />);
  expect(await screen.findByText('No audit entries match.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Users' })).not.toBeInTheDocument();
  rerender(<Administration token="token" account={{ ...account, permissions: { ...account.permissions, view: false } }} />);
  expect(screen.getByRole('button', { name: 'Users' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Audit' })).not.toBeInTheDocument();
  rerender(<Administration token="token" account={{ ...account, permissions: undefined }} />);
  expect(screen.getByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
});

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

it('edits a user, retains values on failure, and shows saved results', async () => {
  const person = { id: 'p', name: 'Dana', email: 'dana@example.com', role: 'engineer', portfolio_ids: ['p1'], active: true, last_sign_in: null };
  vi.mocked(adminApi.users).mockResolvedValueOnce({ items: [person], total: 1, page: 1, page_size: 25 }).mockResolvedValue({ items: [{ ...person, name: 'Dana Updated' }], total: 1, page: 1, page_size: 25 });
  vi.mocked(adminApi.portfolios).mockResolvedValue({ items: [{ id: 'p1', name: 'Finance' }], total: 1, page: 1, page_size: 25 });
  vi.mocked(adminApi.update).mockRejectedValueOnce(new Error('Save denied')).mockResolvedValueOnce({ ...person, name: 'Dana Updated' });
  const user = userEvent.setup();
  render(<Administration token="token" account={account} />);
  await user.click(await screen.findByRole('button', { name: 'Edit' }));
  const dialog = screen.getByRole('dialog');
  await user.clear(within(dialog).getByLabelText('Name'));
  await user.type(within(dialog).getByLabelText('Name'), 'Dana Updated');
  await user.click(within(dialog).getByRole('button', { name: 'Save' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Save denied');
  expect(within(dialog).getByLabelText('Name')).toHaveValue('Dana Updated');
  await user.click(within(dialog).getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Dana Updated')).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(adminApi.update).toHaveBeenLastCalledWith('token', 'p', expect.objectContaining({ name: 'Dana Updated', portfolio_ids: ['p1'] }));
});

it('edits role permissions, preserves changes on failure, and displays the saved role', async () => {
  const role = { name: 'engineer', description: 'Engineering', permissions: { view: true, create: true, edit: true, delete: false, export: true, administer: false } };
  vi.mocked(adminApi.users).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.portfolios).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.mocked(adminApi.roles).mockResolvedValueOnce([role]).mockResolvedValue([{ ...role, description: 'Restricted', permissions: { ...role.permissions, edit: false } }]);
  vi.mocked(adminApi.saveRole).mockRejectedValueOnce(new Error('Cannot save role')).mockResolvedValueOnce({ ...role, description: 'Restricted', permissions: { ...role.permissions, edit: false } });
  const user = userEvent.setup();
  render(<Administration token="token" account={account} />);
  await user.click(screen.getByRole('button', { name: 'Roles' }));
  await user.click(await screen.findByRole('button', { name: 'Edit permissions' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByLabelText('delete')).toBeDisabled();
  await user.clear(within(dialog).getByLabelText('Description'));
  await user.type(within(dialog).getByLabelText('Description'), 'Restricted');
  await user.click(within(dialog).getByLabelText('edit'));
  await user.click(within(dialog).getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Cannot save role');
  expect(within(dialog).getByLabelText('edit')).not.toBeChecked();
  await user.click(within(dialog).getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Restricted')).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(adminApi.saveRole).toHaveBeenLastCalledWith('token', expect.objectContaining({ permissions: expect.objectContaining({ edit: false }) }));
});
