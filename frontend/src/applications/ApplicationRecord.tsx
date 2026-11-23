import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import ApplicationForm from './ApplicationForm';
import ReviewForm, { ReviewerAssignment } from '../reviews/ReviewForm';
import { ApplicationDependencies } from '../dependencies/Dependencies';
import { reviewsApi, type History } from '../reviews/api';
import {
  applicationsApi,
  type Application,
  type ApplicationInput,
  type Lifecycle,
} from './api';

interface Props {
  token: string;
  account: Account;
}

/** Display an application and manage its identity and lifecycle. */
export default function ApplicationRecord({ token, account }: Props) {
  const { applicationId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [item, setItem] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<string>(
    (location.state as { notice?: string } | null)?.notice || '',
  );
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(false);
  const [history, setHistory] = useState<History | null>(null);
  const [latestHistory, setLatestHistory] = useState<History | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [reviewForm, setReviewForm] = useState(false);
  const [assignment, setAssignment] = useState(false);
  const [dialog, setDialog] = useState<'lifecycle' | 'delete' | null>(null);
  const [lifecycle, setLifecycle] = useState<Lifecycle>('Active');
  const [busy, setBusy] = useState(false);
  const inScope =
    account.role === 'administrator' ||
    (!!item && account.portfolio_ids.includes(item.portfolio_id));
  const canEdit =
    inScope &&
    ['administrator', 'portfolio_leader', 'engineer'].includes(account.role) &&
    account.permissions?.edit === true;
  const canReview =
    inScope &&
    ['administrator', 'portfolio_leader', 'engineer'].includes(account.role) &&
    account.permissions?.create === true;
  const canDelete =
    account.role === 'administrator' && account.permissions?.delete === true;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([
      applicationsApi.get(token, applicationId),
      reviewsApi.history(token, applicationId, historyPage),
      reviewsApi.history(token, applicationId),
    ])
      .then(([data, reviews, latestReviews]) => {
        if (active) {
          setItem(data);
          setLifecycle(data.lifecycle);
          setHistory(reviews);
          setLatestHistory(latestReviews);
        }
      })
      .catch(() => {
        if (active) setError('This page could not be loaded');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, applicationId, revision, historyPage]);
  const latest = latestHistory?.items[0];
  const now = new Date();
  const todayUTC = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const overdue =
    latest &&
    latestHistory &&
    (todayUTC - Date.parse(`${latest.date}T00:00:00Z`)) / 86400000 >
      latestHistory.interval;
  async function save(input: ApplicationInput) {
    const saved = await applicationsApi.update(token, applicationId, input);
    setItem(saved);
    setForm(false);
    setNotice('Application saved.');
  }
  async function confirm() {
    setBusy(true);
    setError('');
    try {
      if (dialog === 'delete') {
        await applicationsApi.remove(token, applicationId);
        navigate('/applications');
      } else {
        const saved = await applicationsApi.lifecycle(
          token,
          applicationId,
          lifecycle,
        );
        setItem(saved);
        setNotice('Lifecycle changed.');
        setDialog(null);
      }
    } catch {
      setError('This could not be saved. Try again.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link to="/applications">← Applications</Link>
      {loading && <p role="status">Loading application…</p>}
      {error && (
        <div className="account-card" role="alert">
          <p>{error}</p>
          <button
            className="secondary"
            onClick={() => setRevision((x) => x + 1)}
          >
            Try again
          </button>
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {item && (
        <>
          <header className="application-record-header">
            <h1>{item.name}</h1>
            <Link
              to={`/portfolios?portfolio=${encodeURIComponent(item.portfolio_id)}`}
            >
              {item.portfolio_name}
            </Link>
            <p>
              {item.criticality} · Tier {item.tier} · {item.lifecycle} ·{' '}
              {latest?.risk || 'No review'}
            </p>
            <p>{item.description || 'No description yet.'}</p>
            <div className="portfolio-actions">
              {canReview && (
                <button className="primary" onClick={() => setReviewForm(true)}>
                  Record a review
                </button>
              )}
              {canEdit && (
                <button className="secondary" onClick={() => setForm(true)}>
                  Edit details
                </button>
              )}
              {canEdit && (
                <button
                  className="secondary"
                  onClick={() => setDialog('lifecycle')}
                >
                  Change lifecycle
                </button>
              )}
              {canDelete && (
                <button
                  className="text-button danger"
                  onClick={() => setDialog('delete')}
                >
                  Delete
                </button>
              )}
            </div>
          </header>
          <div className="application-cards">
            <section className="portfolio-detail">
              <h2>Ownership</h2>
              <dl>
                <dt>Business owner</dt>
                <dd>{item.business_owner || 'Not named'}</dd>
                <dt>Technology owner</dt>
                <dd>{item.technology_owner || 'Not named'}</dd>
                <dt>Inventory owner</dt>
                <dd>{item.inventory_owner || 'Not named'}</dd>
                <dt>Assigned reviewer</dt>
                <dd>{history?.assigned_reviewer_name || 'Not assigned'}</dd>
              </dl>
              {canEdit && (
                <button
                  className="text-button"
                  onClick={() => setAssignment(true)}
                >
                  Assign reviewer
                </button>
              )}
            </section>
            <section className="portfolio-detail">
              <h2>Position</h2>
              <dl>
                <dt>Product area</dt>
                <dd>{item.product_area || 'Not named'}</dd>
                <dt>Technology stack</dt>
                <dd>{item.technology_stack || 'Not named'}</dd>
                <dt>Lifecycle</dt>
                <dd>{item.lifecycle}</dd>
                <dt>Criticality</dt>
                <dd>{item.criticality}</dd>
                <dt>Tier</dt>
                <dd>{item.tier}</dd>
              </dl>
            </section>
            <section className="portfolio-detail">
              <h2>Latest review</h2>
              {latest ? (
                <dl>
                  <dt>Date</dt>
                  <dd>
                    {latest.date}
                    {overdue ? ' · Overdue' : ''}
                  </dd>
                  <dt>Health</dt>
                  <dd>{latest.health}</dd>
                  <dt>Quality</dt>
                  <dd>{latest.quality}</dd>
                  <dt>Automation coverage</dt>
                  <dd>{latest.automation_coverage}</dd>
                  <dt>Unit-test coverage</dt>
                  <dd>{latest.unit_test_coverage}</dd>
                  <dt>Open defects</dt>
                  <dd>{latest.open_defects}</dd>
                  <dt>Open critical defects</dt>
                  <dd>{latest.open_critical_defects}</dd>
                  <dt>Risk</dt>
                  <dd>{latest.risk}</dd>
                  <dt>Recorder</dt>
                  <dd>{latest.recorder_name}</dd>
                </dl>
              ) : (
                <p>No review.</p>
              )}
            </section>
          </div>
          <section className="portfolio-detail">
            <h2>Review history</h2>
            {history?.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {[
                        'Date',
                        'Reviewer',
                        'Quality',
                        'Health',
                        'Automation coverage',
                        'Open critical defects',
                        'Risk',
                        'Details',
                      ].map((x) => (
                        <th scope="col" key={x}>
                          {x}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((r) => (
                      <tr key={r.id}>
                        <td>{r.date}</td>
                        <td>{r.recorder_name}</td>
                        <td>{r.quality}</td>
                        <td>{r.health}</td>
                        <td>{r.automation_coverage}</td>
                        <td>{r.open_critical_defects}</td>
                        <td>{r.risk}</td>
                        <td>
                          <details>
                            <summary>More</summary>
                            <p>Unit-test coverage: {r.unit_test_coverage}</p>
                            <p>{r.note || 'No note.'}</p>
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>No reviews recorded.</p>
            )}
            <div className="pagination">
              <button
                className="text-button"
                disabled={historyPage === 1}
                onClick={() => setHistoryPage((x) => x - 1)}
              >
                Previous
              </button>
              <span>Page {historyPage}</span>
              <button
                className="text-button"
                disabled={
                  !history || historyPage * history.page_size >= history.total
                }
                onClick={() => setHistoryPage((x) => x + 1)}
              >
                Next
              </button>
            </div>
          </section>
          {reviewForm && (
            <ReviewForm
              token={token}
              applicationId={applicationId}
              onCancel={() => setReviewForm(false)}
              onSaved={() => {
                setReviewForm(false);
                setHistoryPage(1);
                setNotice('Review recorded');
                setRevision((x) => x + 1);
              }}
            />
          )}
          {assignment && (
            <ReviewerAssignment
              token={token}
              applicationId={applicationId}
              current={history?.assigned_reviewer_id}
              onCancel={() => setAssignment(false)}
              onSaved={() => {
                setAssignment(false);
                setNotice('Reviewer assigned');
                setRevision((x) => x + 1);
              }}
            />
          )}
          <ApplicationDependencies
            token={token}
            account={account}
            applicationId={applicationId}
            canEdit={canEdit}
          />
          {form && (
            <ApplicationForm
              token={token}
              application={item}
              onCancel={() => setForm(false)}
              onSave={save}
            />
          )}
          {dialog && (
            <div className="portfolio-overlay">
              <section
                className="portfolio-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="application-dialog-title"
              >
                <h2 id="application-dialog-title">
                  {dialog === 'delete'
                    ? `Delete ${item.name}?`
                    : 'Change lifecycle'}
                </h2>
                {dialog === 'delete' ? (
                  <p>
                    The application, its reviews, and its dependency links will
                    leave the inventory. Dashboard totals will change with them.
                  </p>
                ) : (
                  <fieldset>
                    <legend>Lifecycle</legend>
                    {(['Active', 'Deprecated', 'Retired'] as Lifecycle[]).map(
                      (value) => (
                        <label className="radio" key={value}>
                          <input
                            type="radio"
                            name="lifecycle"
                            value={value}
                            checked={lifecycle === value}
                            onChange={() => setLifecycle(value)}
                          />
                          <span>
                            {value}
                            <small>
                              {value === 'Active'
                                ? 'Counted on dashboard.'
                                : value === 'Deprecated'
                                  ? 'Still counted and winding down.'
                                  : 'Leaves dashboard but record remains.'}
                            </small>
                          </span>
                        </label>
                      ),
                    )}
                  </fieldset>
                )}
                <div className="actions">
                  <button className="secondary" onClick={() => setDialog(null)}>
                    Cancel
                  </button>
                  <button
                    className={
                      dialog === 'delete' ? 'danger-button' : 'primary'
                    }
                    disabled={busy}
                    onClick={() => void confirm()}
                  >
                    {dialog === 'delete' ? 'Delete' : 'Save'}
                  </button>
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </>
  );
}
