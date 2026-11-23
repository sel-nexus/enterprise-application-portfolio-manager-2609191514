import { useState, type FormEvent } from 'react';
import { api, type Account as AccountData, type Landing, type Session } from './api';

interface PasswordProps { token: string; initial?: boolean; onChanged: (session: Session) => void; onCancel?: () => void }

/** Replace a temporary or existing password. */
export function PasswordForm({ token, initial = false, onChanged, onCancel }: PasswordProps) {
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    if (password.length < 12 || !/\p{L}/u.test(password) || !/\p{N}/u.test(password) || new TextEncoder().encode(password).length > 72) {
      setError('Use at least 12 characters including a letter and a number (maximum 72 bytes).'); return;
    }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    setBusy(true);
    try { onChanged(await api.password(token, current, password, confirm)); }
    catch (err) { setError(err instanceof Error ? err.message : 'This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <h2>{initial ? 'Choose your password' : 'Change password'}</h2>
      <p>Use at least 12 characters including a letter and a number.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <label htmlFor="current">Current password</label>
      <input id="current" autoFocus type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} />
      <label htmlFor="new">New password</label>
      <input id="new" type="password" autoComplete="new-password" required value={password} onChange={e => setPassword(e.target.value)} />
      <label htmlFor="confirm">Confirm password</label>
      <input id="confirm" type="password" autoComplete="new-password" required value={confirm} onChange={e => setConfirm(e.target.value)} />
      <div className="actions">
        {onCancel && <button type="button" className="secondary" onClick={onCancel}>Cancel</button>}
        <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save password'}</button>
      </div>
    </form>
  );
}

interface Props { token: string; account: AccountData; onAccount: (account: AccountData) => void; onSession: (session: Session) => void; onSignOut: () => void }
const landingOptions: { value: Landing; label: string; description: string }[] = [
  { value: 'dashboard', label: 'Executive dashboard', description: 'Open the estate overview after sign-in.' },
  { value: 'applications', label: 'Applications', description: 'Open the application list after sign-in.' },
  { value: 'reviews_due', label: 'Reviews due', description: 'Open the queue of reviews that need attention.' },
];

/** Render account details and persistent personal settings. */
export default function Account({ token, account, onAccount, onSession, onSignOut }: Props) {
  const [view, setView] = useState<'account' | 'password' | 'landing'>('account');
  const [landing, setLanding] = useState<Landing>(account.landing_page);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function saveLanding(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { onAccount(await api.preferences(token, landing)); setMessage('Landing page saved.'); setView('account'); }
    catch { setError('This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <section className="account-card" aria-label="Account settings">
      {message && <p className="notice" role="status">{message}</p>}
      <nav className="account-nav" aria-label="Account menu">
        <button className="text-button" onClick={() => { setView('account'); setMessage(''); }}>Account</button>
        <button className="text-button" onClick={() => { setView('password'); setMessage(''); }}>Change password</button>
        <button className="text-button" onClick={() => { setView('landing'); setMessage(''); }}>Landing page</button>
        <button className="text-button danger" onClick={onSignOut}>Sign out</button>
      </nav>
      {view === 'account' && (
        <div>
          <h2>Account</h2>
          <dl>
            <dt>Name</dt><dd>{account.name}</dd>
            <dt>Email</dt><dd>{account.email}</dd>
            <dt>Role</dt><dd>{account.role.replaceAll('_', ' ')}</dd>
            <dt>Portfolios</dt><dd>{['administrator', 'executive', 'auditor'].includes(account.role) ? 'All' : account.portfolio_ids.join(', ') || 'None assigned'}</dd>
            <dt>Last sign-in</dt><dd>{account.last_sign_in ? new Date(account.last_sign_in).toLocaleString() : 'Never'}</dd>
          </dl>
        </div>
      )}
      {view === 'password' && <PasswordForm token={token} onCancel={() => setView('account')} onChanged={session => { onSession(session); setView('account'); setMessage('Password changed.'); }} />}
      {view === 'landing' && (
        <form onSubmit={saveLanding}>
          <h2>Landing page</h2>
          {error && <p className="error" role="alert">{error}</p>}
          <fieldset>
            <legend>Choose where to start</legend>
            {landingOptions.map(option => (
              <label className="radio" key={option.value}>
                <input type="radio" name="landing" checked={landing === option.value} onChange={() => setLanding(option.value)} />
                <span><strong>{option.label}</strong><small>{option.description}</small></span>
              </label>
            ))}
          </fieldset>
          <div className="actions"><button type="button" className="secondary" onClick={() => setView('account')}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
        </form>
      )}
    </section>
  );
}
