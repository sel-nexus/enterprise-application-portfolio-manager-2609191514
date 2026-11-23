import { useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '../accounts/api';
import { portfoliosApi, type Portfolio } from '../portfolios/api';
import type { Application, ApplicationInput, Criticality } from './api';

interface Props { token: string; application: Application | null; onCancel: () => void; onSave: (input: ApplicationInput) => Promise<void> }

/** Edit identity fields without mixing in review measurements. */
export default function ApplicationForm({ token, application, onCancel, onSave }: Props) {
  const [input, setInput] = useState<ApplicationInput>(application ? {
    name: application.name, description: application.description, portfolio_id: application.portfolio_id,
    product_area: application.product_area, business_owner: application.business_owner, technology_owner: application.technology_owner,
    inventory_owner: application.inventory_owner, criticality: application.criticality, tier: application.tier, technology_stack: application.technology_stack,
  } : { name: '', description: '', portfolio_id: '', product_area: '', business_owner: '', technology_owner: '', inventory_owner: '', criticality: 'Medium', tier: 1, technology_stack: '' });
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      const items: Portfolio[] = [];
      let page = 1;
      let total = 0;
      do {
        const result = await portfoliosApi.list(token, '', 'All', page++);
        items.push(...result.items); total = result.total;
      } while (items.length < total);
      if (active) setPortfolios(items);
    }
    load().catch(() => { if (active) setError('Portfolios could not be loaded. Close and try again.'); });
    return () => { active = false; };
  }, [token]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.name.trim() || !input.portfolio_id) { setError('Name and portfolio are required.'); return; }
    setSaving(true); setError('');
    try { await onSave(input); }
    catch (err) { setError(err instanceof ApiError && err.status === 409 ? err.message : 'This could not be saved. Try again.'); }
    finally { setSaving(false); }
  }
  return (
    <div className="portfolio-overlay">
      <section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="application-form-title">
        <h2 id="application-form-title">{application ? 'Edit details' : 'New application'}</h2>
        <form onSubmit={submit}>
          {error && <p className="error" role="alert">{error}</p>}
          <h3>Identity</h3>
          <label htmlFor="app-name">Name</label>
          <input id="app-name" autoFocus required value={input.name} onChange={e => setInput({ ...input, name: e.target.value })} />
          <label htmlFor="app-description">Description</label>
          <textarea id="app-description" value={input.description} onChange={e => setInput({ ...input, description: e.target.value })} />
          <label htmlFor="app-portfolio">Portfolio</label>
          <select id="app-portfolio" required value={input.portfolio_id} onChange={e => setInput({ ...input, portfolio_id: e.target.value })}>
            <option value="">Select a portfolio</option>
            {portfolios.map(p => <option value={p.id} key={p.id}>{p.name}{p.status === 'Archived' ? ' (Archived)' : ''}</option>)}
          </select>
          <label htmlFor="app-area">Product area</label>
          <input id="app-area" value={input.product_area} onChange={e => setInput({ ...input, product_area: e.target.value })} />
          <h3>Ownership</h3>
          <label htmlFor="app-business">Business owner</label>
          <input id="app-business" value={input.business_owner} onChange={e => setInput({ ...input, business_owner: e.target.value })} />
          <label htmlFor="app-technology">Technology owner</label>
          <input id="app-technology" value={input.technology_owner} onChange={e => setInput({ ...input, technology_owner: e.target.value })} />
          <label htmlFor="app-inventory">Inventory owner</label>
          <input id="app-inventory" value={input.inventory_owner} onChange={e => setInput({ ...input, inventory_owner: e.target.value })} />
          <h3>Position</h3>
          <label htmlFor="app-criticality">Criticality</label>
          <select id="app-criticality" value={input.criticality} onChange={e => setInput({ ...input, criticality: e.target.value as Criticality })}>
            <option>Low</option><option>Medium</option><option>High</option><option>Critical</option>
          </select>
          <label htmlFor="app-tier">Tier</label>
          <select id="app-tier" value={input.tier} onChange={e => setInput({ ...input, tier: Number(e.target.value) })}>
            {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <label htmlFor="app-stack">Technology stack</label>
          <input id="app-stack" value={input.technology_stack} onChange={e => setInput({ ...input, technology_stack: e.target.value })} />
          <div className="actions">
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button className="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
