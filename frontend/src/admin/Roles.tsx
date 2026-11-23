import { useEffect, useState } from 'react';
import { adminApi, type Permissions, type Role } from './api';

const actions: (keyof Permissions)[] = ['view', 'create', 'edit', 'delete', 'export', 'administer'];
const ceiling: Record<string, (keyof Permissions)[]> = { administrator: actions, portfolio_leader: ['view', 'create', 'edit', 'export'], engineer: ['view', 'create', 'edit', 'export'], executive: ['view', 'export'], auditor: ['view', 'export'], read_only: ['view'] };

/** Edit stored restrictions on shipped role capabilities. */
export default function Roles({ token }: { token: string }) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [editing, setEditing] = useState<Role | null>(null);
  const [error, setError] = useState('');
  async function load() { try { setRoles(await adminApi.roles(token)); setError(''); } catch { setError('This page could not be loaded'); } }
  useEffect(() => { void load(); }, [token]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!editing) return;
    try { await adminApi.saveRole(token, editing); setEditing(null); await load(); } catch (e) { setError(e instanceof Error ? e.message : 'This could not be saved. Try again.'); }
  }
  return <section><h2>Roles</h2>{error && <p className="error" role="alert">{error} <button onClick={() => void load()}>Try again</button></p>}
    <div className="portfolio-list table-scroll"><table><thead><tr><th scope="col">Role</th><th scope="col">Description</th><th scope="col">Actions</th></tr></thead><tbody>{roles.map(role => <tr key={role.name}><td>{role.name.replaceAll('_', ' ')}</td><td>{role.description}</td><td><button className="text-button" onClick={() => setEditing(role)}>Edit permissions</button></td></tr>)}</tbody></table></div>
    {editing && <div className="portfolio-overlay"><section className="portfolio-panel" role="dialog" aria-modal="true" aria-labelledby="role-title"><h2 id="role-title">Edit permissions</h2><p>View opens records, including reviews due and dependencies. Create and Edit change portfolios, applications, reviews, reviewer assignments, and dependencies. Delete removes them. Export downloads reports. Administer opens this page and sets the review interval.</p><form onSubmit={save}>
      <label htmlFor="role-description">Description</label><textarea id="role-description" autoFocus value={editing.description} onChange={e => setEditing({ ...editing, description: e.target.value })} />
      {actions.map(action => <label className="radio" key={action}><input type="checkbox" disabled={!ceiling[editing.name].includes(action)} checked={editing.permissions[action]} onChange={e => setEditing({ ...editing, permissions: { ...editing.permissions, [action]: e.target.checked } })} />{action}</label>)}
      <div className="actions"><button type="button" className="secondary" onClick={() => setEditing(null)}>Cancel</button><button className="primary">Save</button></div>
    </form></section></div>}
  </section>;
}
