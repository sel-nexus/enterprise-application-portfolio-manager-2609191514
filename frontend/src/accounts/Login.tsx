import { useState, type FormEvent } from 'react';
import { api, type Session } from './api';

interface Props { onSession: (session: Session) => void }

/** Collect credentials while retaining entered values after an error. */
export default function Login({ onSession }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setBusy(true);
    try { onSession(await api.login(email, password)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Sign-in is unavailable. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <main className="auth-layout">
      <section className="auth-card" aria-labelledby="sign-in-title">
        <h1 id="sign-in-title">Enterprise Application<br />Portfolio Manager</h1>
        <p>Portfolios of the organization’s applications, and the quality reviews recorded on them.</p>
        <form onSubmit={submit}>
          {error && <p className="error" role="alert">{error}</p>}
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} />
          <label htmlFor="password">Password</label>
          <div className="password-field">
            <input id="password" type={show ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
            <button className="text-button" type="button" onClick={() => setShow(!show)}>{show ? 'Hide' : 'Show'}</button>
          </div>
          <button className="primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  );
}
