import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ReviewsDue from './ReviewsDue';
import ReviewForm from './ReviewForm';
import { reviewsApi } from './api';

vi.mock('./api', () => ({ reviewsApi: { due: vi.fn(), record: vi.fn(), eligible: vi.fn(), assign: vi.fn() } }));
const account = { id: 'u', name: 'Reader', email: 'reader@example.com', role: 'read_only', portfolio_ids: [], last_sign_in: null, landing_page: 'reviews_due' as const };
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('renders due counts and hides write actions from a read-only user', async () => {
  vi.mocked(reviewsApi.due).mockResolvedValue({ interval: 90, due_count: 1, total: 1, page: 1, page_size: 25, chart: [{ portfolio_id: 'p', portfolio_name: 'Finance', current: 2, due: 1 }], items: [{ application_id: 'a', application_name: 'Payments', portfolio_id: 'p', portfolio_name: 'Finance', last_review: null, days_since_review: null, assigned_reviewer_name: null, risk: null, standing: 'No review' }] });
  render(<MemoryRouter><ReviewsDue token="token" account={account} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/applications/a');
  expect(screen.getByText('Due now: 1')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Record a review' })).not.toBeInTheDocument();
});

it('rejects invalid defects without submitting and retains input', async () => {
  const user = userEvent.setup();
  render(<ReviewForm token="token" applicationId="a" onCancel={() => {}} onSaved={() => {}} />);
  for (const label of ['Health', 'Quality', 'Automation coverage', 'Unit-test coverage']) await user.type(screen.getByLabelText(label), '50');
  await user.type(screen.getByLabelText('Open defects'), '1');
  await user.type(screen.getByLabelText('Open critical defects'), '2');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Critical defects cannot exceed open defects.');
  expect(screen.getByLabelText('Open defects')).toHaveValue(1);
  expect(reviewsApi.record).not.toHaveBeenCalled();
});
