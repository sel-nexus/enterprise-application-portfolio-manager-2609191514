import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

vi.mock('./reporting/Dashboard', () => ({ default: () => <h1>Dashboard content</h1> }));
vi.mock('./portfolios/Portfolios', () => ({ default: () => <h1>Portfolios content</h1> }));

const account = {
  id: '1', name: 'A Person', email: 'a@example.com', role: 'administrator',
  portfolio_ids: [], last_sign_in: null, landing_page: 'dashboard',
  permissions: { view: true, create: true, edit: true, delete: true, export: true, administer: true },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
  window.history.replaceState({}, '', '/');
});

it('refreshes permissions on navigation and fails closed when refresh fails', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/dashboard');
  let resolveRefresh: (response: Response) => void = () => {};
  const pending = new Promise<Response>(resolve => { resolveRefresh = resolve; });
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(account), { status: 200 }))
    .mockReturnValueOnce(pending)
    .mockRejectedValueOnce(new Error('offline'));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole('heading', { name: 'Dashboard content' });
  await user.click(screen.getByRole('link', { name: 'Portfolios' }));
  expect(screen.queryByRole('heading', { name: 'Portfolios content' })).not.toBeInTheDocument();
  resolveRefresh(new Response(JSON.stringify({ ...account, permissions: { ...account.permissions, view: false, administer: false } }), { status: 200 }));
  expect(await screen.findByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Applications' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('link', { name: 'Account' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
});

it('revokes access on returning focus without navigating and ignores an older refresh', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/dashboard');
  let resolveOld: (response: Response) => void = () => {};
  let resolveNew: (response: Response) => void = () => {};
  const oldRefresh = new Promise<Response>(resolve => { resolveOld = resolve; });
  const newRefresh = new Promise<Response>(resolve => { resolveNew = resolve; });
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(account), { status: 200 }))
    .mockReturnValueOnce(oldRefresh)
    .mockReturnValueOnce(newRefresh);
  render(<App />);
  await screen.findByRole('heading', { name: 'Dashboard content' });

  act(() => window.dispatchEvent(new Event('focus')));
  expect(screen.queryByRole('heading', { name: 'Dashboard content' })).not.toBeInTheDocument();
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await act(async () => {
    resolveNew(new Response(JSON.stringify({ ...account, permissions: { ...account.permissions, view: false, administer: false } }), { status: 200 }));
  });
  expect(await screen.findByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
  await act(async () => { resolveOld(new Response(JSON.stringify(account), { status: 200 })); });
  expect(screen.getByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
  expect(window.location.pathname).toBe('/dashboard');
});

it('fails closed when a visible-page permission refresh fails and can retry', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/dashboard');
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(account), { status: 200 }))
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce(new Response(JSON.stringify(account), { status: 200 }));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole('heading', { name: 'Dashboard content' });
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
  expect(screen.queryByRole('heading', { name: 'Dashboard content' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Applications' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('heading', { name: 'Dashboard content' })).toBeInTheDocument();
});

it('refreshes only when a hidden page becomes visible and signs out on an expired session', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/dashboard');
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(account), { status: 200 }))
    .mockResolvedValueOnce(new Response('{}', { status: 401 }));
  render(<App />);
  await screen.findByRole('heading', { name: 'Dashboard content' });
  visibility.mockReturnValue('hidden');
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('heading', { name: 'Dashboard content' })).toBeInTheDocument();
  visibility.mockReturnValue('visible');
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();
  expect(sessionStorage.getItem('portfolio-session')).toBeNull();
});

const application = {
  id: 'a', name: 'Payments', portfolio_id: 'p', portfolio_name: 'Finance',
  description: '', product_area: 'Finance', business_owner: 'Alex', technology_owner: '',
  inventory_owner: '', criticality: 'High', tier: 1, technology_stack: 'Python', lifecycle: 'Active',
};
const page = { items: [], total: 0, page: 1, page_size: 25 };

function mockApplicationRequests(me: () => Promise<Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname;
    if (path === '/api/v1/accounts/me') return me();
    if (path === '/api/v1/applications/a' && init?.method === 'PUT') return new Response(JSON.stringify({ detail: 'Not permitted' }), { status: 403 });
    if (path === '/api/v1/applications/a') return new Response(JSON.stringify(application));
    if (path === '/api/v1/reviews/applications/a') return new Response(JSON.stringify({ ...page, interval: 90, assigned_reviewer_id: null, assigned_reviewer_name: null }));
    if (path === '/api/v1/dependencies') return new Response(JSON.stringify({ ...page, chart: [], unlinked_count: 0, portfolios: [] }));
    if (path === '/api/v1/portfolios') return new Response(JSON.stringify({ ...page, items: [{ id: 'p', name: 'Finance', status: 'Active' }], total: 1 }));
    throw new Error(`Unexpected request: ${path}`);
  });
}

it('retains a typed application draft across a successful background permission refresh', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/applications/a');
  let resolveRefresh: (response: Response) => void = () => {};
  const pending = new Promise<Response>(resolve => { resolveRefresh = resolve; });
  const me = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(account))).mockReturnValueOnce(pending);
  const requests = mockApplicationRequests(me);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: 'Edit details' }));
  const description = screen.getByLabelText('Description');
  await user.type(description, 'Unsaved draft');
  act(() => window.dispatchEvent(new Event('focus')));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  await act(async () => { resolveRefresh(new Response(JSON.stringify(account))); });
  expect(await screen.findByRole('dialog', { name: 'Edit details' })).toBeInTheDocument();
  expect(screen.getByLabelText('Description')).toBe(description);
  expect(description).toHaveValue('Unsaved draft');
  expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This could not be saved');
  expect(description).toHaveValue('Unsaved draft');
  expect(requests.mock.calls.some(([url, init]) => String(url).includes('/applications/a') && init?.method === 'PUT')).toBe(true);
});

it('keeps a draft inaccessible after refresh failure and restores it on retry', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/applications/a');
  const me = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(account)))
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce(new Response(JSON.stringify(account)));
  mockApplicationRequests(me);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: 'Edit details' }));
  const description = screen.getByLabelText('Description');
  await user.type(description, 'Retry draft');
  act(() => window.dispatchEvent(new Event('focus')));
  expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('dialog', { name: 'Edit details' })).toBeInTheDocument();
  expect(screen.getByLabelText('Description')).toBe(description);
  expect(description).toHaveValue('Retry draft');
});

it('removes a previously open write dialog when edit permission is revoked', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/applications/a');
  const me = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(account)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...account, permissions: { ...account.permissions, edit: false } })));
  mockApplicationRequests(me);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: 'Edit details' }));
  await user.type(screen.getByLabelText('Description'), 'Draft');
  act(() => window.dispatchEvent(new Event('focus')));
  expect(await screen.findByRole('heading', { name: 'Payments' })).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
});

it('removes draft content when view access is revoked and ignores a stale grant', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/applications/a');
  let resolveOld: (response: Response) => void = () => {};
  let resolveNew: (response: Response) => void = () => {};
  const old = new Promise<Response>(resolve => { resolveOld = resolve; });
  const newer = new Promise<Response>(resolve => { resolveNew = resolve; });
  const me = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(account))).mockReturnValueOnce(old).mockReturnValueOnce(newer);
  mockApplicationRequests(me);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: 'Edit details' }));
  await user.type(screen.getByLabelText('Description'), 'Private draft');
  act(() => window.dispatchEvent(new Event('focus')));
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await act(async () => { resolveNew(new Response(JSON.stringify({ ...account, permissions: { ...account.permissions, view: false, administer: false } }))); });
  expect(await screen.findByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
  expect(screen.queryByDisplayValue('Private draft')).not.toBeInTheDocument();
  await act(async () => { resolveOld(new Response(JSON.stringify(account))); });
  expect(screen.getByRole('heading', { name: 'Not permitted' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Payments' })).not.toBeInTheDocument();
});

it('does not show a draft or accept an old refresh after navigating away', async () => {
  sessionStorage.setItem('portfolio-session', 'token');
  window.history.replaceState({}, '', '/applications/a');
  let resolveOld: (response: Response) => void = () => {};
  let resolveNavigation: (response: Response) => void = () => {};
  const old = new Promise<Response>(resolve => { resolveOld = resolve; });
  const navigation = new Promise<Response>(resolve => { resolveNavigation = resolve; });
  const me = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(account))).mockReturnValueOnce(old).mockReturnValueOnce(navigation);
  mockApplicationRequests(me);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: 'Edit details' }));
  await user.type(screen.getByLabelText('Description'), 'Old draft');
  act(() => window.dispatchEvent(new Event('focus')));
  await user.click(screen.getByRole('link', { name: 'Account' }));
  await act(async () => { resolveOld(new Response(JSON.stringify(account))); });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Account settings' })).not.toBeInTheDocument();
  await act(async () => { resolveNavigation(new Response(JSON.stringify(account))); });
  expect(await screen.findByRole('region', { name: 'Account settings' })).toBeInTheDocument();
  expect(screen.queryByDisplayValue('Old draft')).not.toBeInTheDocument();
});

describe('mobile navigation', () => {
  it('opens with the keyboard, moves focus into the navigation, and restores it on Escape', async () => {
    sessionStorage.setItem('portfolio-session', 'token');
    window.history.replaceState({}, '', '/dashboard');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(account), { status: 200 }));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole('heading', { name: 'Dashboard content' });

    const menu = screen.getByRole('button', { name: /menu/i });
    const navigation = screen.getByRole('navigation', { name: 'Main navigation', hidden: true });
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveAttribute('aria-controls', navigation.parentElement?.id);
    menu.focus();
    await user.keyboard('{Enter}');
    expect(menu).toHaveAttribute('aria-expanded', 'true');
    expect(within(navigation).getByRole('link', { name: 'Executive dashboard' })).toHaveFocus();
    expect(within(navigation).getByRole('link', { name: 'Executive dashboard' })).toHaveAttribute('aria-current', 'page');
    await user.keyboard('{Escape}');
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveFocus();
  });

  it('closes after choosing a destination, focuses the content, and can be toggled closed', async () => {
    sessionStorage.setItem('portfolio-session', 'token');
    window.history.replaceState({}, '', '/dashboard');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(account), { status: 200 }));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole('heading', { name: 'Dashboard content' });

    const menu = screen.getByRole('button', { name: /menu/i });
    await user.click(menu);
    await user.click(screen.getByRole('link', { name: 'Portfolios' }));
    expect(await screen.findByRole('heading', { name: 'Portfolios content' })).toBeVisible();
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('main')).toHaveFocus();
    await user.click(menu);
    expect(screen.getByRole('link', { name: 'Portfolios' })).toHaveAttribute('aria-current', 'page');
    await user.click(menu);
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveFocus();
  });
});
