import { useEffect, useState } from 'react';
import type { Account } from '../accounts/api';
import PortfolioForm from './PortfolioForm';
import { portfoliosApi, type Portfolio, type PortfolioInput, type PortfolioPage } from './api';
import { applicationsApi, type Application } from '../applications/api';
import { reviewsApi, type Review } from '../reviews/api';
import { reportingApi, type ReportRow } from '../reporting/api';

interface Props { token: string; account: Account }

/** Display and manage the portfolios visible to the signed-in person. */
export default function Portfolios({ token, account }: Props) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('Active');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<PortfolioPage | null>(null);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [latest, setLatest] = useState<Record<string, Review | undefined>>({});
  const [rollups, setRollups] = useState<Record<string, ReportRow>>({});
  const [applicationsError, setApplicationsError] = useState('');
  const [form, setForm] = useState<'new' | 'edit' | null>(null);
  const [dialog, setDialog] = useState<'archive' | 'delete' | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const canEdit = ['administrator', 'portfolio_leader'].includes(account.role);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('portfolio');
    if (id) portfoliosApi.get(token, id).then(setSelected).catch(() => setError('This page could not be loaded'));
  }, [token]);
  useEffect(() => {
    if (!selected) { setApplications([]); return; }
    let active = true;
    setApplicationsError('');
    applicationsApi.list(token, new URLSearchParams({ portfolio_id: selected.id, lifecycle: 'All', include_archived: 'true' }))
      .then(async result => { const reviews = await Promise.all(result.items.map(item => reviewsApi.history(token, item.id))); if (active) { setApplications(result.items); setLatest(Object.fromEntries(result.items.map((item, index) => [item.id, reviews[index].items[0]]))); } })
      .catch(() => { if (active) setApplicationsError('Applications could not be loaded.'); });
    return () => { active = false; };
  }, [token, selected?.id]);
  useEffect(() => {
    let active = true;
    async function load() {
      let pageNumber = 1; let total = 0; const items: ReportRow[] = [];
      do { const data = await reportingApi.report(token, 'portfolios', new URLSearchParams({ page: String(pageNumber++), page_size: '100' })); items.push(...data.items); total = data.total; } while (items.length < total);
      if (active) setRollups(Object.fromEntries(items.map(item => [String(item.id), item])));
    }
    load().catch(() => { if (active) setError('This page could not be loaded'); });
    return () => { active = false; };
  }, [token, revision]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    portfoliosApi.list(token, search, status, page).then(data => { if (active) setResult(data); }).catch(() => { if (active) setError('This page could not be loaded'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, search, status, page, revision]);
  async function save(input: PortfolioInput) {
    const saved = form === 'edit' && selected ? await portfoliosApi.update(token, selected.id, input) : await portfoliosApi.create(token, input);
    setSelected(saved); setForm(null); setNotice('Portfolio saved.'); setRevision(value => value + 1);
  }
  async function confirm() {
    if (!selected || !dialog) return;
    setBusy(true); setError('');
    try {
      if (dialog === 'archive') { setSelected(await portfoliosApi.archive(token, selected.id)); setNotice('Portfolio archived.'); }
      else { await portfoliosApi.remove(token, selected.id); setSelected(null); setNotice('Portfolio deleted.'); }
      setDialog(null); setRevision(value => value + 1);
    } catch (err) { setError(err instanceof Error ? err.message : 'This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <>
      <header className="portfolio-header">
        <div>
          <h1>Portfolios</h1>
          <p>Groups of applications owned by one part of the organization.</p>
        </div>
        {canEdit && <button className="primary" onClick={() => setForm('new')}>New portfolio</button>}
      </header>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <div className="account-card" role="alert"><p>{error}</p><button className="secondary" onClick={() => { setError(''); setRevision(value => value + 1); }}>Try again</button></div>}
      <div className="portfolio-filters">
        <label>Search name or owner<input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} /></label>
        <label>Status<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option>Active</option><option>Archived</option><option>All</option></select></label>
      </div>
      {loading && <p role="status">Loading portfolios…</p>}
      {!loading && result && <div className={selected ? 'portfolio-layout selected' : 'portfolio-layout'}>
        <section className="portfolio-list" aria-label="Portfolio list">
          {result.items.length === 0 ? <p>{search ? 'No portfolio matches that search.' : 'No portfolios yet.'}</p> : <div className="table-scroll"><table>
            <thead><tr><th scope="col">Name</th><th scope="col">Owner</th><th scope="col">Product area</th><th scope="col">Applications</th><th scope="col">Quality</th><th scope="col">Status</th></tr></thead>
            <tbody>{result.items.map(item => <tr key={item.id} className={selected?.id === item.id ? 'selected-row' : ''}><td><button className="text-button" onClick={() => setSelected(item)}>{item.name}</button></td><td>{item.owner}</td><td>{item.product_area}</td><td>{item.application_count}</td><td>{rollups[item.id]?.quality ?? '—'}</td><td><span className={`status-chip ${item.status.toLowerCase()}`}>{item.status}</span></td></tr>)}</tbody>
          </table></div>}
          <div className="pagination"><button className="text-button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} · {result.total ? (page - 1) * result.page_size + 1 : 0}–{Math.min(page * result.page_size, result.total)} of {result.total}</span><button className="text-button" disabled={page * result.page_size >= result.total} onClick={() => setPage(page + 1)}>Next</button></div>
        </section>
        {selected && <section className="portfolio-detail" aria-label="Portfolio details">
          <h2>{selected.name}</h2><span className={`status-chip ${selected.status.toLowerCase()}`}>{selected.status}</span>
          <dl><dt>Owner</dt><dd>{selected.owner}</dd><dt>Product area</dt><dd>{selected.product_area}</dd><dt>Description</dt><dd>{selected.description || 'No description yet.'}</dd><dt>Applications</dt><dd>{selected.application_count}</dd><dt>Quality</dt><dd>{rollups[selected.id]?.quality ?? '—'}</dd><dt>Open critical defects</dt><dd>{rollups[selected.id]?.open_critical_defects ?? '—'}</dd></dl>
          <h3>Applications</h3>
          {applicationsError && <p role="alert">{applicationsError}</p>}
          {applications.map(item => <p key={item.id}><a href={`/applications/${item.id}`}>{item.name}</a> · {item.criticality} · {item.lifecycle} · Health {latest[item.id]?.health ?? '—'} · {latest[item.id]?.risk || 'No review'}</p>)}
          {selected.application_count > applications.length && <a href={`/applications?portfolio_id=${encodeURIComponent(selected.id)}&lifecycle=All&include_archived=true`}>View all applications</a>}
          <div className="portfolio-actions">{canEdit && <button className="secondary" onClick={() => setForm('edit')}>Edit</button>}{canEdit && selected.status === 'Active' && <button className="text-button danger" onClick={() => setDialog('archive')}>Archive</button>}{account.role === 'administrator' && <button className="text-button danger" onClick={() => setDialog('delete')}>Delete</button>}</div>
        </section>}
      </div>}
      {form && <PortfolioForm portfolio={form === 'edit' ? selected : null} onCancel={() => setForm(null)} onSave={save} />}
      {dialog && selected && <div className="portfolio-overlay"><section className="portfolio-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><h2 id="confirm-title">{dialog === 'archive' ? `Archive ${selected.name}?` : `Delete ${selected.name}?`}</h2><p>{dialog === 'archive' ? 'It will leave the executive dashboard. Its applications stay in the inventory and can still be opened from this page by including archived portfolios.' : selected.application_count ? 'Move or delete the applications first, or archive the portfolio instead.' : 'This cannot be undone.'}</p><div className="actions"><button className="secondary" onClick={() => setDialog(null)}>{dialog === 'delete' && selected.application_count ? 'Close' : 'Cancel'}</button>{!(dialog === 'delete' && selected.application_count) && <button className="danger-button" disabled={busy} onClick={() => void confirm()}>{dialog === 'archive' ? 'Archive' : 'Delete'}</button>}</div></section></div>}
    </>
  );
}
