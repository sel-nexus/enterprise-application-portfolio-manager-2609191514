import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Account } from '../accounts/api';
import {
  applicationColumns,
  portfolioColumns,
  reportingApi,
  type ReportPage,
} from './api';

/** Open, paginate and export the scoped reports. */
export default function Reports({
  token,
  account,
}: {
  token: string;
  account: Account;
}) {
  const [params, setParams] = useSearchParams();
  const kind =
    params.get('report') === 'applications'
      ? 'applications'
      : params.get('report') === 'portfolios'
        ? 'portfolios'
        : null;
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [data, setData] = useState<ReportPage | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!kind) return;
    let active = true;
    setLoading(true);
    setError('');
    const query = new URLSearchParams({
      page: String(page),
      lifecycle: 'All',
      include_archived: 'true',
    });
    reportingApi
      .report(token, kind, query)
      .then((value) => {
        if (active) setData(value);
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
  }, [kind, page, token, revision]);
  async function download() {
    if (!kind) return;
    try {
      await reportingApi.export(
        token,
        kind,
        new URLSearchParams({ lifecycle: 'All', include_archived: 'true' }),
      );
    } catch {
      setError('Export failed. Try again.');
    }
  }
  return (
    <>
      <header>
        <h1>Reports</h1>
        <p>The same inventory, laid out for reading and export.</p>
      </header>
      {!kind ? (
        <div className="dashboard-charts">
          <section className="portfolio-list">
            <h2>Application report</h2>
            <p>
              One row for every application you can see, with the latest review.
            </p>
            <button
              className="primary"
              onClick={() => setParams({ report: 'applications' })}
            >
              Open report
            </button>
          </section>
          <section className="portfolio-list">
            <h2>Portfolio report</h2>
            <p>
              One row for every portfolio you can see, with quality rolled up
              from the latest reviews.
            </p>
            <button
              className="secondary"
              onClick={() => setParams({ report: 'portfolios' })}
            >
              Open report
            </button>
          </section>
        </div>
      ) : (
        <>
          <button className="text-button" onClick={() => setParams({})}>
            All reports
          </button>
          <h2>
            {kind === 'applications'
              ? 'Application report'
              : 'Portfolio report'}
          </h2>
          {loading && <p role="status">Loading report…</p>}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button
                className="secondary"
                onClick={() => setRevision((x) => x + 1)}
              >
                Try again
              </button>
            </div>
          )}
          {!loading && !error && data && (
            <section className="portfolio-list">
              {data.total === 0 ? (
                <p>Nothing to report for the portfolios you can see.</p>
              ) : (
                <>
                  {[
                    'administrator',
                    'portfolio_leader',
                    'engineer',
                    'executive',
                    'auditor',
                  ].includes(account.role) &&
                    account.permissions?.export === true && (
                      <button
                        className="primary"
                        onClick={() => void download()}
                      >
                        Export CSV
                      </button>
                    )}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {(kind === 'applications'
                            ? applicationColumns
                            : portfolioColumns
                          ).map(([key, title]) => (
                            <th scope="col" key={key}>
                              {title}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.items.map((row) => (
                          <tr key={String(row.id)}>
                            {(kind === 'applications'
                              ? applicationColumns
                              : portfolioColumns
                            ).map(([key]) => (
                              <td key={key}>
                                {key === 'name' ? (
                                  <Link
                                    to={
                                      kind === 'applications'
                                        ? `/applications/${row.id}`
                                        : `/portfolios?portfolio=${row.id}`
                                    }
                                  >
                                    {row[key]}
                                  </Link>
                                ) : (
                                  (row[key] ?? '—')
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="pagination">
                    <button
                      disabled={page === 1}
                      onClick={() =>
                        setParams({ report: kind, page: String(page - 1) })
                      }
                    >
                      Previous
                    </button>
                    <span>
                      Page {page} · {data.total} total
                    </span>
                    <button
                      disabled={page * data.page_size >= data.total}
                      onClick={() =>
                        setParams({ report: kind, page: String(page + 1) })
                      }
                    >
                      Next
                    </button>
                  </div>
                </>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}
