import { expect, test } from './fixtures';

test('the seeded estate populates the first dashboard, inventory, reviews and dependencies', async ({ page, request, admin }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on('pageerror', () => errors.push('Uncaught browser exception'));
  page.on('console', message => { if (message.type() === 'error') errors.push('Browser console error'); });

  // The fixture provisions a fresh administrator in the run-owned database.
  // Set the session without putting credentials into browser action logs.
  const login = await request.post('/api/v1/accounts/login', { data: { email: admin.email, password: admin.password } });
  expect(login.status(), 'isolated administrator login').toBe(200);
  const { access_token } = await login.json();
  await page.addInitScript(token => sessionStorage.setItem('portfolio-session', token), access_token);
  await page.goto('/');

  // Initial landing page must display seeded data, not an empty or hardcoded shell.
  await expect(page).toHaveURL(/\/dashboard$/);
  const applicationsCard = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Applications', exact: true }) });
  await expect(applicationsCard.locator('strong')).toHaveText('33'); // 36 less three retired
  await expect(applicationsCard).toContainText('6 portfolios');
  const qualityChart = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Quality by portfolio' }) });
  await expect(qualityChart.locator('.dependency-bar-row')).toHaveCount(6);
  const strongGroup = qualityChart.locator('.dependency-bar-row').filter({ hasText: 'Customer Experience' });
  const weakGroup = qualityChart.locator('.dependency-bar-row').filter({ hasText: 'Infrastructure' });
  await expect(strongGroup.locator('.dependency-bar')).not.toHaveCSS('width', '0px');
  const strongQuality = Number(await strongGroup.locator('span').innerText());
  const weakQuality = Number(await weakGroup.locator('span').innerText());
  expect(strongQuality).toBeGreaterThan(weakQuality);
  const riskChart = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Applications at risk by portfolio' }) });
  await expect(riskChart.locator('.dependency-bar-row').filter({ hasText: 'Corporate Services' }).locator('span')).not.toHaveText('0');

  await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
  const portfolioList = page.getByRole('region', { name: 'Portfolio list' });
  await expect(portfolioList.getByRole('row')).toHaveCount(7);
  for (const name of ['Customer Experience', 'Commerce Platforms', 'Operations', 'Data and Insights', 'Corporate Services', 'Infrastructure']) {
    await expect(portfolioList.getByRole('button', { name, exact: true })).toBeVisible();
  }
  await expect(portfolioList).toContainText('of 6');

  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await page.getByLabel('Lifecycle').selectOption('All');
  const inventory = page.getByRole('region', { name: 'Application list' });
  await expect(inventory).toContainText('of 36');
  const count = Number((await inventory.locator('.pagination span').innerText()).match(/of (\d+)/)?.[1]);
  expect(count).toBeGreaterThanOrEqual(32);
  expect(count).toBeLessThanOrEqual(40);
  await page.getByLabel('Search name or business owner').fill('Customer Gateway');
  const gateway = inventory.getByRole('row').filter({ hasText: 'Customer Gateway' });
  await expect(gateway).toContainText('Customer Experience');
  await expect(gateway).toContainText('93'); // latest health from seeded review
  await gateway.getByRole('link', { name: 'Customer Gateway' }).click();
  const history = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Review history' }) });
  await expect(history.locator('tbody tr')).toHaveCount(4);
  const latest = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Latest review' }) });
  await expect(latest).toContainText('95');
  await expect(latest).toContainText('Overdue');

  await page.getByRole('link', { name: 'Reviews due', exact: true }).click();
  await expect(page.getByText('Review interval: 90 days')).toBeVisible();
  await expect(page.getByText('Due now: 11')).toBeVisible();
  const reviewChart = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Current and due by portfolio' }) });
  const customerReviewChart = reviewChart.locator('div').filter({ has: page.locator('strong', { hasText: /^Customer Experience$/ }) }).first();
  await expect(customerReviewChart.getByLabel('3 current, 3 due')).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: 'Service Desk' })).toContainText('No review');
  await expect(page.getByRole('row').filter({ hasText: 'Customer Gateway' })).toContainText('Maya Chen');
  await page.getByLabel('Standing').selectOption('Overdue');
  await expect(page.getByRole('row').filter({ hasText: 'Service Desk' })).toHaveCount(0);
  await expect(page.getByRole('row').filter({ hasText: 'Customer Gateway' })).toBeVisible();

  await page.getByRole('link', { name: 'Dependencies', exact: true }).click();
  await expect(page.getByText('Page 1 · 27 results')).toBeVisible();
  const incoming = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Most depended on' }) });
  const cloud = incoming.locator('.dependency-bar-row').filter({ hasText: 'Cloud Control' });
  await expect(cloud.locator('span')).toHaveText('9');
  await expect(cloud.locator('.dependency-bar')).not.toHaveCSS('width', '0px');
  const unlinked = page.locator('section').filter({ has: page.getByRole('heading', { name: 'No recorded dependency' }) });
  await expect(unlinked.locator('strong')).toHaveText('4');
  await page.getByLabel('Search', { exact: true }).fill('Customer Gateway');
  const dependency = page.getByRole('row').filter({ hasText: 'Customer Gateway' });
  await expect(dependency).toContainText('Calls');
  await expect(dependency).toContainText('Cloud Control');
  await expect(dependency).toContainText('Supports the shared operating workflow.');
  await page.getByLabel('Search', { exact: true }).fill('');
  for (const relationship of ['Calls', 'Receives data from', 'Needs at runtime']) {
    await page.getByLabel('Relationship', { exact: true }).selectOption(relationship);
    await expect(page.getByText('Page 1 · 9 results')).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: relationship }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});
