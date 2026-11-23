"""Calculate scoped dashboard metrics and report rows."""
import csv
import io
import math
from datetime import date
from app.accounts.service import AccountService
from app.reporting.repository import ReportingRepository
from app.reporting.schemas import Filters

APPLICATION_COLUMNS = {'name': 'Name', 'portfolio': 'Portfolio', 'product_area': 'Product area', 'criticality': 'Criticality', 'tier': 'Tier', 'lifecycle': 'Lifecycle', 'business_owner': 'Business owner', 'technology_owner': 'Technology owner', 'inventory_owner': 'Inventory owner', 'assigned_reviewer': 'Assigned reviewer', 'health': 'Health', 'quality': 'Quality', 'automation_coverage': 'Automation coverage', 'unit_test_coverage': 'Unit-test coverage', 'open_defects': 'Open defects', 'open_critical_defects': 'Open critical defects', 'risk': 'Risk', 'last_review_date': 'Last review date', 'review_standing': 'Review standing', 'depends_on': 'Depends on'}
PORTFOLIO_COLUMNS = {'name': 'Name', 'owner': 'Owner', 'product_area': 'Product area', 'status': 'Status', 'applications': 'Applications', 'quality': 'Quality', 'health': 'Health', 'open_critical_defects': 'Open critical defects', 'applications_at_risk': 'Applications at risk', 'reviews_due': 'Reviews due'}


def average(rows: list[dict], key: str) -> int | None:
    """Round the mean of available values, or return no value."""
    values = [row[key] for row in rows if row.get(key) is not None]
    return math.floor(sum(values) / len(values) + 0.5) if values else None


class ReportingService:
    """Enforce scope and derive current values from reviews."""
    def __init__(self, repo: ReportingRepository, accounts: AccountService) -> None:
        """Bind database and authorization collaborators."""
        self.repo, self.accounts = repo, accounts

    async def source(self, user: dict, filters: Filters, action: str = 'view') -> tuple[list[dict], list[dict]]:
        """Build report rows after enforcing role and portfolio permissions."""
        await self.accounts.authorize(user, 'view', resource='application')
        if action == 'export':
            await self.accounts.authorize(user, 'export', resource='application')
        if filters.portfolio_id:
            await self.accounts.authorize(user, 'view', filters.portfolio_id, 'application')
        portfolios, apps, counts, interval = await self.repo.estate(self.accounts.portfolio_scope(user))
        by_id = {str(p['_id']): p for p in portfolios}
        rows = []
        for app in apps:
            portfolio = by_id[app['portfolio_id']]
            review = app['latest'][0] if app['latest'] else None
            age = (date.today() - date.fromisoformat(review['date'])).days if review else None
            standing = 'No review' if review is None else ('Overdue' if age > interval else 'Current')
            row = {'id': str(app['_id']), 'portfolio_id': app['portfolio_id'], 'name': app['name'], 'portfolio': portfolio['name'], 'product_area': app.get('product_area', ''), 'criticality': app.get('criticality', ''), 'tier': app.get('tier'), 'lifecycle': app['lifecycle'], 'business_owner': app.get('business_owner', ''), 'technology_owner': app.get('technology_owner', ''), 'inventory_owner': app.get('inventory_owner', ''), 'assigned_reviewer': app.get('assigned_reviewer_name'), 'last_review_date': review['date'] if review else None, 'review_standing': standing, 'depends_on': counts.get(str(app['_id']), 0)}
            for key in ('health', 'quality', 'automation_coverage', 'unit_test_coverage', 'open_defects', 'open_critical_defects', 'risk'):
                row[key] = review.get(key) if review else None
            rows.append(row)
        return portfolios, rows

    def filter_rows(self, portfolios: list[dict], rows: list[dict], filters: Filters, dashboard: bool = False) -> list[dict]:
        """Apply filters consistently before pagination or export."""
        statuses = {str(p['_id']): p['status'] for p in portfolios}
        search = filters.search.strip().casefold()
        return [r for r in rows if (not filters.portfolio_id or r['portfolio_id'] == filters.portfolio_id)
                and (not filters.product_area or r['product_area'] == filters.product_area)
                and (filters.risk == 'All' or (r['risk'] or 'No review') == filters.risk)
                and (not search or search in r['name'].casefold() or search in r['business_owner'].casefold())
                and (filters.criticality == 'All' or r['criticality'] == filters.criticality)
                and ((r['lifecycle'] in ('Active', 'Deprecated')) if dashboard or filters.lifecycle == 'Default' else (filters.lifecycle == 'All' or r['lifecycle'] == filters.lifecycle))
                and (statuses[r['portfolio_id']] == 'Active' if dashboard or not filters.include_archived else True)]

    def portfolio_rows(self, portfolios: list[dict], rows: list[dict]) -> list[dict]:
        """Roll up eligible application reviews for each portfolio."""
        result = []
        for portfolio in portfolios:
            pid = str(portfolio['_id'])
            group = [r for r in rows if r['portfolio_id'] == pid and r['lifecycle'] in ('Active', 'Deprecated')]
            result.append({'id': pid, 'name': portfolio['name'], 'owner': portfolio.get('owner', ''), 'product_area': portfolio.get('product_area', ''), 'status': portfolio['status'], 'applications': len(group), 'quality': average(group, 'quality'), 'health': average(group, 'health'), 'open_critical_defects': sum(r['open_critical_defects'] or 0 for r in group), 'applications_at_risk': sum(r['risk'] == 'High' for r in group), 'reviews_due': sum(r['review_standing'] != 'Current' for r in group)})
        return result

    async def dashboard(self, user: dict, filters: Filters) -> dict:
        """Calculate cards and portfolio chart values for eligible applications."""
        portfolios, rows = await self.source(user, filters)
        eligible = self.filter_rows(portfolios, rows, filters, dashboard=True)
        selected = [p for p in portfolios if p['status'] == 'Active' and (not filters.portfolio_id or str(p['_id']) == filters.portfolio_id) and any(r['portfolio_id'] == str(p['_id']) for r in eligible)]
        groups = self.portfolio_rows(selected, eligible)
        groups.sort(key=lambda p: (p['quality'] is None, p['quality'] if p['quality'] is not None else 0, p['name'].casefold(), p['id']))
        active_ids = {str(p['_id']) for p in portfolios if p['status'] == 'Active'}
        return {'quality': average(eligible, 'quality'), 'health': average(eligible, 'health'), 'automation_coverage': average(eligible, 'automation_coverage'), 'open_critical_defects': sum(r['open_critical_defects'] or 0 for r in eligible), 'applications_at_risk': sum(r['risk'] == 'High' for r in eligible), 'applications': len(eligible), 'portfolios': len(groups), 'groups': groups, 'portfolio_options': [{'id': str(p['_id']), 'name': p['name']} for p in portfolios if p['status'] == 'Active'], 'product_areas': sorted({r['product_area'] for r in rows if r['product_area'] and r['portfolio_id'] in active_ids and r['lifecycle'] in ('Active', 'Deprecated')})}

    async def report(self, user: dict, kind: str, filters: Filters, action: str = 'view') -> list[dict]:
        """Return report rows, including archived and retired records by default."""
        portfolios, rows = await self.source(user, filters, action)
        if kind == 'portfolios':
            return self.portfolio_rows(portfolios, rows)
        return self.filter_rows(portfolios, rows, filters)

    async def export(self, user: dict, kind: str, filters: Filters) -> str:
        """Generate injection-safe CSV and record the export event."""
        rows = await self.report(user, kind, filters, 'export')
        columns = APPLICATION_COLUMNS if kind == 'applications' else PORTFOLIO_COLUMNS
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(columns.values())
        for row in rows:
            values = []
            for key in columns:
                value = row.get(key)
                if isinstance(value, str) and (value.startswith(('\t', '\r', '\n')) or value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))):
                    value = "'" + value
                values.append('' if value is None else value)
            writer.writerow(values)
        await self.accounts.repo.audit(user['name'], 'export', kind, f'Exported {kind} report.')
        return output.getvalue()
