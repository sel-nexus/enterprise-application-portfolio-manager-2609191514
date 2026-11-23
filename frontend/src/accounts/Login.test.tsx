import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Login from './Login';
import Account, { PasswordForm } from './Account';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('account interactions', () => {
  it('retains credentials and displays the backend error after failed sign in', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Email or password is incorrect.' }), { status: 401 }));
    const user = userEvent.setup();
    render(<Login onSession={vi.fn()} />);
    await user.type(screen.getByLabelText('Email'), 'admin@example.com');
    await user.type(screen.getByLabelText('Password'), 'incorrect');
    await user.click(screen.getByRole('button', { name: 'Show' }));
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.');
    expect(screen.getByLabelText('Password')).toHaveValue('incorrect');
    expect(screen.getByLabelText('Email')).toHaveValue('admin@example.com');
  });
  it('validates confirmation before sending the first password', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const user = userEvent.setup();
    render(<PasswordForm token="setup" initial onChanged={vi.fn()} />);
    await user.type(screen.getByLabelText('Current password'), 'temporary123');
    await user.type(screen.getByLabelText('New password'), 'longpassword123');
    await user.type(screen.getByLabelText('Confirm password'), 'different1234');
    await user.click(screen.getByRole('button', { name: 'Save password' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.');
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it('persists the chosen landing page through the API', async () => {
    const account = { id: '1', name: 'A Person', email: 'a@example.com', role: 'engineer', portfolio_ids: ['one'], last_sign_in: null, landing_page: 'applications' as const };
    const update = vi.fn();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ...account, landing_page: 'reviews_due' }), { status: 200 }));
    const user = userEvent.setup();
    render(<Account account={account} token="token" onAccount={update} onSession={vi.fn()} onSignOut={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Landing page' }));
    await user.click(screen.getByRole('radio', { name: /Reviews due/ }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Landing page saved.');
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ landing_page: 'reviews_due' }));
  });
});
