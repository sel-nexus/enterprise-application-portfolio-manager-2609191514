import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import { reportingApi, type DashboardData, type PortfolioRow } from './api';

/** Show scoped latest-review measures and portfolio comparisons. */
export default function Dashboard({ token, account }: { token: string; account: Account }) {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    reportingApi.dashboard(token, params).then(value => { if (active) setData(value); }).catch(() => { if (active) setError('This page could not be loaded'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, params.toString(), revision]);
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  }
  function chart(title: string, field: 'quality' | 'applications_at_risk', groups: PortfolioRow[]) {
    const max = field === 'quality' ? 100 : Math.max(1, ...groups.map(row => row.applications_at_risk));
    return <section className="portfolio-list"><h2>{title}</h2>{groups.length ? groups.map(row => <div className="dependency-bar-row" key={row.id}><Link to={`/portfolios?portfolio=${row.id}`}>{row.name}</Link><div className="dependency-track"><div className={field === 'quality' ? 'dependency-bar' : 'dependency-bar risk-bar'} style={{ width: `${(row[field] || 0) / max * 100}%` }} /></div><span>{row[field] ?? '—'}</span></div>) : <><p>Nothing matches these filters.</p><button className="text-button" onClick={() => setParams({})}>Clear filters</button></>}</section>;
  }
  return <>
    <header className="portfolio-header"><div><h1>Executive dashboard</h1><p>Latest quality reviews across the portfolios you can see.</p></div>{account.role !== 'read_only' && <Link className="secondary" to="/reports">Go to reports</Link>}</header>
    <div className="portfolio-filters application-filters">
      <label>Portfolio<select value={params.get('portfolio_id') || ''} onChange={e => change('portfolio_id', e.target.value)}><option value="">All</option>{data?.portfolio_options.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Product area<select value={params.get('product_area') || ''} onChange={e => change('product_area', e.target.value)}><option value="">All</option>{data?.product_areas.map(area => <option key={area}>{area}</option>)}</select></label>
      <label>Risk<select value={params.get('risk') || 'All'} onChange={e => change('risk', e.target.value === 'All' ? '' : e.target.value)}>{['All', 'Low', 'Medium', 'High', 'No review'].map(value => <option key={value}>{value}</option>)}</select></label>
      {params.toString() && <button className="text-button" onClick={() => setParams({})}>Clear filters</button>}
    </div>
    {loading && <p role="status">Loading dashboard…</p>}
    {error && <div role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
    {!loading && !error && data && <>
      <div className="dashboard-metrics">{[['Average quality', data.quality], ['Average health', data.health], ['Average automation coverage', data.automation_coverage], ['Open critical defects', data.open_critical_defects], ['Applications at risk', data.applications_at_risk], ['Applications', data.applications]].map(([label, value]) => <section className="metric" key={label}><h2>{label}</h2><strong>{value ?? '—'}</strong>{label === 'Applications' && <div>{data.portfolios} portfolios</div>}</section>)}</div>
      <div className="dashboard-charts">{chart('Quality by portfolio', 'quality', data.groups)}{chart('Applications at risk by portfolio', 'applications_at_risk', data.groups)}</div>
      <section className="portfolio-list"><h2>Lowest portfolio quality</h2><div className="table-scroll"><table><thead><tr>{['Portfolio', 'Product area', 'Quality', 'Applications at risk', 'Open critical defects'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{data.groups.slice(0, 5).map(row => <tr key={row.id}><td><Link to={`/portfolios?portfolio=${row.id}`}>{row.name}</Link></td><td>{row.product_area}</td><td>{row.quality ?? '—'}</td><td>{row.applications_at_risk}</td><td>{row.open_critical_defects}</td></tr>)}</tbody></table></div></section>
    </>}
  </>;
}
