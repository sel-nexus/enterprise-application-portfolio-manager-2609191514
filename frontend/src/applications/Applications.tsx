import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import { portfoliosApi, type Portfolio } from '../portfolios/api';
import ApplicationForm from './ApplicationForm';
import { reviewsApi, type Review } from '../reviews/api';
import { applicationsApi, type ApplicationInput, type ApplicationPage } from './api';

interface Props { token: string; account: Account }

/** Browse the authorized application inventory. */
export default function Applications({ token, account }: Props) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [result, setResult] = useState<ApplicationPage | null>(null);
  const [latest, setLatest] = useState<Record<string, Review | undefined>>({});
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(false);
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
    applicationsApi.list(token, params).then(async data => {
      const reviews = await Promise.all(data.items.map(item => reviewsApi.history(token, item.id)));
      if (active) { setResult(data); setLatest(Object.fromEntries(data.items.map((item, index) => [item.id, reviews[index].items[0]]))); }
    })
      .catch(() => { if (active) setError('This page could not be loaded'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, params.toString(), revision]);
  useEffect(() => {
    let active = true;
    async function load() {
      let pageNumber = 1; let total = 0; const items: Portfolio[] = [];
      do {
        const data = await portfoliosApi.list(token, '', 'All', pageNumber++);
        items.push(...data.items); total = data.total;
      } while (items.length < total);
      if (active) setPortfolios(items);
    }
    load().catch(() => { if (active) setError('This page could not be loaded'); });
    return () => { active = false; };
  }, [token, revision]);
  async function save(input: ApplicationInput) {
    const item = await applicationsApi.create(token, input);
    setForm(false);
    navigate(`/applications/${item.id}`, { state: { notice: 'Application saved.' } });
  }
  return (
    <>
      <header className="portfolio-header">
        <div><h1>Applications</h1><p>Every application in the portfolios you can see.</p></div>
        {canEdit && <button className="primary" onClick={() => setForm(true)}>New application</button>}
      </header>
      {error && <div className="account-card" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
      <div className="portfolio-filters application-filters">
        <label>Search name or business owner<input value={params.get('search') || ''} onChange={e => change('search', e.target.value)} /></label>
        <label>Portfolio<select value={params.get('portfolio_id') || ''} onChange={e => change('portfolio_id', e.target.value)}><option value="">All</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Criticality<select value={params.get('criticality') || 'All'} onChange={e => change('criticality', e.target.value)}>{['All', 'Low', 'Medium', 'High', 'Critical'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label>Lifecycle<select value={params.get('lifecycle') || 'Default'} onChange={e => change('lifecycle', e.target.value)}><option value="Default">Active and Deprecated</option>{['All', 'Active', 'Deprecated', 'Retired'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="radio"><input type="checkbox" checked={params.get('include_archived') === 'true'} onChange={e => change('include_archived', e.target.checked ? 'true' : '')} />Include archived portfolios</label>
        <button className="text-button" onClick={() => setParams({})}>Clear filters</button>
      </div>
      {loading && <p role="status">Loading applications…</p>}
      {!loading && result && <section className="portfolio-list" aria-label="Application list">
        {result.items.length === 0 ? <p>{params.toString() ? 'No applications match.' : 'No applications yet.'}</p> : <div className="table-scroll"><table>
          <thead><tr><th scope="col">Name</th><th scope="col">Portfolio</th><th scope="col">Criticality</th><th scope="col">Tier</th><th scope="col">Lifecycle</th><th scope="col">Health</th><th scope="col">Automation coverage</th><th scope="col">Open critical defects</th><th scope="col">Risk</th></tr></thead>
          <tbody>{result.items.map(item => <tr key={item.id}><td><Link to={`/applications/${item.id}`}>{item.name}</Link></td><td>{item.portfolio_name}</td><td>{item.criticality}</td><td>{item.tier}</td><td>{item.lifecycle}</td><td>{latest[item.id]?.health ?? '—'}</td><td>{latest[item.id]?.automation_coverage ?? '—'}</td><td>{latest[item.id]?.open_critical_defects ?? '—'}</td><td>{latest[item.id]?.risk || 'No review'}</td></tr>)}</tbody>
        </table></div>}
        <div className="pagination"><button className="text-button" disabled={page === 1} onClick={() => change('page', String(page - 1))}>Previous</button><span>Page {page} · {result.total ? (page - 1) * result.page_size + 1 : 0}–{Math.min(page * result.page_size, result.total)} of {result.total}</span><button className="text-button" disabled={page * result.page_size >= result.total} onClick={() => change('page', String(page + 1))}>Next</button></div>
      </section>}
      {form && <ApplicationForm token={token} application={null} onCancel={() => setForm(false)} onSave={save} />}
    </>
  );
}
