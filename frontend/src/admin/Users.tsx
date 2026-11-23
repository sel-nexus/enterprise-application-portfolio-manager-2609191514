import { useEffect, useState } from 'react';
import { adminApi, type Person, type PersonInput } from './api';

const roles = ['administrator', 'portfolio_leader', 'engineer', 'executive', 'auditor', 'read_only'];
const empty: PersonInput = { name: '', email: '', role: 'read_only', portfolio_ids: [], vendor_staff: false, manager: '' };

/** Manage people and their portfolio assignments. */
export default function Users({ token }: { token: string }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [form, setForm] = useState<PersonInput | null>(null);
  const [editing, setEditing] = useState('');
  const [temporary, setTemporary] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function load() {
    try {
      const [users, groups] = await Promise.all([adminApi.users(token, page), adminApi.portfolios(token)]);
      setPeople(users.items); setTotal(users.total); setPortfolios(groups.items); setError('');
    } catch { setError('This page could not be loaded'); }
  }
  useEffect(() => { void load(); }, [token, page]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!form) return;
    try {
      if (editing) await adminApi.update(token, editing, form);
      else await adminApi.create(token, { ...form, temporary_password: temporary });
      setForm(null); setTemporary(''); setNotice('User saved.'); await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'This could not be saved. Try again.'); }
  }
  async function deactivate(person: Person) {
    if (!window.confirm(`${person.name} will no longer be able to sign in. Their name stays on reviews and on the audit list.`)) return;
    try { await adminApi.deactivate(token, person.id); setNotice('User deactivated.'); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'This could not be saved. Try again.'); }
  }
  return (
    <section>
      <div className="portfolio-header"><h2>Users</h2><button className="primary" onClick={() => { setEditing(''); setForm(empty); setError(''); }}>New user</button></div>
      {notice && <p role="status" className="notice">{notice}</p>}
      {error && <p role="alert" className="error">{error} <button className="text-button" onClick={() => void load()}>Try again</button></p>}
      <div className="portfolio-list table-scroll">
        <table><thead><tr>{['Name', 'Email', 'Role', 'Portfolios', 'Status', 'Vendor', 'Last sign-in', 'Actions'].map(x => <th scope="col" key={x}>{x}</th>)}</tr></thead>
          <tbody>{people.map(person => <tr key={person.id}><td>{person.name}</td><td>{person.email}</td><td>{person.role.replaceAll('_', ' ')}</td><td>{['administrator', 'executive', 'auditor'].includes(person.role) ? 'All' : person.portfolio_ids.map(id => portfolios.find(p => p.id === id)?.name || id).join(', ') || 'None'}</td><td>{person.active ? 'Active' : 'Inactive'}</td><td>{person.vendor_staff ? 'Yes' : 'No'}</td><td>{person.last_sign_in ? new Date(person.last_sign_in).toLocaleString() : 'Never'}</td><td><button className="text-button" onClick={() => { setEditing(person.id); setForm({ name: person.name, email: person.email, role: person.role, portfolio_ids: person.portfolio_ids, manager: person.manager || '', vendor_staff: !!person.vendor_staff }); }}>Edit</button>{person.active && <button className="text-button danger" onClick={() => void deactivate(person)}>Deactivate</button>}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} · {total} users</span><button disabled={page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button></div>
      {form && <div className="portfolio-overlay"><section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="user-title"><h2 id="user-title">{editing ? 'Edit user' : 'New user'}</h2><form onSubmit={save}>
        {error && <p role="alert" className="error">{error}</p>}
        <label htmlFor="person-name">Name</label><input id="person-name" autoFocus required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        <label htmlFor="person-email">Email</label><input id="person-email" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
        <label htmlFor="person-role">Role</label><select id="person-role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>{roles.map(r => <option key={r} value={r}>{r.replaceAll('_', ' ')}</option>)}</select>
        {!['administrator', 'executive', 'auditor'].includes(form.role) && <fieldset><legend>Portfolios</legend>{portfolios.map(p => <label className="radio" key={p.id}><input type="checkbox" checked={form.portfolio_ids.includes(p.id)} onChange={e => setForm({ ...form, portfolio_ids: e.target.checked ? [...form.portfolio_ids, p.id] : form.portfolio_ids.filter(id => id !== p.id) })} />{p.name}</label>)}</fieldset>}
        <label htmlFor="person-manager">Manager</label><input id="person-manager" value={form.manager} onChange={e => setForm({ ...form, manager: e.target.value })} />
        <label className="radio"><input type="checkbox" checked={form.vendor_staff} onChange={e => setForm({ ...form, vendor_staff: e.target.checked })} />Vendor staff</label>
        {!editing && <><label htmlFor="person-password">Temporary password</label><input id="person-password" type="password" required minLength={12} maxLength={72} value={temporary} onChange={e => setTemporary(e.target.value)} /><p>Provide this credential securely; the person must change it on first sign-in.</p></>}
        <div className="actions"><button type="button" className="secondary" onClick={() => setForm(null)}>Cancel</button><button className="primary">Save</button></div>
      </form></section></div>}
    </section>
  );
}
