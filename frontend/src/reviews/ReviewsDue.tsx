import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import ReviewForm, { ReviewerAssignment } from './ReviewForm';
import { reviewsApi, type Queue } from './api';

interface Props { token: string; account: Account }

/** Show due reviews and provide scoped row actions. */
export default function ReviewsDue({ token, account }: Props) {
  const [params, setParams] = useSearchParams();
  const [result, setResult] = useState<Queue | null>(null);
  const [portfolios, setPortfolios] = useState<Queue['chart']>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState('');
  const [assignment, setAssignment] = useState('');
  const [notice, setNotice] = useState('');
  const canEdit = ['administrator', 'portfolio_leader', 'engineer'].includes(account.role);
  const page = Math.max(1, Number(params.get('page')) || 1);
  function change(key: string, value: string) { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); setParams(next); }
  useEffect(() => {
    let active = true;
    reviewsApi.due(token, new URLSearchParams()).then(data => { if (active) setPortfolios(data.chart); }).catch(() => { if (active) setError('This page could not be loaded'); });
    return () => { active = false; };
  }, [token, revision]);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    reviewsApi.due(token, params).then(data => { if (active) setResult(data); }).catch(() => { if (active) setError('This page could not be loaded'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, params.toString(), revision]);
  return <>
    <header><h1>Reviews due</h1><p>Applications with no review, or with a review older than the interval.</p></header>
    {notice && <p role="status" className="notice">{notice}</p>}
    {error && <div role="alert" className="account-card"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
    {loading && <p role="status">Loading reviews…</p>}
    {result && !loading && <>
      <div className="notice"><strong>Due now: {result.due_count}</strong><p>Review interval: {result.interval} days</p><p>Recording a review dated inside the interval removes the application from this queue.</p></div>
      <section className="portfolio-detail"><h2>Current and due by portfolio</h2>{result.chart.map(c => <div key={c.portfolio_id}><strong>{c.portfolio_name}</strong><div className="review-chart" aria-label={`${c.current} current, ${c.due} due`}><span className="review-current" style={{ flex: c.current }} /><span className="review-due" style={{ flex: c.due }} /></div><p>Current {c.current} · Due {c.due}</p></div>)}</section>
      <div className="portfolio-filters"><label>Portfolio<select value={params.get('portfolio_id') || ''} onChange={e => change('portfolio_id', e.target.value)}><option value="">All</option>{portfolios.map(c => <option value={c.portfolio_id} key={c.portfolio_id}>{c.portfolio_name}</option>)}</select></label><label>Standing<select value={params.get('standing') || 'All due'} onChange={e => change('standing', e.target.value === 'All due' ? '' : e.target.value)}><option>All due</option><option>No review</option><option>Overdue</option></select></label></div>
      <section className="portfolio-list">{result.items.length === 0 ? <p>{params.get('standing') || params.get('portfolio_id') ? 'Nothing in this queue matches.' : 'Every application you can see has a current review.'} <Link to="/applications">Open applications</Link></p> : <div className="table-scroll"><table><thead><tr>{['Application', 'Portfolio', 'Last review', 'Days since review', 'Assigned reviewer', 'Risk', 'Actions'].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{result.items.map(row => <tr key={row.application_id}><td><Link to={`/applications/${row.application_id}`}>{row.application_name}</Link></td><td>{row.portfolio_name}</td><td>{row.last_review || 'No review'}</td><td>{row.days_since_review ?? '—'}</td><td>{row.assigned_reviewer_name || 'Not assigned'}</td><td>{row.risk || 'No review'}</td><td>{canEdit && <><button className="text-button" onClick={() => setForm(row.application_id)}>Record a review</button><button className="text-button" onClick={() => setAssignment(row.application_id)}>Assign reviewer</button></>}</td></tr>)}</tbody></table></div>}
        <div className="pagination"><button className="text-button" disabled={page === 1} onClick={() => change('page', String(page - 1))}>Previous</button><span>Page {page} · {result.total} results</span><button className="text-button" disabled={page * result.page_size >= result.total} onClick={() => change('page', String(page + 1))}>Next</button></div>
      </section>
    </>}
    {form && <ReviewForm token={token} applicationId={form} onCancel={() => setForm('')} onSaved={() => { setForm(''); setNotice('Review recorded'); setRevision(x => x + 1); }} />}
    {assignment && <ReviewerAssignment token={token} applicationId={assignment} current={result?.items.find(row => row.application_id === assignment)?.assigned_reviewer_id} onCancel={() => setAssignment('')} onSaved={() => { setAssignment(''); setNotice('Reviewer assigned'); setRevision(x => x + 1); }} />}
  </>;
}
