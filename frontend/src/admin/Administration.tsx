import { useState } from 'react';
import type { Account } from '../accounts/api';
import Users from './Users';
import Roles from './Roles';
import Settings from './Settings';
import Audit from './Audit';

/** Show administration sections appropriate to the signed-in role. */
export default function Administration({
  token,
  account,
}: {
  token: string;
  account: Account;
}) {
  const [tab, setTab] = useState('Users');
  const canAdmin =
    account.role === 'administrator' &&
    account.permissions?.administer === true;
  const canAudit =
    ['administrator', 'auditor'].includes(account.role) &&
    account.permissions?.view === true;
  if (!canAdmin && !canAudit)
    return (
      <section>
        <h1>Not permitted</h1>
        <p>You cannot open administration.</p>
      </section>
    );
  if (!canAdmin)
    return (
      <>
        <h1>Audit</h1>
        <Audit token={token} canExport={account.permissions?.export === true} />
      </>
    );
  return (
    <section>
      <h1>Administration</h1>
      <p>
        People, roles, the review interval, and the record of what they did.
      </p>
      <nav className="account-nav" aria-label="Administration sections">
        {['Users', 'Roles', 'Settings', ...(canAudit ? ['Audit'] : [])].map(
          (name) => (
            <button
              className="text-button"
              aria-current={tab === name ? 'page' : undefined}
              key={name}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ),
        )}
      </nav>
      {(tab === 'Users' || (tab === 'Audit' && !canAudit)) && (
        <Users token={token} />
      )}
      {tab === 'Roles' && <Roles token={token} />}
      {tab === 'Settings' && <Settings token={token} />}
      {tab === 'Audit' && canAudit && <Audit token={token} canExport={account.permissions?.export === true} />}
    </section>
  );
}
