import { useEffect, useState } from 'react';
import { adminApi } from './api';

/** Display and persist the review interval. */
export default function Settings({ token }: { token: string }) {
  const [days, setDays] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  async function load() { try { setDays(String((await adminApi.settings(token)).days)); setError(''); } catch { setError('This page could not be loaded'); } }
  useEffect(() => { void load(); }, [token]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    const value = Number(days);
    if (!Number.isInteger(value) || value < 30 || value > 365) { setError('Enter a whole number from 30 to 365.'); return; }
    try { await adminApi.saveInterval(token, value); setMessage('Review interval saved.'); setError(''); } catch { setError('This could not be saved. Try again.'); }
  }
  return <section className="account-card"><h2>Review interval</h2><p>An application is due when it has no review, or when its latest review is older than this many days. Active and deprecated applications in active portfolios are counted.</p>
    {message && <p className="notice" role="status">{message}</p>}{error && <p className="error" role="alert">{error} <button className="text-button" onClick={() => void load()}>Try again</button></p>}
    <form onSubmit={save}><label htmlFor="interval">Days</label><input id="interval" type="number" min="30" max="365" step="1" required value={days} onChange={e => setDays(e.target.value)} /><div className="actions"><button className="primary">Save interval</button></div></form>
  </section>;
}
