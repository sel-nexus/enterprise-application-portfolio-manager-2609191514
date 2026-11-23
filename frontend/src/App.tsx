import { useEffect, useState } from 'react';
import { BrowserRouter, useNavigate, useLocation, Link, Routes, Route } from 'react-router-dom';
import Login from './accounts/Login';
import Account, { PasswordForm } from './accounts/Account';
import { api, ApiError, type Account as AccountData, type Session } from './accounts/api';
import Portfolios from './portfolios/Portfolios';
import Applications from './applications/Applications';
import ApplicationRecord from './applications/ApplicationRecord';

const storageKey = 'portfolio-session';

/** Coordinate the authenticated account shell and session lifecycle. */
function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState(() => sessionStorage.getItem(storageKey) || '');
  const [setup, setSetup] = useState(false);
  const [account, setAccount] = useState<AccountData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  function clear() { sessionStorage.removeItem(storageKey); setToken(''); setSetup(false); setAccount(null); navigate('/'); }
  function accept(session: Session) {
    setSetup(session.must_change_password);
    if (session.must_change_password) sessionStorage.removeItem(storageKey);
    else sessionStorage.setItem(storageKey, session.access_token);
    setToken(session.access_token);
  }
  useEffect(() => {
    if (!token || setup) return;
    let active = true;
    setLoading(true); setError('');
    api.me(token).then(result => {
      if (active) { setAccount(result); if (location.pathname === '/') navigate(`/${result.landing_page.replace('_', '-')}`, { replace: true }); }
    }).catch(err => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) clear();
      else setError('This page could not be loaded');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, setup, retry]);
  async function signOut() {
    try { await api.logout(token); clear(); }
    catch (err) {
      if (err instanceof ApiError && err.status === 401) clear();
      else setError('Sign out failed. Try again.');
    }
  }
  if (!token) return <Login onSession={accept} />;
  if (setup) return <main className="auth-layout"><section className="auth-card"><h1>Enterprise Application<br />Portfolio Manager</h1><PasswordForm token={token} initial onChanged={accept} /><button className="text-button" onClick={clear}>Back to sign in</button></section></main>;
  return (
    <div className="shell">
      <aside className="rail"><strong>Enterprise Application<br />Portfolio Manager</strong><nav className="shell-nav" aria-label="Main navigation"><Link to="/portfolios" aria-current={location.pathname === '/portfolios' ? 'page' : undefined}>Portfolios</Link><Link to="/applications" aria-current={location.pathname.startsWith('/applications') ? 'page' : undefined}>Applications</Link><Link to="/account" aria-current={location.pathname === '/account' ? 'page' : undefined}>Account</Link></nav><div className="rail-account">{account?.name}<small>{account?.role.replaceAll('_', ' ')}</small></div></aside>
      <main className="content">
        {location.pathname === '/account' && <header><h1>Account</h1><p>Manage your account and sign-in preferences.</p></header>}
        {loading && <p role="status">Loading account…</p>}
        {error && <div className="account-card" role="alert"><p>{error}</p><button className="secondary" onClick={() => { if (account) void signOut(); else setRetry(retry + 1); }}>Try again</button></div>}
        {account && <Routes>
          <Route path="/portfolios" element={<Portfolios token={token} account={account} />} />
          <Route path="/applications" element={<Applications token={token} account={account} />} />
          <Route path="/applications/:applicationId" element={<ApplicationRecord token={token} account={account} />} />
          <Route path="*" element={<Account token={token} account={account} onAccount={setAccount} onSession={accept} onSignOut={() => void signOut()} />} />
        </Routes>}
      </main>
    </div>
  );
}

/** Install the application's single browser router. */
export default function App() { return <BrowserRouter><Shell /></BrowserRouter>; }
