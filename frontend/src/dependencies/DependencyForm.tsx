import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, type Account } from '../accounts/api';
import { applicationsApi, type Application } from '../applications/api';
import { dependenciesApi, type Relationship } from './api';

interface Props { token: string; account: Account; fromId?: string; onCancel: () => void; onSaved: () => void }

/** Collect a link using visible application identities. */
export default function DependencyForm({ token, account, fromId = '', onCancel, onSaved }: Props) {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [source, setSource] = useState(fromId);
  const [target, setTarget] = useState('');
  const [relationship, setRelationship] = useState<Relationship>('Calls');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      const items: Application[] = [];
      let page = 1;
      do {
        const data = await applicationsApi.list(token, new URLSearchParams({ lifecycle: 'All', include_archived: 'true', page: String(page), page_size: '100' }));
        items.push(...data.items);
        if (items.length >= data.total || !data.items.length) break;
        page += 1;
      } while (active);
      if (active) setApps(items);
    }
    setError('');
    load().catch(() => { if (active) setError('Applications could not be loaded. Try again.'); });
    return () => { active = false; };
  }, [token, retry]);
  const editable = apps?.filter(app => account.role === 'administrator' || account.portfolio_ids.includes(app.portfolio_id)) || [];
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!source || !target) { setError('Choose both applications.'); return; }
    if (source === target) { setError('An application cannot depend on itself.'); return; }
    setBusy(true); setError('');
    try { await dependenciesApi.create(token, { from_application_id: source, to_application_id: target, relationship, note }); onSaved(); }
    catch (err) { setError(err instanceof ApiError && err.status === 409 ? err.message : 'This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <div className="portfolio-overlay">
      <section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="dependency-form-title">
        <h2 id="dependency-form-title">Add dependency</h2>
        <form onSubmit={submit}>
          {error && <p role="alert" className="error">{error}</p>}
          {!apps && !error && <p role="status">Loading applications…</p>}
          {!apps && error && <button type="button" className="secondary" onClick={() => setRetry(x => x + 1)}>Try again</button>}
          <label htmlFor="dependency-from">From</label>
          <select id="dependency-from" autoFocus value={source} disabled={!!fromId || !apps} onChange={e => setSource(e.target.value)} required>
            <option value="">Choose an application</option>
            {editable.map(app => <option value={app.id} key={app.id}>{app.name}</option>)}
          </select>
          <label htmlFor="dependency-relationship">Relationship</label>
          <select id="dependency-relationship" value={relationship} onChange={e => setRelationship(e.target.value as Relationship)}>
            <option>Calls</option><option>Receives data from</option><option>Needs at runtime</option>
          </select>
          <label htmlFor="dependency-to">To</label>
          <select id="dependency-to" value={target} disabled={!apps} onChange={e => setTarget(e.target.value)} required>
            <option value="">Choose an application</option>
            {apps?.filter(app => app.id !== source).map(app => <option value={app.id} key={app.id}>{app.name}</option>)}
          </select>
          <label htmlFor="dependency-note">Note</label>
          <textarea id="dependency-note" maxLength={2000} value={note} onChange={e => setNote(e.target.value)} />
          <div className="actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button><button className="primary" disabled={busy || !apps}>Save</button></div>
        </form>
      </section>
    </div>
  );
}
