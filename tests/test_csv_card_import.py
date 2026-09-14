"""A CSV export can be attributed to the card it came from.

CSV is the fallback when an issuer cannot be linked at all -- PayPal's Mastercard is the
case: Plaid hits a reCAPTCHA on PayPal, and Synchrony's own portal refuses to service the
co-brand. So the import path has to be as good as the sync path, and that means the rows
landing ON the card rather than with a blank source that reconciles against nothing.

The dedupe key is the delicate part: it must keep its old shape for account imports, or
re-importing an export loaded before this field existed would double every row.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='csvcard_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'c.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import hashlib  # noqa: E402
import json  # noqa: E402

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
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.FinanceAccount(id=10, user_id=1, name='SoFi Checking', type='checking'))
    db.session.add(A.Debt(id=20, user_id=1, name='PayPal Mastercard', type='credit_card',
                          balance=2333.50, apr=18.49, min_payment=27))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

CSV = ('Date,Description,Amount\n'
       '09/02/2026,TRACTOR SUPPLY 1422,84.19\n'
       '09/04/2026,SPEEDWAY 4471,52.10\n'
       '09/05/2026,WEGMANS,131.44\n')


def imp(**mapping):
    m = {'date': 'Date', 'description': 'Description', 'amount': 'Amount',
         'sign': 'debit_positive', 'skip_income': True}
    m.update(mapping)
    return c.post('/api/finance/transactions/import-csv',
                  data={'csv': CSV, 'mapping': json.dumps(m)})


print('\n--- the preview step still works ---')
r = c.post('/api/finance/transactions/import-csv', data={'csv': CSV})
d = r.get_json()
check('previews rather than importing', d.get('preview') is True, d)
check('finds the rows', d['row_count'] == 3, d)

print('\n--- importing onto a credit card ---')
r = imp(paid_from='debt:20')
d = r.get_json()
check('all three land', d['imported'] == 3, d)
with app.app_context():
    rows = A.SpendTransaction.query.all()
    check('every row points at the card', all(t.debt_id == 20 for t in rows),
          [(t.description, t.debt_id) for t in rows])
    check('and none at a bank account', all(t.account_id is None for t in rows))
    check('source is csv', all(t.source == 'csv' for t in rows))

print('\n--- re-importing the same file changes nothing ---')
r = imp(paid_from='debt:20')
check('all skipped as duplicates', r.get_json()['duplicates_skipped'] == 3, r.get_json())
with app.app_context():
    check('still only three rows', A.SpendTransaction.query.count() == 3)

print('\n--- the same rows from a DIFFERENT card are not duplicates ---')
with app.app_context():
    db.session.add(A.Debt(id=21, user_id=1, name='Other card', type='credit_card',
                          balance=100, apr=20, min_payment=25))
    db.session.commit()
r = imp(paid_from='debt:21')
check('they import as their own rows', r.get_json()['imported'] == 3, r.get_json())
with app.app_context():
    check('six in total now', A.SpendTransaction.query.count() == 6)

print('\n--- the old account dedupe key is preserved exactly ---')
# Built the way the pre-change code built it: the bare account id, not 'account:<id>'.
legacy = 'csv:' + hashlib.sha1('{}|{}|{}|{}'.format(
    '2026-09-02', 'tractor supply 1422', 84.19, 10).encode('utf-8')).hexdigest()[:24]
with app.app_context():
    db.session.add(A.SpendTransaction(
        user_id=1, posted_at=A.date(2026, 9, 2), description='TRACTOR SUPPLY 1422',
        category='other', amount=84.19, account_id=10, source='csv', external_id=legacy))
    db.session.commit()
r = imp(paid_from='account:10')
d = r.get_json()
check('the row imported under the old scheme is recognised',
      d['duplicates_skipped'] == 1, d)
check('and the other two still come in', d['imported'] == 2, d)

print('\n--- a card that is not yours is ignored, not honoured ---')
with app.app_context():
    db.session.add(A.User(id=2, google_id='g2', email='o@x.com', name='O', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.Debt(id=99, user_id=2, name='Theirs', type='credit_card',
                          balance=1, apr=1, min_payment=1))
    db.session.commit()
before = None
with app.app_context():
    before = A.SpendTransaction.query.count()
r = imp(paid_from='debt:99')
with app.app_context():
    new = [t for t in A.SpendTransaction.query.all() if t.debt_id == 99]
check('nothing was attributed to it', not new, new)

print('\n--- no source given still works, as it always did ---')
CSV2 = 'Date,Description,Amount\n09/09/2026,ACE HARDWARE,19.99\n'
r = c.post('/api/finance/transactions/import-csv',
           data={'csv': CSV2, 'mapping': json.dumps(
               {'date': 'Date', 'description': 'Description', 'amount': 'Amount',
                'sign': 'debit_positive'})})
check('imports', r.get_json()['imported'] == 1, r.get_json())
with app.app_context():
    t = A.SpendTransaction.query.filter_by(description='ACE HARDWARE').first()
    check('with no source attached', t.debt_id is None and t.account_id is None, t)

print('\n--- a real PayPal Mastercard export, verbatim ---')
# The actual shape the issuer produces: M/D/YY dates, a '$' on every amount, '-$' on the
# payment, purchases positive, and descriptions padded out with runs of spaces.
PAYPAL = '''"date","id","amount","description"
"8/19/26","8521853KR00XSM0ZJ","$66.11","KNGARTFLOUR                              -PAYPAL PURCHASE          SAN JOSE     CA "
"8/18/26","8521853KP00XSMQQX","$774.00","AUDIMALABSP SWAY MID                     -PAYPAL PURCHASE          SAN JOSE     CA "
"8/12/26","8521853KH00XSLSRF","$116.59","GOZNEYGROUP GOZNEYGR                     -PAYPAL PURCHASE          SAN JOSE     CA "
"8/12/26","8521853KH00XSLSR7","$152.59","GOZNEYGROUP GOZNEYGR                     -PAYPAL PURCHASE          SAN JOSE     CA "
"8/9/26","8521853KE00XSLZHN","$350.00","BESTAIRSPOR                              -PAYPAL PURCHASE          SAN JOSE     CA "
"8/6/26","8521853KB00XSM47D","$54.37","EBAY 800-456-3229                        -PAYPAL PURCHASE          SAN JOSE     CA "
"7/30/26","8521853K301P152LN","-$243.15","Payment"
"7/25/26","8521853JZ00XSKN6D","$2.99","DISNEY PLUS                              -PAYPAL PURCHASE          SAN JOSE     CA "
"7/24/26","8521853JZ00XSM30J","$95.00","BESTAIRSPOR                              -PAYPAL PURCHASE          SAN JOSE     CA "
'''
with app.app_context():
    db.session.add(A.Debt(id=30, user_id=1, name='PayPal World Mastercard', type='credit_card',
                          balance=2333.50, apr=18.49, min_payment=27))
    db.session.commit()
r = c.post('/api/finance/transactions/import-csv', data={'csv': PAYPAL})
pv = r.get_json()
check('preview reads all nine rows', pv['row_count'] == 9, pv)
check('and guesses purchases are written positive',
      pv['guessed_sign'] == 'debit_positive', pv['guessed_sign'])
r = c.post('/api/finance/transactions/import-csv', data={'csv': PAYPAL, 'mapping': json.dumps(
    {'date': 'date', 'description': 'description', 'amount': 'amount',
     'sign': pv['guessed_sign'], 'skip_income': True, 'paid_from': 'debt:30'})})
d = r.get_json()
check('eight purchases import', d['imported'] == 8, d)
check('the card payment is left out -- it is money moving onto the card, not a purchase',
      d['income_rows_skipped'] == 1, d)
check('nothing is unreadable', d['unparseable_rows'] == 0, d)
with app.app_context():
    got = A.SpendTransaction.query.filter_by(debt_id=30).all()
    check('every row is on the PayPal card', len(got) == 8, len(got))
    check('two-digit years land in 2026, not the year 26',
          all(t.posted_at.year == 2026 for t in got), sorted({t.posted_at for t in got}))
    check("'$' is stripped and the purchases total correctly",
          round(sum(float(t.amount) for t in got), 2) == 1611.65,
          round(sum(float(t.amount) for t in got), 2))
    check('the same-day Gozney charges stay two rows, not one',
          len([t for t in got if t.posted_at == A.date(2026, 8, 12)]) == 2)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CSV CARD-IMPORT CHECKS PASSED')
