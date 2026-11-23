import { useEffect, useState, type FormEvent } from 'react';
import { reviewsApi, type ReviewInput } from './api';

interface Props { token: string; applicationId: string; onCancel: () => void; onSaved: () => void }

/** Collect a point-in-time application assessment. */
export default function ReviewForm({ token, applicationId, onCancel, onSaved }: Props) {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const [values, setValues] = useState({ date: today, health: '', quality: '', automation_coverage: '', unit_test_coverage: '', open_defects: '', open_critical_defects: '', risk: 'Low', note: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const fields = [ ['health', 'Health'], ['quality', 'Quality'], ['automation_coverage', 'Automation coverage'], ['unit_test_coverage', 'Unit-test coverage'], ['open_defects', 'Open defects'], ['open_critical_defects', 'Open critical defects'] ] as const;
  async function submit(event: FormEvent) {
    event.preventDefault();
    const percentages = fields.slice(0, 4).map(([key]) => Number(values[key]));
    if (fields.some(([key]) => values[key] === '') || percentages.some(n => !Number.isFinite(n) || n < 0 || n > 100)) { setError('Enter a number from 0 to 100.'); return; }
    const defects = Number(values.open_defects), critical = Number(values.open_critical_defects);
    if (!Number.isInteger(defects) || !Number.isInteger(critical) || defects < 0 || critical < 0) { setError('Enter non-negative whole numbers for defects.'); return; }
    if (critical > defects) { setError('Critical defects cannot exceed open defects.'); return; }
    if (!values.date || values.date > today) { setError('Review date cannot be in the future.'); return; }
    setBusy(true); setError('');
    try {
      await reviewsApi.record(token, applicationId, { ...values, health: Number(values.health), quality: Number(values.quality), automation_coverage: Number(values.automation_coverage), unit_test_coverage: Number(values.unit_test_coverage), open_defects: defects, open_critical_defects: critical } as ReviewInput);
      onSaved();
    } catch { setError('This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return <div className="portfolio-overlay"><section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="review-form-title">
    <h2 id="review-form-title">Record a review</h2>
    <form onSubmit={submit} noValidate>
      {error && <p role="alert" className="error">{error}</p>}
      <label htmlFor="review-date">Date</label><input id="review-date" type="date" autoFocus max={today} value={values.date} onChange={e => setValues({ ...values, date: e.target.value })} />
      {fields.map(([key, label], index) => <div key={key}><label htmlFor={key}>{label}</label><input id={key} type="number" min="0" max={index < 4 ? 100 : undefined} step={index < 4 ? 'any' : 1} value={values[key]} onChange={e => setValues({ ...values, [key]: e.target.value })} /></div>)}
      <label htmlFor="review-risk">Risk</label><select id="review-risk" value={values.risk} onChange={e => setValues({ ...values, risk: e.target.value })}>{['Low', 'Medium', 'High'].map(x => <option key={x}>{x}</option>)}</select>
      <label htmlFor="review-note">Note</label><textarea id="review-note" value={values.note} onChange={e => setValues({ ...values, note: e.target.value })} />
      <div className="actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button><button className="primary" disabled={busy}>Save</button></div>
    </form>
  </section></div>;
}

/** Select an eligible reviewer or clear the current assignment. */
export function ReviewerAssignment({ token, applicationId, current, onCancel, onSaved }: Props & { current?: string | null }) {
  const [reviewers, setReviewers] = useState<{ id: string; name: string }[] | null>(null);
  const [selected, setSelected] = useState(current || '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; reviewsApi.eligible(token, applicationId).then(data => { if (active) setReviewers(data); }).catch(() => { if (active) setError('This page could not be loaded'); }); return () => { active = false; }; }, [token, applicationId]);
  async function save() {
    setBusy(true); setError('');
    try { await reviewsApi.assign(token, applicationId, selected || null); onSaved(); }
    catch { setError('This could not be saved. Try again.'); }
    finally { setBusy(false); }
  }
  return <div className="portfolio-overlay"><section className="portfolio-dialog" role="dialog" aria-modal="true" aria-labelledby="assignment-title">
    <h2 id="assignment-title">Assign reviewer</h2>
    {error && <p role="alert" className="error">{error}</p>}
    <label htmlFor="reviewer">Reviewer</label><select id="reviewer" autoFocus value={selected} onChange={e => setSelected(e.target.value)}><option value="">Not assigned</option>{reviewers?.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
    <div className="actions"><button className="secondary" onClick={onCancel}>Cancel</button><button className="primary" disabled={busy || !reviewers} onClick={() => void save()}>Save</button></div>
  </section></div>;
}
