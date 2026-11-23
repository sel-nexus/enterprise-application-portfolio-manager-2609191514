import { useState, type FormEvent } from 'react';
import { ApiError } from '../accounts/api';
import type { Portfolio, PortfolioInput, PortfolioStatus } from './api';

interface Props { portfolio: Portfolio | null; onCancel: () => void; onSave: (input: PortfolioInput) => Promise<void> }

/** Edit a portfolio while retaining input when saving fails. */
export default function PortfolioForm({ portfolio, onCancel, onSave }: Props) {
  const [input, setInput] = useState<PortfolioInput>(portfolio ? { name: portfolio.name, owner: portfolio.owner, product_area: portfolio.product_area, description: portfolio.description, status: portfolio.status } : { name: '', owner: '', product_area: '', description: '', status: 'Active' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (![input.name, input.owner, input.product_area].every(value => value.trim())) { setError('Name, owner and product area are required.'); return; }
    setSaving(true); setError('');
    try { await onSave(input); }
    catch (err) { setError(err instanceof ApiError && err.status === 409 ? err.message : 'This could not be saved. Try again.'); }
    finally { setSaving(false); }
  }
  return (
    <div className="portfolio-overlay">
      <section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="portfolio-form-title">
        <h2 id="portfolio-form-title">{portfolio ? 'Edit portfolio' : 'New portfolio'}</h2>
        <form onSubmit={submit}>
          {error && <p className="error" role="alert">{error}</p>}
          <label htmlFor="portfolio-name">Name</label>
          <input id="portfolio-name" autoFocus required value={input.name} onChange={event => setInput({ ...input, name: event.target.value })} />
          <label htmlFor="portfolio-owner">Owner</label>
          <input id="portfolio-owner" required value={input.owner} onChange={event => setInput({ ...input, owner: event.target.value })} />
          <label htmlFor="portfolio-area">Product area</label>
          <input id="portfolio-area" required value={input.product_area} onChange={event => setInput({ ...input, product_area: event.target.value })} />
          <label htmlFor="portfolio-description">Description</label>
          <textarea id="portfolio-description" value={input.description} onChange={event => setInput({ ...input, description: event.target.value })} />
          <label htmlFor="portfolio-status">Status</label>
          <select id="portfolio-status" value={input.status} onChange={event => setInput({ ...input, status: event.target.value as PortfolioStatus })}>
            <option>Active</option>
            <option>Archived</option>
          </select>
          <div className="actions">
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button className="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
