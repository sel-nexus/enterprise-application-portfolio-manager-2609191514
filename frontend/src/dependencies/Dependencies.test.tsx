import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dependencies, { ApplicationDependencies } from './Dependencies';
import DependencyForm from './DependencyForm';
import { dependenciesApi, type DependencyPage } from './api';
import { applicationsApi } from '../applications/api';
import { ApiError } from '../accounts/api';

vi.mock('./api', () => ({ dependenciesApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() } }));
vi.mock('../applications/api', () => ({ applicationsApi: { list: vi.fn() } }));
const account = { id: 'u', name: 'Reader', email: 'reader@example.com', role: 'read_only', portfolio_ids: ['p'], last_sign_in: null, landing_page: 'applications' as const, permissions: { view: true, create: true, edit: true, delete: false, export: false, administer: false } };
const link = { id: 'l', from_application_id: 'a', from_name: 'Alpha', from_portfolio_id: 'p', to_application_id: 'b', to_name: 'Beta', portfolio_id: 'p', portfolio_name: 'Finance', relationship: 'Calls' as const, note: 'API' };
const page: DependencyPage = { items: [link], total: 1, page: 1, page_size: 25, chart: [{ application_id: 'b', application_name: 'Beta', count: 1 }], unlinked_count: 2, portfolios: [{ id: 'p', name: 'Finance' }] };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('requires edit permission and source portfolio scope for dependency actions', async () => {
  vi.mocked(dependenciesApi.list).mockResolvedValue(page);
  const restricted = { ...account, role: 'engineer', permissions: { ...account.permissions, edit: false } };
  const { rerender } = render(<MemoryRouter><Dependencies token="token" account={restricted} /></MemoryRouter>);
  await screen.findByRole('link', { name: 'Alpha' });
  expect(screen.queryByRole('button', { name: 'Add dependency' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  rerender(<MemoryRouter><Dependencies token="token" account={{ ...restricted, permissions: account.permissions, portfolio_ids: ['other'] }} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: 'Add dependency' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  rerender(<MemoryRouter><Dependencies token="token" account={{ ...restricted, permissions: account.permissions }} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument();
});

it('renders a scoped chart and links without exposing write controls to readers', async () => {
  vi.mocked(dependenciesApi.list).mockResolvedValue(page);
  render(<MemoryRouter><Dependencies token="token" account={account} /></MemoryRouter>);
  expect(await screen.findByText('No recorded dependency')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/applications/a');
  expect(screen.queryByRole('button', { name: 'Add dependency' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
});

it('shows a retryable loading failure', async () => {
  vi.mocked(dependenciesApi.list).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page);
  const user = userEvent.setup();
  render(<MemoryRouter><Dependencies token="token" account={account} /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('link', { name: 'Alpha' })).toBeInTheDocument();
});

it('keeps Used by read only and confirms outgoing removal', async () => {
  const incomingLink = { ...link, id: 'incoming', from_application_id: 'c', from_name: 'Gamma', to_application_id: 'a', to_name: 'Alpha' };
  let links = [link, incomingLink];
  vi.mocked(dependenciesApi.list).mockImplementation(async (_token, params) => {
    const items = links.filter((item) => params.get('direction') === 'outgoing' ? item.from_application_id === 'a' : item.to_application_id === 'a');
    return { ...page, items, total: items.length };
  });
  vi.mocked(dependenciesApi.remove).mockImplementation(async (_token, id) => {
    links = links.filter((item) => item.id !== id);
  });
  const user = userEvent.setup();
  render(<MemoryRouter><ApplicationDependencies token="token" account={{ ...account, role: 'engineer' }} applicationId="a" canEdit /></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: 'Used by' })).toBeInTheDocument();
  const usedBy = screen.getByRole('heading', { name: 'Used by' }).closest('section')!;
  const dependsOn = screen.getByRole('heading', { name: 'Depends on' }).closest('section')!;
  expect(within(usedBy).getByRole('link', { name: 'Gamma' })).toHaveAttribute('href', '/applications/c');
  expect(within(usedBy).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  expect(within(usedBy).queryByRole('button', { name: 'Add dependency' })).not.toBeInTheDocument();
  expect(within(dependsOn).getByRole('link', { name: 'Beta' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1);
  await user.click(screen.getByRole('button', { name: 'Remove' }));
  expect(screen.getByRole('dialog')).toHaveTextContent('Remove the link from Alpha to Beta? Both application records will update.');
  await user.click(screen.getByRole('dialog').querySelector('button.danger-button')!);
  expect(await screen.findByText('Dependency removed')).toBeInTheDocument();
  expect(dependenciesApi.remove).toHaveBeenCalledWith('token', 'l');
  await waitFor(() => {
    const updatedDependsOn = screen.getByRole('heading', { name: 'Depends on' }).closest('section')!;
    expect(within(updatedDependsOn).queryByRole('link', { name: 'Beta' })).not.toBeInTheDocument();
    expect(within(updatedDependsOn).getByText('No dependencies recorded.')).toBeInTheDocument();
    const updatedUsedBy = screen.getByRole('heading', { name: 'Used by' }).closest('section')!;
    expect(within(updatedUsedBy).getByRole('link', { name: 'Gamma' })).toBeInTheDocument();
    expect(within(updatedUsedBy).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  });
});

it('retains form values and reports duplicate errors', async () => {
  const app = (id: string, name: string) => ({ id, name, portfolio_id: 'p', portfolio_name: 'Finance', lifecycle: 'Active' as const, description: '', product_area: '', business_owner: '', technology_owner: '', inventory_owner: '', criticality: 'Low' as const, tier: 1, technology_stack: '' });
  vi.mocked(applicationsApi.list).mockResolvedValue({ items: [app('a', 'Alpha'), app('b', 'Beta')], total: 2, page: 1, page_size: 100 });
  vi.mocked(dependenciesApi.create).mockRejectedValue(new ApiError(409, 'That dependency is already recorded.'));
  const user = userEvent.setup();
  render(<DependencyForm token="token" account={{ ...account, role: 'engineer' }} fromId="a" onCancel={() => {}} onSaved={() => {}} />);
  await screen.findAllByRole('option', { name: 'Beta' });
  await user.selectOptions(screen.getByLabelText('To'), 'b');
  await user.type(screen.getByLabelText('Note'), 'Keep me');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('That dependency is already recorded.');
  expect(screen.getByLabelText('Note')).toHaveValue('Keep me');
});
