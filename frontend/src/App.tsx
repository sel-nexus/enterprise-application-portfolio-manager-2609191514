import { useEffect, useRef, useState } from 'react';
import {
  BrowserRouter,
  useNavigate,
  useLocation,
  Link,
  Routes,
  Route,
} from 'react-router-dom';
import Login from './accounts/Login';
import Account, { PasswordForm } from './accounts/Account';
import {
  api,
  ApiError,
  type Account as AccountData,
  type Session,
} from './accounts/api';
import Portfolios from './portfolios/Portfolios';
import Applications from './applications/Applications';
import ApplicationRecord from './applications/ApplicationRecord';
import ReviewsDue from './reviews/ReviewsDue';
import Dependencies from './dependencies/Dependencies';
import Dashboard from './reporting/Dashboard';
import Reports from './reporting/Reports';
import Administration from './admin/Administration';

const storageKey = 'portfolio-session';

/** Coordinate the authenticated account shell and session lifecycle. */
function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState(
    () => sessionStorage.getItem(storageKey) || '',
  );
  const [setup, setSetup] = useState(false);
  const [account, setAccount] = useState<AccountData | null>(null);
  const [accountPath, setAccountPath] = useState('');
  const [accountToken, setAccountToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const navigation = useRef<HTMLElement>(null);
  const content = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    navigation.current?.querySelector<HTMLAnchorElement>('a')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    const onResize = () => {
      if (window.innerWidth >= 768) setMenuOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onResize);
    };
  }, [menuOpen]);
  function clear() {
    sessionStorage.removeItem(storageKey);
    setToken('');
    setSetup(false);
    setAccount(null);
    navigate('/');
  }
  function accept(session: Session) {
    setSetup(session.must_change_password);
    if (session.must_change_password) sessionStorage.removeItem(storageKey);
    else sessionStorage.setItem(storageKey, session.access_token);
    setToken(session.access_token);
  }
  useEffect(() => {
    if (!token || setup) return;
    let active = true;
    let requestId = 0;
    const refresh = () => {
      const currentRequest = ++requestId;
      setLoading(true);
      setError('');
      api
        .me(token)
        .then((result) => {
          if (active && currentRequest === requestId) {
            setAccount(result);
            setAccountPath(location.pathname);
            setAccountToken(token);
            if (location.pathname === '/')
              navigate(
                result.permissions?.view === true
                  ? `/${result.landing_page.replace('_', '-')}`
                  : '/account',
                { replace: true },
              );
          }
        })
        .catch((err) => {
          if (!active || currentRequest !== requestId) return;
          if (err instanceof ApiError && err.status === 401) clear();
          else setError('This page could not be loaded');
        })
        .finally(() => {
          if (active && currentRequest === requestId) setLoading(false);
        });
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    refresh();
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      active = false;
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [token, setup, retry, location.pathname]);
  async function signOut() {
    try {
      await api.logout(token);
      clear();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clear();
      else setError('Sign out failed. Try again.');
    }
  }
  if (!token) return <Login onSession={accept} />;
  if (setup)
    return (
      <main className="auth-layout">
        <section className="auth-card">
          <h1>
            Enterprise Application
            <br />
            Portfolio Manager
          </h1>
          <PasswordForm token={token} initial onChanged={accept} />
          <button className="text-button" onClick={clear}>
            Back to sign in
          </button>
        </section>
      </main>
    );
  // Keep only the last verified route for this token and path mounted while
  // its permissions are rechecked; hide it until verification succeeds.
  const routeAccount =
    accountToken === token && accountPath === location.pathname ? account : null;
  const currentAccount = !loading && !error ? routeAccount : null;
  const routeCanView = routeAccount?.permissions?.view === true;
  const canView = currentAccount?.permissions?.view === true;
  // Open action dialogs do not all re-check permissions, so discard them
  // when effective authorization or portfolio scope actually changes.
  const authorizationKey = routeAccount && JSON.stringify([
    routeAccount.id,
    routeAccount.role,
    [...routeAccount.portfolio_ids].sort(),
    ...(['view', 'create', 'edit', 'delete', 'export', 'administer'] as const)
      .map((permission) => routeAccount.permissions?.[permission] === true),
  ]);
  const canAdmin =
    currentAccount?.role === 'administrator' &&
    currentAccount.permissions?.administer === true;
  const canAudit =
    !!currentAccount &&
    ['administrator', 'auditor'].includes(currentAccount.role) &&
    canView;
  return (
    <div className="shell">
      <aside
        className="rail"
        onBlur={(event) => {
          if (
            menuOpen &&
            !event.currentTarget.contains(event.relatedTarget as Node | null)
          )
            setMenuOpen(false);
        }}
      >
        <div className="rail-header">
          <strong>
            Enterprise Application
            <br />
            Portfolio Manager
          </strong>
          <button
            ref={menuButton}
            className="menu-toggle"
            type="button"
            aria-expanded={menuOpen}
            aria-controls="navigation-sheet"
            onClick={() => setMenuOpen((open) => !open)}
          >
            Menu
          </button>
        </div>
        <div
          id="navigation-sheet"
          className={`rail-sheet${menuOpen ? ' open' : ''}`}
        >
          <nav
            ref={navigation}
            className="shell-nav"
            aria-label="Main navigation"
            onClick={(event) => {
              const target = event.target as HTMLElement;
              if (
                menuOpen &&
                target.closest('a') &&
                event.button === 0 &&
                !event.metaKey &&
                !event.ctrlKey &&
                !event.shiftKey &&
                !event.altKey
              ) {
                setMenuOpen(false);
                content.current?.focus();
              }
            }}
          >
            {canView && (
              <>
                <Link
                  to="/dashboard"
                  aria-current={
                    location.pathname === '/dashboard' ? 'page' : undefined
                  }
                >
                  Executive dashboard
                </Link>
                <Link
                  to="/portfolios"
                  aria-current={
                    location.pathname === '/portfolios' ? 'page' : undefined
                  }
                >
                  Portfolios
                </Link>
                <Link
                  to="/applications"
                  aria-current={
                    location.pathname.startsWith('/applications')
                      ? 'page'
                      : undefined
                  }
                >
                  Applications
                </Link>
                <Link
                  to="/reviews-due"
                  aria-current={
                    location.pathname === '/reviews-due' ? 'page' : undefined
                  }
                >
                  Reviews due
                </Link>
                <Link
                  to="/dependencies"
                  aria-current={
                    location.pathname === '/dependencies' ? 'page' : undefined
                  }
                >
                  Dependencies
                </Link>
                <Link
                  to="/reports"
                  aria-current={
                    location.pathname === '/reports' ? 'page' : undefined
                  }
                >
                  Reports
                </Link>
              </>
            )}
            {(canAdmin || canAudit) && (
              <Link
                to="/administration"
                aria-current={
                  location.pathname === '/administration' ? 'page' : undefined
                }
              >
                {canAdmin ? 'Administration' : 'Audit'}
              </Link>
            )}
            <Link
              to="/account"
              aria-current={
                location.pathname === '/account' ? 'page' : undefined
              }
            >
              Account
            </Link>
          </nav>
          <div className="rail-account">
            {account?.name}
            <small>{account?.role.replaceAll('_', ' ')}</small>
          </div>
        </div>
      </aside>
      <main ref={content} className="content" tabIndex={-1}>
        {location.pathname === '/account' && (
          <header>
            <h1>Account</h1>
            <p>Manage your account and sign-in preferences.</p>
          </header>
        )}
        {loading && <p role="status">Loading account…</p>}
        {error && (
          <div className="account-card" role="alert">
            <p>{error}</p>
            <button className="secondary" onClick={() => setRetry(retry + 1)}>
              Try again
            </button>
          </div>
        )}
        {routeAccount && (
          <div hidden={!currentAccount} style={!currentAccount ? { display: 'none' } : undefined}>
          <Routes key={authorizationKey}>
            <Route
              path="/account"
              element={
                <Account
                  token={token}
                  account={routeAccount}
                  onAccount={setAccount}
                  onSession={accept}
                  onSignOut={() => void signOut()}
                />
              }
            />
            <Route
              path="/administration"
              element={
                <Administration token={token} account={routeAccount} />
              }
            />
            {!routeCanView && (
              <Route
                path="*"
                element={
                  <section>
                    <h1>Not permitted</h1>
                    <p>You cannot open this page.</p>
                  </section>
                }
              />
            )}
            {routeCanView && (
              <>
                <Route
                  path="/dashboard"
                  element={<Dashboard token={token} account={routeAccount} />}
                />
                <Route
                  path="/reports"
                  element={<Reports token={token} account={routeAccount} />}
                />
                <Route
                  path="/portfolios"
                  element={
                    <Portfolios token={token} account={routeAccount} />
                  }
                />
                <Route
                  path="/applications"
                  element={
                    <Applications token={token} account={routeAccount} />
                  }
                />
                <Route
                  path="/applications/:applicationId"
                  element={
                    <ApplicationRecord token={token} account={routeAccount} />
                  }
                />
                <Route
                  path="/reviews-due"
                  element={
                    <ReviewsDue token={token} account={routeAccount} />
                  }
                />
                <Route
                  path="/dependencies"
                  element={
                    <Dependencies token={token} account={routeAccount} />
                  }
                />
                <Route
                  path="*"
                  element={
                    <Account
                      token={token}
                      account={routeAccount}
                      onAccount={setAccount}
                      onSession={accept}
                      onSignOut={() => void signOut()}
                    />
                  }
                />
              </>
            )}
          </Routes>
          </div>
        )}
      </main>
    </div>
  );
}

/** Install the application's single browser router. */
export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
