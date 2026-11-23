import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import DependencyForm from './DependencyForm';
import { dependenciesApi, type Dependency, type DependencyPage } from './api';

interface Props { token: string; account: Account }

/** Confirm and remove a directional link. */
export function RemoveDependency({ token, link, onCancel, onRemoved }: { token: string; link: Dependency; onCancel: () => void; onRemoved: () => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function remove() {
    setBusy(true); setError('');
    try { await dependenciesApi.remove(token, link.id); onRemoved(); }
    catch { setError('This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <div className="portfolio-overlay">
      <section className="portfolio-dialog" role="dialog" aria-modal="true" aria-labelledby="remove-dependency-title">
        <h2 id="remove-dependency-title">Remove dependency</h2>
        <p>Remove the link from {link.from_name} to {link.to_name}? Both application records will update.</p>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="actions"><button className="secondary" onClick={onCancel}>Cancel</button><button className="danger-button" disabled={busy} onClick={() => void remove()}>Remove</button></div>
      </section>
    </div>
  );
}

/** Display the scoped dependency table, filters, and estate summary. */
export default function Dependencies({ token, account }: Props) {
  const [params, setParams] = useSearchParams();
  const [result, setResult] = useState<DependencyPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(false);
  const [removing, setRemoving] = useState<Dependency | null>(null);
  const [notice, setNotice] = useState('');
  const canEdit = ['administrator', 'portfolio_leader', 'engineer'].includes(account.role);
  const page = Math.max(1, Number(params.get('page')) || 1);
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next);
  }
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    dependenciesApi.list(token, params).then(data => { if (active) setResult(data); })
      .catch(() => { if (active) setError('This page could not be loaded'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, params.toString(), revision]);
  return (
    <>
      <header className="portfolio-header">
        <div><h1>Dependencies</h1><p>Links recorded between applications: calls, receives data from, or needs at runtime.</p></div>
        {canEdit && <button className="primary" onClick={() => setForm(true)}>Add dependency</button>}
      </header>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <div className="account-card" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
      {loading && <p role="status">Loading dependencies…</p>}
      {result && !error && <>
        <div className="dependency-summary">
          <section className="portfolio-detail"><h2>Most depended on</h2>
            {result.chart.length ? result.chart.map(row => <div key={row.application_id} className="dependency-bar-row"><Link to={`/applications/${row.application_id}`}>{row.application_name}</Link><div className="dependency-track"><div className="dependency-bar" style={{ width: `${row.count / result.chart[0].count * 100}%` }} /></div><span>{row.count}</span></div>) : <p>No incoming links recorded.</p>}
          </section>
          <section className="portfolio-detail"><h2>No recorded dependency</h2><strong>{result.unlinked_count}</strong><p>Active or deprecated applications with no links.</p></section>
        </div>
        <div className="portfolio-filters">
          <label>Search<input value={params.get('search') || ''} onChange={e => change('search', e.target.value)} /></label>
          <label>Relationship<select value={params.get('relationship') || ''} onChange={e => change('relationship', e.target.value)}><option value="">All</option><option>Calls</option><option>Receives data from</option><option>Needs at runtime</option></select></label>
          <label>Portfolio (of To)<select value={params.get('portfolio_id') || ''} onChange={e => change('portfolio_id', e.target.value)}><option value="">All</option>{result.portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        </div>
        <section className="portfolio-list">
          {!result.items.length ? <p>{params.get('search') || params.get('relationship') || params.get('portfolio_id') ? 'No dependency matches that search.' : 'No dependencies recorded yet.'}</p> : <div className="table-scroll"><table><thead><tr>{['From', 'Relationship', 'To', 'Note', 'Portfolio', 'Actions'].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{result.items.map(link => <tr key={link.id}><td><Link to={`/applications/${link.from_application_id}`}>{link.from_name}</Link></td><td>{link.relationship}</td><td><Link to={`/applications/${link.to_application_id}`}>{link.to_name}</Link></td><td>{link.note || '—'}</td><td>{link.portfolio_name}</td><td>{canEdit && (account.role === 'administrator' || account.portfolio_ids.includes(link.from_portfolio_id)) && <button className="text-button danger" onClick={() => setRemoving(link)}>Remove</button>}</td></tr>)}</tbody></table></div>}
          <div className="pagination"><button className="text-button" disabled={page === 1} onClick={() => change('page', String(page - 1))}>Previous</button><span>Page {page} · {result.total} results</span><button className="text-button" disabled={page * result.page_size >= result.total} onClick={() => change('page', String(page + 1))}>Next</button></div>
        </section>
      </>}
      {form && <DependencyForm token={token} account={account} onCancel={() => setForm(false)} onSaved={() => { setForm(false); setNotice('Dependency added'); setRevision(x => x + 1); }} />}
      {removing && <RemoveDependency token={token} link={removing} onCancel={() => setRemoving(null)} onRemoved={() => { setRemoving(null); setNotice('Dependency removed'); setRevision(x => x + 1); }} />}
    </>
  );
}

/** Show an application's outgoing and incoming links independently. */
export function ApplicationDependencies({ token, account, applicationId }: Props & { applicationId: string }) {
  const [outgoing, setOutgoing] = useState<DependencyPage | null>(null);
  const [incoming, setIncoming] = useState<DependencyPage | null>(null);
  const [outPage, setOutPage] = useState(1);
  const [inPage, setInPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(false);
  const [removing, setRemoving] = useState<Dependency | null>(null);
  const [notice, setNotice] = useState('');
  const canEdit = ['administrator', 'portfolio_leader', 'engineer'].includes(account.role);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    Promise.all(['outgoing', 'incoming'].map((direction, index) => dependenciesApi.list(token, new URLSearchParams({ application_id: applicationId, direction, page: String(index ? inPage : outPage) }))))
      .then(([out, incomingLinks]) => { if (active) { setOutgoing(out); setIncoming(incomingLinks); } })
      .catch(() => { if (active) setError('Dependencies could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, applicationId, revision, outPage, inPage]);
  function list(title: string, data: DependencyPage | null, page: number, setPage: (page: number) => void, outgoingList: boolean) {
    return <section className="portfolio-detail"><h2>{title}</h2>
      {outgoingList && canEdit && <button className="text-button" onClick={() => setForm(true)}>Add dependency</button>}
      {!data?.items.length ? <p>No dependencies recorded.</p> : <ul>{data.items.map(link => <li key={link.id}>{link.relationship} <Link to={`/applications/${outgoingList ? link.to_application_id : link.from_application_id}`}>{outgoingList ? link.to_name : link.from_name}</Link>{link.note && ` — ${link.note}`}{outgoingList && canEdit && <button className="text-button danger" onClick={() => setRemoving(link)}>Remove</button>}</li>)}</ul>}
      {data && data.total > data.page_size && <div className="pagination"><button className="text-button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} · {data.total} results</span><button className="text-button" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button></div>}
    </section>;
  }
  return <>
    {notice && <p className="notice" role="status">{notice}</p>}
    {loading && <p role="status">Loading dependencies…</p>}
    {error && <div role="alert" className="account-card"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
    {!loading && !error && <div className="dependency-summary">{list('Depends on', outgoing, outPage, setOutPage, true)}{list('Used by', incoming, inPage, setInPage, false)}</div>}
    {form && <DependencyForm token={token} account={account} fromId={applicationId} onCancel={() => setForm(false)} onSaved={() => { setForm(false); setNotice('Dependency added'); setOutPage(1); setRevision(x => x + 1); }} />}
    {removing && <RemoveDependency token={token} link={removing} onCancel={() => setRemoving(null)} onRemoved={() => { setRemoving(null); setNotice('Dependency removed'); setOutPage(1); setRevision(x => x + 1); }} />}
  </>;
}
