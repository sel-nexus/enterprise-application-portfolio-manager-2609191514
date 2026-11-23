import { useState } from 'react';
import type { Account } from '../accounts/api';
import Users from './Users';
import Roles from './Roles';
import Settings from './Settings';
import Audit from './Audit';

/** Show administration sections appropriate to the signed-in role. */
export default function Administration({ token, account }: { token: string; account: Account }) {
  const [tab, setTab] = useState('Users');
  if (!['administrator', 'auditor'].includes(account.role)) return <section><h1>Not permitted</h1><p>You cannot open administration.</p></section>;
  if (account.role === 'auditor') return <><h1>Audit</h1><Audit token={token} /></>;
  return <section><h1>Administration</h1><p>People, roles, the review interval, and the record of what they did.</p>
    <nav className="account-nav" aria-label="Administration sections">{['Users', 'Roles', 'Settings', 'Audit'].map(name => <button className="text-button" aria-current={tab === name ? 'page' : undefined} key={name} onClick={() => setTab(name)}>{name}</button>)}</nav>
    {tab === 'Users' && <Users token={token} />}{tab === 'Roles' && <Roles token={token} />}{tab === 'Settings' && <Settings token={token} />}{tab === 'Audit' && <Audit token={token} />}
  </section>;
}
