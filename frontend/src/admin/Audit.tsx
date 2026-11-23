import { useEffect, useState } from 'react';
import { adminApi, type AuditEntry } from './api';

/** Filter and export the authorized audit history. */
export default function Audit({ token }: { token: string }) {
  const [who, setWho] = useState('');
  const [action, setAction] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const params = () => { const p = new URLSearchParams({ page: String(page) }); if (who) p.set('who', who); if (action) p.set('action', action); if (start) p.set('start', start); if (end) p.set('end', end); return p; };
  async function load() { try { const result = await adminApi.audit(token, params()); setItems(result.items); setTotal(result.total); setError(''); } catch { setError('This page could not be loaded'); } }
  useEffect(() => { void load(); }, [token, page]);
  async function exportCsv() { try { await adminApi.exportAudit(token, params()); } catch { setError('Export failed. Try again.'); } }
  return <section><div className="portfolio-header"><h2>Audit</h2><button className="secondary" onClick={() => void exportCsv()}>Export CSV</button></div>
    <form className="portfolio-filters" onSubmit={e => { e.preventDefault(); if (page === 1) void load(); else setPage(1); }}>
      <label>Person<input value={who} onChange={e => setWho(e.target.value)} /></label><label>Action<input value={action} onChange={e => setAction(e.target.value)} /></label><label>From<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label><label>To<input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label><button className="secondary">Filter</button>
    </form>
    {error && <p role="alert" className="error">{error} <button onClick={() => void load()}>Try again</button></p>}
    <div className="portfolio-list table-scroll"><table><thead><tr>{['When', 'Who', 'Action', 'Record', 'Summary'].map(x => <th key={x} scope="col">{x}</th>)}</tr></thead><tbody>{items.map(row => <tr key={row.id}><td>{new Date(row.when).toLocaleString()}</td><td>{row.who}</td><td>{row.action}</td><td>{row.record}</td><td>{row.summary}</td></tr>)}</tbody></table>{!items.length && <p>No audit entries match.</p>}</div>
    <div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} · {total} entries</span><button disabled={page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button></div>
  </section>;
}
