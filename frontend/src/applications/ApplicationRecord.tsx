import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import ApplicationForm from './ApplicationForm';
import { applicationsApi, type Application, type ApplicationInput, type Lifecycle } from './api';

interface Props { token: string; account: Account }

/** Display an application and manage its identity and lifecycle. */
export default function ApplicationRecord({ token, account }: Props) {
  const { applicationId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [item, setItem] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<string>((location.state as { notice?: string } | null)?.notice || '');
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(false);
  const [dialog, setDialog] = useState<'lifecycle' | 'delete' | null>(null);
  const [lifecycle, setLifecycle] = useState<Lifecycle>('Active');
  const [busy, setBusy] = useState(false);
  const canEdit = ['administrator', 'portfolio_leader', 'engineer'].includes(account.role);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    applicationsApi.get(token, applicationId).then(data => { if (active) { setItem(data); setLifecycle(data.lifecycle); } })
      .catch(() => { if (active) setError('This page could not be loaded'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, applicationId, revision]);
  async function save(input: ApplicationInput) {
    const saved = await applicationsApi.update(token, applicationId, input);
    setItem(saved); setForm(false); setNotice('Application saved.');
  }
  async function confirm() {
    setBusy(true); setError('');
    try {
      if (dialog === 'delete') {
        await applicationsApi.remove(token, applicationId);
        navigate('/applications');
      } else {
        const saved = await applicationsApi.lifecycle(token, applicationId, lifecycle);
        setItem(saved); setNotice('Lifecycle changed.'); setDialog(null);
      }
    } catch { setError('This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <>
      <Link to="/applications">← Applications</Link>
      {loading && <p role="status">Loading application…</p>}
      {error && <div className="account-card" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision(x => x + 1)}>Try again</button></div>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {item && <>
        <header className="application-record-header">
          <h1>{item.name}</h1>
          <Link to={`/portfolios?portfolio=${encodeURIComponent(item.portfolio_id)}`}>{item.portfolio_name}</Link>
          <p>{item.criticality} · Tier {item.tier} · {item.lifecycle} · Risk unavailable</p>
          <p>{item.description || 'No description yet.'}</p>
          <div className="portfolio-actions">
            {canEdit && <button className="secondary" onClick={() => setForm(true)}>Edit details</button>}
            {canEdit && <button className="secondary" onClick={() => setDialog('lifecycle')}>Change lifecycle</button>}
            {account.role === 'administrator' && <button className="text-button danger" onClick={() => setDialog('delete')}>Delete</button>}
          </div>
        </header>
        <div className="application-cards">
          <section className="portfolio-detail"><h2>Ownership</h2><dl><dt>Business owner</dt><dd>{item.business_owner || 'Not named'}</dd><dt>Technology owner</dt><dd>{item.technology_owner || 'Not named'}</dd><dt>Inventory owner</dt><dd>{item.inventory_owner || 'Not named'}</dd><dt>Assigned reviewer</dt><dd>Unavailable</dd></dl></section>
          <section className="portfolio-detail"><h2>Position</h2><dl><dt>Product area</dt><dd>{item.product_area || 'Not named'}</dd><dt>Technology stack</dt><dd>{item.technology_stack || 'Not named'}</dd><dt>Lifecycle</dt><dd>{item.lifecycle}</dd><dt>Criticality</dt><dd>{item.criticality}</dd><dt>Tier</dt><dd>{item.tier}</dd></dl></section>
          <section className="portfolio-detail"><h2>Latest review</h2><p>Review data is not yet available.</p></section>
        </div>
        <section className="portfolio-detail"><h2>Dependencies</h2><p>Dependency data is not yet available.</p></section>
        {form && <ApplicationForm token={token} application={item} onCancel={() => setForm(false)} onSave={save} />}
        {dialog && <div className="portfolio-overlay"><section className="portfolio-dialog" role="dialog" aria-modal="true" aria-labelledby="application-dialog-title">
          <h2 id="application-dialog-title">{dialog === 'delete' ? `Delete ${item.name}?` : 'Change lifecycle'}</h2>
          {dialog === 'delete' ? <p>The application, its reviews, and its dependency links will leave the inventory. Dashboard totals will change with them.</p> : <fieldset><legend>Lifecycle</legend>
            {(['Active', 'Deprecated', 'Retired'] as Lifecycle[]).map(value => <label className="radio" key={value}><input type="radio" name="lifecycle" value={value} checked={lifecycle === value} onChange={() => setLifecycle(value)} /><span>{value}<small>{value === 'Active' ? 'Counted on dashboard.' : value === 'Deprecated' ? 'Still counted and winding down.' : 'Leaves dashboard but record remains.'}</small></span></label>)}
          </fieldset>}
          <div className="actions"><button className="secondary" onClick={() => setDialog(null)}>Cancel</button><button className={dialog === 'delete' ? 'danger-button' : 'primary'} disabled={busy} onClick={() => void confirm()}>{dialog === 'delete' ? 'Delete' : 'Save'}</button></div>
        </section></div>}
      </>}
    </>
  );
}
