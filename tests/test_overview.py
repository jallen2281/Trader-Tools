"""Phase 6: whole-picture overview + deterministic observations + deep AI read.

Two users are seeded: one in genuine trouble, one healthy. The healthy user matters as much
as the troubled one — an observations engine that manufactures concerns for someone doing
fine is worse than useless, because it trains the reader to ignore it.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='ovw_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'o.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
TODAY = date.today()
MONTH = TODAY.strftime('%Y-%m')


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    V = A.CONSENT_VERSION
    db.session.add_all([
        A.User(id=1, google_id='g1', email='t@x.com', name='Trouble', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='h@x.com', name='Healthy', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.flush()

    # ---- user 1: thin cash, high-rate debt, over budget, under-withheld, broken sync ----
    db.session.add_all([
        A.FinanceAccount(user_id=1, name='Checking', type='checking', balance=900),
        A.Debt(user_id=1, name='Visa', type='credit_card', apr=24.99, balance=18000,
               min_payment=520),
        A.Debt(user_id=1, name='Auto', type='auto', apr=6.5, balance=14000, min_payment=430,
               secured=True),
        A.IncomeSource(user_id=1, name='Salary', type='salary', annual_salary=78000,
                       pay_frequency='biweekly', tax_form='W2', active=True,
                       next_pay_date=TODAY + timedelta(days=9)),
        A.RecurringBill(user_id=1, name='Rent', category='housing', amount=1750,
                        frequency='monthly', next_due_date=TODAY + timedelta(days=3)),
        A.RecurringBill(user_id=1, name='Electric', category='utilities', amount=180,
                        frequency='monthly', next_due_date=TODAY + timedelta(days=6)),
        A.BudgetCategory(user_id=1, category='food', monthly_limit=400),
        A.PlaidItem(user_id=1, item_id='it-1', access_token_enc=b'x',
                    institution_name='Old Bank', status='login_required'),
    ])
    for i, amt in enumerate((210.0, 180.0, 165.0)):
        db.session.add(A.SpendTransaction(
            user_id=1, posted_at=TODAY.replace(day=min(TODAY.day, 28)),
            description='Grocery run %d' % i, amount=amt, category='food', source='manual'))
    db.session.add(A.SpendTransaction(
        user_id=1, posted_at=TODAY.replace(day=min(TODAY.day, 28)),
        description='Hobby shop', amount=120.0, category='entertainment', source='manual'))
    db.session.add(A.TaxDocument(user_id=1, doc_type='W2', tax_year=TODAY.year,
                                 wages=78000, fed_withheld=1200, filename='w2.pdf'))

    # ---- user 2: healthy ----
    db.session.add_all([
        A.FinanceAccount(user_id=2, name='Savings', type='savings', balance=42000),
        A.FinanceAccount(user_id=2, name='Checking', type='checking', balance=9000),
        A.IncomeSource(user_id=2, name='Salary', type='salary', annual_salary=150000,
                       pay_frequency='biweekly', tax_form='W2', active=True,
                       next_pay_date=TODAY + timedelta(days=4)),
        A.RecurringBill(user_id=2, name='Mortgage', category='housing', amount=1900,
                        frequency='monthly', next_due_date=TODAY + timedelta(days=12)),
        A.BudgetCategory(user_id=2, category='food', monthly_limit=900),
        A.TaxDocument(user_id=2, doc_type='W2', tax_year=TODAY.year,
                      wages=150000, fed_withheld=26000, filename='w2.pdf'),
    ])
    db.session.add(A.SpendTransaction(user_id=2, posted_at=TODAY.replace(day=min(TODAY.day, 28)),
                                      description='Groceries', amount=260.0, category='food',
                                      source='manual'))
    db.session.commit()

trouble, healthy = client_for(1), client_for(2)

print('\n--- the overview endpoint assembles every module ---')
r = trouble.get('/api/finance/overview')
check('GET /api/finance/overview -> 200', r.status_code == 200, r.status_code)
d = r.get_json()
p = d['picture']
for section in ('outlook', 'accounts', 'bills', 'budgets', 'spending', 'cashflow', 'tax',
                'connections', 'liquid_total', 'runway_months', 'monthly_outflow'):
    check('picture includes %s' % section, section in p, list(p))
check('spending is aggregated by category',
      any(c['category'] == 'food' for c in p['spending']['by_category']), p['spending'])
check('food spend totals 555', abs(
    [c for c in p['spending']['by_category'] if c['category'] == 'food'][0]['amount'] - 555.0) < 0.01)
check('bills totalled', abs(p['bills']['total_monthly'] - 1930.0) < 0.01, p['bills'])
check('liquid total picked up', p['liquid_total'] == 900.0, p['liquid_total'])
check('tax estimate present', (p['tax'] or {}).get('total_federal_tax', 0) > 0, p['tax'])

print('\n--- observations fire on the troubled picture ---')
keys = {o['key'].split(':')[0] for o in d['observations']}
titles = {o['key']: o for o in d['observations']}
check('flags the over-budget category', 'budget_over' in keys, sorted(keys))
check('flags the 24.99%% high-rate debt', 'high_apr_debt' in keys, sorted(keys))
check('flags the thin emergency fund', 'thin_runway' in keys, sorted(keys))
check('flags the broken bank connection', 'connection_broken' in keys, sorted(keys))
check('flags under-withholding', 'tax_due' in keys, sorted(keys))
check('flags cash-flow trouble',
      'cashflow_negative' in keys or 'cashflow_thin' in keys, sorted(keys))
check('severities are ranked, critical first',
      [o['severity'] for o in d['observations']] ==
      sorted([o['severity'] for o in d['observations']],
             key=lambda s: {'critical': 0, 'warning': 1, 'note': 2}[s]),
      [o['severity'] for o in d['observations']])
fb = [o for o in d['observations'] if o['key'].startswith('budget_over')][0]
check('over-budget observation states the real overage',
      abs(fb['amount'] - 155.0) < 0.01, fb)
check('counts summarize by severity', d['counts']['warning'] >= 3, d['counts'])
check('flags obligations on the honest ratio, not the debt-only DTI',
      'obligations_high' in keys or 'obligations_critical' in keys, sorted(keys))
check('obligations ratio = (housing 1750 + debt 950) / 6500 gross',
      abs(p['obligations_ratio'] - 41.5) < 0.6, p.get('obligations_ratio'))
check('debt-only DTI would have looked healthy', p['outlook']['dti'] < 20, p['outlook']['dti'])

print('\n--- a healthy picture is not given manufactured problems ---')
r2 = healthy.get('/api/finance/overview')
d2 = r2.get_json()
keys2 = {o['key'].split(':')[0] for o in d2['observations']}
check('no critical findings', d2['counts']['critical'] == 0, d2['observations'])
check('no high-rate debt flag', 'high_apr_debt' not in keys2, sorted(keys2))
check('no over-budget flag', 'budget_over' not in keys2, sorted(keys2))
check('no thin-runway flag', 'thin_runway' not in keys2, sorted(keys2))
check('no tax-due flag (well withheld)', 'tax_due' not in keys2, sorted(keys2))
check('no spend-over-income flag', 'spend_over_income' not in keys2, sorted(keys2))

print('\n--- the facts document the model reads ---')
with app.app_context():
    pic = A._finance_full_picture(1)
    obs = A._finance_observations(pic)
    facts = A._overview_facts(pic, obs)
for header in ('== NET WORTH ==', '== INCOME ==', '== DEBTS', '== RECURRING BILLS ==',
               '== BUDGET vs ACTUAL', '== SPENDING THIS MONTH ==', '== CASH FLOW',
               '== TAX ESTIMATE', '== FLAGGED BY THE SYSTEM'):
    check('facts contain %s' % header.strip('= '), header in facts, facts[:200])
check('facts name the actual high-rate debt', 'Visa' in facts and '24.99' in facts)
check('facts include real bill names', 'Rent' in facts and 'Electric' in facts)
check('facts carry the computed findings for the model to trust',
      'do not re-derive' in facts)
check('no stray "None" leaked into the briefing', 'None' not in facts,
      [l for l in facts.split('\n') if 'None' in l][:3])
check('briefing stays compact (under 4k chars)', len(facts) < 4000, len(facts))

print('\n--- deep AI read: gated, and hands back the findings either way ---')
with app.app_context():
    db.session.add(A.User(id=3, google_id='g3', email='n@x.com', name='NoAI', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()
r = client_for(3).post('/api/finance/ai-overview', json={})
check('403 without ai_analysis', r.status_code == 403, r.status_code)
check('names the missing permission',
      (r.get_json() or {}).get('missing_permission') == 'ai_analysis', r.get_json())

captured = {}


def fake_read(user_id, kind, system, facts, **kw):
    captured['kind'] = kind
    captured['facts'] = facts
    captured['system'] = system
    captured['tier'] = kw.get('tier')
    return {'read': 'Pay the Visa first.', 'engine': 'claude', 'model': 'x', 'cached': False}


A.cached_ai_read = fake_read
r = trouble.post('/api/finance/ai-overview', json={'question': 'Can I afford a $500/mo car?'})
check('ai-overview -> 200', r.status_code == 200, r.status_code)
out = r.get_json()
check('returns the model narrative', out.get('read') == 'Pay the Visa first.', out)
check('returns the deterministic findings alongside it', len(out.get('observations') or []) > 0)
check('cached under its own kind', captured.get('kind') == 'finance_overview', captured.get('kind'))
check('the question reached the model', 'Can I afford a $500/mo car?' in captured['facts'])
check('default tier is the cheap model', captured.get('tier') == 'default', captured.get('tier'))
r = trouble.post('/api/finance/ai-overview', json={'deep': True})
check('deep=true opts into the high tier', captured.get('tier') == 'high', captured.get('tier'))


def empty_read(*a, **kw):
    return {'empty': True}


A.cached_ai_read = empty_read
r = trouble.post('/api/finance/ai-overview', json={})
out = r.get_json()
check('AI unavailable still returns the local findings', len(out.get('observations') or []) > 0, out)
check('and says so honestly', 'computed locally' in (out.get('message') or ''), out)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PHASE 6 OVERVIEW CHECKS PASSED')
