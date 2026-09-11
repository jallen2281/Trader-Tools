"""Exercise the Phase 4 spending ledger end to end against a throwaway SQLite DB.

Runs the real Flask app, but with auth stubbed to a fixed user id so the endpoints can be
hit directly. Nothing here touches the user's real database.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='p4test_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p4.db').replace('\\', '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ.setdefault('FLASK_ENV', 'testing')

sys.path.insert(0, os.getcwd())
import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['WTF_CSRF_ENABLED'] = False

db = A.db
UID = 1

# Stub auth: pin every request to user 1.
A._get_current_user_id = lambda *a, **k: UID

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='p4-test', email='p4@example.com', name='P4 Test',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.BudgetCategory(user_id=UID, category='food', monthly_limit=600, kind='expense'))
    db.session.add(A.BudgetCategory(user_id=UID, category='housing', monthly_limit=2000, kind='expense'))
    db.session.add(A.RecurringBill(user_id=UID, name='Rent', category='housing', amount=1800,
                                   frequency='monthly', due_day=1, active=True))
    db.session.commit()

c = app.test_client()
# Real session login — Phase 2 is live now, so require_api_auth actually enforces.
with c.session_transaction() as sess:
    sess['_user_id'] = str(UID)
    sess['_fresh'] = True

print('\n--- pure helpers ---')
check('amount "$1,234.56" -> 1234.56', A._parse_csv_amount('$1,234.56') == 1234.56)
check('amount "(45.00)" -> -45.0 (accounting negative)', A._parse_csv_amount('(45.00)') == -45.0)
check('amount "" -> None', A._parse_csv_amount('') is None)
check('amount "n/a" -> None', A._parse_csv_amount('n/a') is None)
check('date 09/03/2026 parses', str(A._parse_csv_date('09/03/2026')) == '2026-09-03')
check('date 2026-09-03 parses', str(A._parse_csv_date('2026-09-03')) == '2026-09-03')
check('date garbage -> None', A._parse_csv_date('not a date') is None)
check('category guess: WEGMANS -> food', A._guess_spend_category('WEGMANS #123') == 'food')
check('category guess: SHELL OIL -> transportation', A._guess_spend_category('SHELL OIL 4432') == 'transportation')
check('category guess: unknown -> other', A._guess_spend_category('ZZQQ LLC') == 'other')
s, e = A._month_bounds('2026-02')
check('month bounds 2026-02 -> Feb 1..28', str(s) == '2026-02-01' and str(e) == '2026-02-28', (s, e))
s, e = A._month_bounds('2026-12')
check('month bounds 2026-12 wraps year', str(s) == '2026-12-01' and str(e) == '2026-12-31', (s, e))

print('\n--- manual transaction CRUD ---')
r = c.post('/api/finance/transactions', json={'posted_at': '2026-09-02', 'description': 'Wegmans run',
                                              'amount': 82.14})
check('POST manual txn -> 201', r.status_code == 201, r.data[:200])
tid = r.get_json().get('id')
check('auto-categorized to food', r.get_json().get('category') == 'food', r.get_json())

r = c.post('/api/finance/transactions', json={'description': 'no amount but valid'})
check('POST without description -> 400', c.post('/api/finance/transactions', json={}).status_code == 400)

r = c.put('/api/finance/transactions/%d' % tid, json={'amount': 90.00, 'category': 'entertainment'})
check('PUT updates amount+category', r.get_json()['amount'] == 90.0 and r.get_json()['category'] == 'entertainment')

r = c.get('/api/finance/transactions?month=2026-09')
d = r.get_json()
check('GET month lists txns', d['count'] >= 1, d)
check('GET reports by_category', isinstance(d['by_category'], list) and len(d['by_category']) >= 1)

r = c.get('/api/finance/transactions?month=2026-01')
check('GET other month is empty', r.get_json()['count'] == 0)

print('\n--- CSV import ---')
CSV = (
    'Post Date,Description,Amount,Category\n'
    '09/01/2026,WEGMANS #442,-120.55,Groceries\n'
    '09/02/2026,SHELL OIL 7781,-48.20,Gas\n'
    '09/03/2026,NETFLIX.COM,-15.99,\n'
    '09/03/2026,PAYROLL DEPOSIT,2400.00,\n'
    '09/04/2026,"MCDONALD\'S #91",-9.87,\n'
    'bad-date,BROKEN ROW,-1.00,\n'
)
import io as _io

r = c.post('/api/finance/transactions/import-csv',
           data={'file': (_io.BytesIO(CSV.encode('utf-8')), 'export.csv')},
           content_type='multipart/form-data')
prev = r.get_json()
check('CSV preview -> 200', r.status_code == 200, prev)
check('preview detects headers', prev.get('headers') == ['Post Date', 'Description', 'Amount', 'Category'], prev.get('headers'))
check('preview guesses date column', prev['guessed_mapping']['date'] == 'Post Date', prev['guessed_mapping'])
check('preview guesses description column', prev['guessed_mapping']['description'] == 'Description')
check('preview infers debit_negative from data', prev['guessed_sign'] == 'debit_negative', prev['guessed_sign'])
check('preview counts rows', prev['row_count'] == 6, prev['row_count'])

import json as _json

mapping = {'date': 'Post Date', 'description': 'Description', 'amount': 'Amount',
           'sign': 'debit_negative', 'skip_income': True}
r = c.post('/api/finance/transactions/import-csv',
           data={'file': (_io.BytesIO(CSV.encode('utf-8')), 'export.csv'),
                 'mapping': _json.dumps(mapping)},
           content_type='multipart/form-data')
res = r.get_json()
check('CSV import -> 200', r.status_code == 200, res)
check('imported the 4 real purchases', res['imported'] == 4, res)
check('skipped the payroll deposit', res['income_rows_skipped'] == 1, res)
check('flagged the bad-date row', res['unparseable_rows'] == 1, res)

# Re-import the same file: everything should dedupe.
r = c.post('/api/finance/transactions/import-csv',
           data={'file': (_io.BytesIO(CSV.encode('utf-8')), 'export.csv'),
                 'mapping': _json.dumps(mapping)},
           content_type='multipart/form-data')
res2 = r.get_json()
check('re-import imports nothing', res2['imported'] == 0, res2)
check('re-import counts 4 duplicates', res2['duplicates_skipped'] == 4, res2)

r = c.get('/api/finance/transactions?month=2026-09')
d = r.get_json()
descs = [t['description'] for t in d['transactions']]
check("apostrophe merchant survived", any("MCDONALD" in x for x in descs), descs)
check('netflix auto-categorized to subscriptions',
      any(t['category'] == 'subscriptions' for t in d['transactions']), d['transactions'])

print('\n--- receipt import ---')
with app.app_context():
    db.session.add(A.TaxDocument(user_id=UID, doc_type='receipt', merchant='HOME DEPOT',
                                 amount=212.40, category='housing', filename='hd.pdf',
                                 uploaded_at=A.datetime(2026, 9, 2, 12, 0)))
    db.session.add(A.TaxDocument(user_id=UID, doc_type='receipt', merchant='UNREAD RECEIPT',
                                 amount=0, filename='blurry.jpg',
                                 uploaded_at=A.datetime(2026, 9, 2, 12, 0)))
    db.session.commit()

r = c.post('/api/finance/transactions/import-receipts')
res = r.get_json()
check('receipt import -> 200', r.status_code == 200, res)
check('imported the priced receipt', res['imported'] == 1, res)
check('left the amount-less receipt alone', res['receipts_without_amount'] == 1, res)
r = c.post('/api/finance/transactions/import-receipts')
check('re-running imports nothing new', r.get_json()['imported'] == 0, r.get_json())

print('\n--- budget rollup: actual vs committed ---')
r = c.get('/api/finance/budgets?month=2026-09')
d = r.get_json()
rows = {b['category']: b for b in d['budgets']}
check('rollup reports month', d.get('month') == '2026-09', d.get('month'))
check('food has actual spend', rows['food']['actual_monthly'] > 0, rows.get('food'))
check('food has no bills committed', rows['food']['committed_monthly'] == 0, rows.get('food'))
check('food projected == actual', rows['food']['projected_monthly'] == rows['food']['actual_monthly'])
h = rows['housing']
check('housing committed = 1800 rent', h['committed_monthly'] == 1800.0, h)
check('housing actual = 212.40 receipt', h['actual_monthly'] == 212.40, h)
check('housing projected is max(), not sum (no double-count)', h['projected_monthly'] == 1800.0, h)
check('housing remaining = 2000 - 1800', h['remaining'] == 200.0, h)
check('housing not flagged over', h['over'] is False, h)

# Push food over its 600 limit and confirm the flag flips.
c.post('/api/finance/transactions', json={'posted_at': '2026-09-05', 'description': 'Costco haul',
                                          'amount': 700, 'category': 'food'})
rows = {b['category']: b for b in c.get('/api/finance/budgets?month=2026-09').get_json()['budgets']}
check('food now flagged over limit', rows['food']['over'] is True, rows['food'])
check('food remaining went negative', rows['food']['remaining'] < 0, rows['food'])

print('\n--- refunds net out ---')
before = {b['category']: b for b in
          c.get('/api/finance/budgets?month=2026-09').get_json()['budgets']}['food']['actual_monthly']
c.post('/api/finance/transactions', json={'posted_at': '2026-09-06', 'description': 'Costco return',
                                          'amount': -100, 'category': 'food'})
after = {b['category']: b for b in
         c.get('/api/finance/budgets?month=2026-09').get_json()['budgets']}['food']['actual_monthly']
check('a -100 refund lowers food actual by exactly 100',
      abs((before - after) - 100.0) < 0.001, 'before=%s after=%s' % (before, after))
r = c.get('/api/finance/transactions?month=2026-09&category=food')
check('refund row is listed as negative',
      any(t['amount'] == -100.0 for t in r.get_json()['transactions']), r.get_json()['transactions'])
check('category filter returns only food',
      all(t['category'] == 'food' for t in r.get_json()['transactions']))
r = c.get('/api/finance/transactions?month=2026-09&q=netflix')
check('search filter matches description', r.get_json()['count'] == 1, r.get_json())
r = c.get('/api/finance/transactions?month=2026-09&source=receipt')
check('source filter isolates receipt imports', r.get_json()['count'] == 1, r.get_json())

print('\n--- delete ---')
r = c.delete('/api/finance/transactions/%d' % tid)
check('DELETE -> 200', r.status_code == 200)
check('DELETE of missing id -> 404', c.delete('/api/finance/transactions/999999').status_code == 404)

print('\n--- bills can be semiannual, for property tax and auto insurance ---')
r = c.post('/api/finance/bills', json={'name': 'Property tax', 'category': 'taxes',
                                       'amount': 2400, 'frequency': 'semiannual',
                                       'next_due_date': '2026-07-15'})
check('semiannual is accepted',
      r.status_code == 201 and r.get_json()['frequency'] == 'semiannual', r.get_json())
check('$2,400 twice a year is $400/mo in the budget floor',
      r.get_json()['monthly_amount'] == 400.0, r.get_json()['monthly_amount'])
due = r.get_json()['upcoming_due_dates']
check('due dates step six months, keeping the calendar month',
      due[0] == '2026-07-15' and due[1] == '2027-01-15' and due[2] == '2027-07-15', due)
# The two lists drifting apart is how a frequency gets accepted and then priced as monthly.
check('every frequency the model can price is also accepted by the API',
      set(A.BILL_FREQUENCIES) == set(A.RecurringBill.FREQ_PER_YEAR),
      (sorted(A.BILL_FREQUENCIES), sorted(A.RecurringBill.FREQ_PER_YEAR)))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PHASE 4 CHECKS PASSED')
