"""One view of every dollar in and out.

Spending and deposits are stored apart on purpose -- a paycheck must never be summed into
spending -- and nothing ever showed them together. Paychecks were invisible, the cash-flow
card was a projection, and the spending card was only the outgoing half, so a month could
not be checked against a bank statement. The ledger lists both, signed the way a bank does
(money in positive), and totals each direction separately.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='ledger_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'l.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


with app.app_context():
    db.drop_all()
    db.create_all()
    for uid in (1, 2):
        db.session.add(A.User(id=uid, google_id='g%d' % uid, email='u%d@x.com' % uid, name='U%d' % uid,
                              role='admin', privacy_consent_at=A.datetime.utcnow(),
                              privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.PlaidAccount(user_id=1, item_id=1, account_id='chk', name='Total Checking',
                                  mask='1349', type='depository', subtype='checking'))
    db.session.add(A.PlaidAccount(user_id=1, item_id=1, account_id='amex', name='Amex EveryDay',
                                  mask='2001', type='credit', subtype='credit card'))
    farm = A.Entity(user_id=1, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    home = A.Entity(user_id=1, name='Personal finance', kind='personal')
    db.session.add_all([farm, home])
    db.session.flush()
    FARM, HOME = farm.id, home.id
    job = A.IncomeSource(user_id=1, name='Liquid Web', type='salary', annual_salary=94605,
                         pay_frequency='biweekly', tax_form='W2', owner='me', active=True,
                         entity_id=HOME)
    db.session.add(job)
    db.session.flush()
    S = A.SpendTransaction
    db.session.add_all([
        S(user_id=1, posted_at=date(2026, 9, 11), description='Tractor Supply', category='farm_feed',
          amount=897.13, plaid_account_id='amex', entity_id=FARM, source='plaid'),
        S(user_id=1, posted_at=date(2026, 9, 14), description='Walmart', category='personal',
          amount=158.61, plaid_account_id='amex', entity_id=HOME, source='plaid'),
        S(user_id=1, posted_at=date(2026, 9, 15), description='Walmart return', category='personal',
          amount=-25.00, plaid_account_id='amex', entity_id=HOME, source='plaid'),
        S(user_id=1, posted_at=date(2026, 9, 10), description='AMEX EPAYMENT', category='transfer',
          amount=1062.62, plaid_account_id='chk', entity_id=HOME, source='plaid'),
        S(user_id=1, posted_at=date(2026, 9, 12), description='Hand-entered cash', category='food',
          amount=40.00, source='manual'),
        S(user_id=1, posted_at=date(2026, 8, 30), description='Last month', category='food',
          amount=500.00, plaid_account_id='chk', source='plaid'),
        S(user_id=2, posted_at=date(2026, 9, 12), description='SOMEONE ELSE', category='food',
          amount=999.00, source='manual'),
    ])
    D = A.PlaidDeposit
    db.session.add_all([
        D(user_id=1, external_id='plaid:p1', plaid_account_id='chk', posted_at=date(2026, 9, 10),
          description='LIQUID WEB PAYROLL', amount=2906.00, kind='income', income_source_id=job.id),
        D(user_id=1, external_id='plaid:p2', plaid_account_id='amex', posted_at=date(2026, 9, 10),
          description='PAYMENT RECEIVED', amount=1062.62, kind='card_payment'),
        D(user_id=1, external_id='plaid:p3', plaid_account_id='chk', posted_at=date(2026, 9, 5),
          description='Egg sales', amount=60.00, kind='unknown'),
        D(user_id=2, external_id='plaid:x', plaid_account_id='zzz', posted_at=date(2026, 9, 5),
          description='NOT YOURS', amount=5000.00, kind='income'),
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True


def ledger(**q):
    q.setdefault('month', '2026-09')
    return c.get('/api/finance/ledger', query_string=q).get_json()


d = ledger()
rows = d['rows']
by = {r['description']: r for r in rows}

print('\n--- everything for the month, in one list ---')
check('paychecks are visible', 'LIQUID WEB PAYROLL' in by, list(by))
check('spending is there too', 'Tractor Supply' in by and 'Walmart' in by)
check('hand-entered rows included', 'Hand-entered cash' in by)
check("another user's money is not", 'SOMEONE ELSE' not in by and 'NOT YOURS' not in by)
check('only this month', 'Last month' not in by)
check('eight rows', d['count'] == 8, d['count'])
check('newest first', rows[0]['posted_at'] >= rows[-1]['posted_at'])

print('\n--- signed like a bank statement ---')
check('a paycheck is positive', by['LIQUID WEB PAYROLL']['amount'] == 2906.00)
check('a purchase is negative', by['Walmart']['amount'] == -158.61)
check('a refund is money in', by['Walmart return']['amount'] == 25.00
      and by['Walmart return']['direction'] == 'in')
check('a card payment out of checking is a transfer',
      by['AMEX EPAYMENT']['direction'] == 'transfer' and by['AMEX EPAYMENT']['amount'] == -1062.62)
check('and its landing on the card is a transfer in',
      by['PAYMENT RECEIVED']['direction'] == 'transfer' and by['PAYMENT RECEIVED']['amount'] == 1062.62)
check('an unclassified deposit still counts as money in', by['Egg sales']['direction'] == 'in')

print('\n--- totals keep the directions apart ---')
t = d['totals']
check('money in = paycheck + egg sales + refund', t['money_in'] == round(2906 + 60 + 25, 2), t)
check('money out = purchases only', t['money_out'] == round(897.13 + 158.61 + 40, 2), t)
check('net is in minus out', t['net'] == round(t['money_in'] - t['money_out'], 2), t)
check('transfers are reported, never netted into spending',
      t['transfers_out'] == 1062.62 and t['transfers_in'] == 1062.62, t)

print('\n--- accounts and books ---')
check('a Plaid row names its account', by['Walmart']['account_name'] == 'Amex EveryDay ...2001',
      by['Walmart']['account_name'])
check('a hand-entered row without one says so', by['Hand-entered cash']['account_name'] == 'No account')
check('spending carries its book', by['Tractor Supply']['book'] == 'Chicken Tales LLC')
check('a paycheck takes the book of the job it came from', by['LIQUID WEB PAYROLL']['book'] == 'Personal finance')
check('and is labelled with that job', by['LIQUID WEB PAYROLL']['category_label'] == 'Liquid Web')
check('per-account in/out', any(a['account'].startswith('Total Checking') and a['in'] == 2966.0
                                for a in d['by_account']), d['by_account'])
check('the account list offers every connected account',
      {a['key'] for a in d['accounts']} >= {'chk', 'amex'}, d['accounts'])

print('\n--- filters ---')
check('money in only', {r['direction'] for r in ledger(direction='in')['rows']} == {'in'})
check('money out only', {r['description'] for r in ledger(direction='out')['rows']}
      == {'Tractor Supply', 'Walmart', 'Hand-entered cash'})
check('transfers only', ledger(direction='transfer')['count'] == 2)
check('one account', {r['account_key'] for r in ledger(account='chk')['rows']} == {'chk'})
check('one book', {r['description'] for r in ledger(book=str(FARM))['rows']} == {'Tractor Supply'})
check('rows with no book', 'Hand-entered cash' in {r['description'] for r in ledger(book='none')['rows']})
check('search', [r['description'] for r in ledger(q='tractor')['rows']] == ['Tractor Supply'])
check('totals follow the filters', ledger(account='amex')['totals']['money_out'] == round(897.13 + 158.61, 2))
check('a spend row carries what the edit form needs', by['Walmart']['txn']['id'] == by['Walmart']['id'])

print('\n--- the page ---')
body = c.get('/finances').get_data(as_text=True)
check('Transactions card present and wired', 'id="ledgerBody"' in body and 'loadLedger()' in body
      and 'ledDir' in body and 'ledAcct' in body)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL LEDGER CHECKS PASSED')
