"""A hand-entered balance already contains the payments made before it was read.

Nothing recorded WHEN a debt's balance was true, so `_apply_debt_payments` applied every
unapplied payment in the ledger to whatever figure it found -- including payments that had
posted months before the record existed, and which the typed-in figure therefore already
reflected. The paydown was counted twice.

Found the live way round, and the arithmetic below is this install's, not an invention.
Three debts were created on 2026-08-21 at round opening figures; a backfill on 13 October
applied the June, July and August payments as well as September's and October's:

    1st Mortgage      $342,000.00 entered, 1 payment pre-dating it, $1,341.19 removed
    Home Improvement   $56,000.00 entered, 3 payments pre-dating it,   $601.57 removed
    Car Loan           $26,000.00 entered, 3 payments pre-dating it, $1,452.54 removed

$3,395.30 of principal retired a second time, every dollar of it in the direction that
flatters net worth. The truck loan is the one that got noticed: the app read $23,595.26
against a real $25,767.33.

Note what this fix does NOT claim. Guarding the date brings the truck to $25,047.80, which
is still $719.53 under the lender's figure -- the entered $26,000.00 was itself a round
number, and the residual belongs to that, not to the payment pass. A test that asserted
reality here would be asserting a coincidence.

The boundary is deliberately inclusive. A payment posted ON the as-of date is treated as
already counted, because there is no way to know which side of it a statement was read
from, and the error that leaves a debt looking too big is the safe one.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='debtasof_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'a.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['TT_BACKGROUND_JOBS'] = '0'
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


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


UID = 1
TODAY = date.today()
# The real dates, so the figures below are the production figures.
CREATED = date(2026, 8, 21)
PAYMENTS = [date(2026, 6, 14), date(2026, 7, 14), date(2026, 8, 16),
            date(2026, 9, 15), date(2026, 10, 15)]

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    def truck(balance=26000.00, as_of=None, created=CREATED):
        """The loan as it stood: $26,000 at 8.1%, $650 a month to Community Choice."""
        d = A.Debt(user_id=UID, name='Car Loan', type='auto', lender='Community Credit Union',
                   balance=balance, apr=8.100, min_payment=650.00, secured=True,
                   balance_as_of=as_of)
        d.created_at = A.datetime(created.year, created.month, created.day, 18, 42, 55)
        db.session.add(d)
        db.session.commit()
        db.session.add(A.RecurringBill(
            user_id=UID, name="Tricia's Truck", payee='Community Credit Union',
            category='debt', amount=650.00, frequency='monthly',
            linked_debt_id=d.id, active=True))
        db.session.commit()
        return d

    def pay(dates, amount=650.00):
        out = []
        for i, when in enumerate(dates):
            t = A.SpendTransaction(
                user_id=UID, posted_at=when, description='COMMUNITY CHOICE',
                merchant='Community Choice', category='debt', amount=amount,
                source='plaid', external_id='plaid:cc%s%s' % (when.isoformat(), i))
            db.session.add(t)
            out.append(t)
        db.session.commit()
        return out

    def wipe():
        for m in (A.SpendTransaction, A.RecurringBill, A.Debt):
            for r in m.query.filter_by(user_id=UID).all():
                db.session.delete(r)
        db.session.commit()

    print('\n--- the floor: which date says what the balance already contains ---')
    d = truck(as_of=date(2026, 9, 30))
    check('a stated as-of date is the floor',
          A._payment_floor(d) == date(2026, 9, 30), A._payment_floor(d))
    d.balance_as_of = None
    db.session.commit()
    check('without one, the record cannot describe a figure older than itself',
          A._payment_floor(d) == CREATED, A._payment_floor(d))
    d.created_at = None
    db.session.commit()
    check('with neither, nothing is excluded -- the old behaviour, not a silent skip',
          A._payment_floor(d) == date.min, A._payment_floor(d))
    wipe()

    print('\n--- THE REGRESSION: five payments, three of them already in the figure ---')
    d = truck()                      # created 2026-08-21, no as-of -> created_at is the floor
    rows = pay(PAYMENTS)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    # 26,000.00 -> Sep: 175.50 interest, 474.50 principal -> 25,525.50
    #           -> Oct: 172.30 interest, 477.70 principal -> 25,047.80
    check('only the two payments after the record applied',
          abs(float(d.balance) - 25047.80) < 0.005, d.balance)
    check('which is exactly the $1,452.54 production had wrongly removed',
          abs((float(d.balance) - 23595.26) - 1452.54) < 0.005,
          (d.balance, float(d.balance) - 23595.26))
    applied = [t for t in A.SpendTransaction.query.filter_by(user_id=UID).all()
               if t.debt_applied_at is not None]
    check('and only those two rows are marked applied', len(applied) == 2,
          [(t.posted_at, t.debt_applied_at) for t in applied])
    check('the pre-dating rows are left as evidence, not marked spent',
          all(t.debt_applied_at is None for t in rows[:3]),
          [t.debt_applied_at for t in rows[:3]])

    print('\n--- the as-of date moves with the balance it describes ---')
    check('it now reports the last payment it took in',
          d.balance_as_of == date(2026, 10, 15), d.balance_as_of)
    before = float(d.balance)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    check('so a second pass cannot walk it down again', float(d.balance) == before,
          (before, d.balance))

    print('\n--- a payment on the as-of date itself is already counted ---')
    pay([date(2026, 10, 15)], amount=650.00)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    check('same-day payment does not reduce the balance again',
          float(d.balance) == before, (before, d.balance))
    pay([date(2026, 10, 16)])
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    check('but the very next day does', float(d.balance) < before, d.balance)
    check('and the floor follows it', d.balance_as_of == date(2026, 10, 16), d.balance_as_of)

    print('\n--- restating the balance as of an earlier date re-opens the skipped rows ---')
    # The pre-floor rows were never marked applied, so they are still reachable. This is
    # what makes leaving them unmarked the right call rather than mere tidiness.
    d.balance = 26000.00
    d.balance_as_of = date(2026, 6, 1)
    db.session.commit()
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    check('a balance restated as older takes in the June payment too',
          float(d.balance) < 25047.80, d.balance)
    wipe()

    print('\n--- the direction of the error is never the flattering one ---')
    d = truck()
    pay(PAYMENTS)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d)
    guarded = float(d.balance)
    wipe()
    d2 = truck(as_of=date(2026, 6, 1))
    pay(PAYMENTS)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(d2)
    check('guarding the date can only leave a debt larger, never smaller',
          guarded > float(d2.balance), (guarded, d2.balance))
    check('and the unguarded figure is the one production was showing',
          abs(float(d2.balance) - 23595.26) < 0.005, d2.balance)
    wipe()

    print('\n--- escrow still comes out before principal, with the floor in place ---')
    m = A.Debt(user_id=UID, name='1st Mortgage', type='mortgage', balance=342000.00,
               apr=6.0, escrow_monthly=66.00, min_payment=3100.00,
               balance_as_of=date(2026, 8, 1))
    db.session.add(m)
    db.session.commit()
    db.session.add(A.RecurringBill(user_id=UID, name='Mortgage', payee='UWM',
                                   category='housing', amount=3103.88, frequency='monthly',
                                   linked_debt_id=m.id, active=True))
    db.session.add_all([
        A.SpendTransaction(user_id=UID, posted_at=date(2026, 7, 6), description='UWM',
                           merchant='UWM', category='housing', amount=3103.88,
                           source='plaid', external_id='plaid:uwm-jul'),
        A.SpendTransaction(user_id=UID, posted_at=date(2026, 9, 6), description='UWM',
                           merchant='UWM', category='housing', amount=3103.88,
                           source='plaid', external_id='plaid:uwm-sep'),
    ])
    db.session.commit()
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(m)
    # 342,000 at 6% is 1,710.00 of interest; 3,103.88 - 1,710.00 - 66.00 escrow = 1,327.88
    check('one payment applied, by principal net of escrow',
          abs(float(m.balance) - (342000.00 - 1327.88)) < 0.02, m.balance)
    check('the July payment was already inside the August figure',
          float(m.balance) > 342000.00 - 2 * 1327.88, m.balance)
    wipe()

print('\n--- the API stamps the date, because the user is the only one who knows it ---')
with app.app_context():
    c = client_for(UID)
    r = c.post('/api/finance/debts', json={'name': 'Truck', 'type': 'auto',
                                           'balance': 25767.33, 'apr': 8.1})
    check('create succeeds', r.status_code == 201, r.status_code)
    body = r.get_json()
    check('a new balance is taken as read today',
          body.get('balance_as_of') == TODAY.isoformat(), body.get('balance_as_of'))
    check('and to_dict reports it at all', 'balance_as_of' in body, sorted(body))
    did = body['id']

    r = c.post('/api/finance/debts', json={'name': 'Older', 'type': 'personal',
                                           'balance': 500.0, 'apr': 5.0,
                                           'balance_as_of': '2026-01-15'})
    check('an explicitly older figure is honoured on create',
          r.get_json().get('balance_as_of') == '2026-01-15',
          r.get_json().get('balance_as_of'))

    r = c.put('/api/finance/debts/%d' % did, json={'balance': 25000.00})
    check('a corrected balance restamps to today',
          r.get_json().get('balance_as_of') == TODAY.isoformat(),
          r.get_json().get('balance_as_of'))

    with app.app_context():
        x = db.session.get(A.Debt, did)
        x.balance_as_of = date(2026, 3, 3)
        db.session.commit()
    r = c.put('/api/finance/debts/%d' % did, json={'apr': 9.25})
    check('EDITING THE APR DOES NOT RE-DATE THE BALANCE',
          r.get_json().get('balance_as_of') == '2026-03-03',
          r.get_json().get('balance_as_of'))
    r = c.put('/api/finance/debts/%d' % did, json={'balance': 25000.00})
    check('nor does re-sending the same balance',
          r.get_json().get('balance_as_of') == '2026-03-03',
          r.get_json().get('balance_as_of'))
    r = c.put('/api/finance/debts/%d' % did, json={'balance': 24000.00,
                                                   'balance_as_of': '2026-05-05'})
    check('an explicit date on an edit wins',
          r.get_json().get('balance_as_of') == '2026-05-05',
          r.get_json().get('balance_as_of'))

    print('\n--- a recorded payment carries the date forward, never backward ---')
    r = c.post('/api/finance/debts/%d/payment' % did,
               json={'amount': 650.00, 'posted_at': '2026-06-20'})
    check('recording a payment succeeds', r.status_code == 201, (r.status_code, r.get_json()))
    with app.app_context():
        check('and advances the as-of date to the payment',
              db.session.get(A.Debt, did).balance_as_of == date(2026, 6, 20),
              db.session.get(A.Debt, did).balance_as_of)
    r = c.post('/api/finance/debts/%d/payment' % did,
               json={'amount': 650.00, 'posted_at': '2026-05-01'})
    with app.app_context():
        x = db.session.get(A.Debt, did)
        check('a late-entered older payment still reduces the balance',
              float(x.balance) < 24000.00, x.balance)
        check('but does not drag the as-of date back and re-open the gap',
              x.balance_as_of == date(2026, 6, 20), x.balance_as_of)

print('\n--- A RATE IS ONLY TRUE AS OF A DATE, TOO ---')
# The roof loan is the case. It was recorded at 11.900% and that was RIGHT when it was
# entered: the lender's own "interest paid YTD" of $5,441.93, less the known September
# ($515.49) and October ($496.76) interest, leaves $4,429.68 over the 243 days of the
# January-August payments -- $18.23/day, which is 11.90% on the balance it carried then
# and cannot be 10.95% on any balance a $57,000 line can hold. By 2026-11-12 the lender's
# rate was 10.950%. The number was never wrong; it went stale, and nothing in the app
# could tell a rate read yesterday from one read in March.
with app.app_context():
    c = client_for(UID)

    r = c.post('/api/finance/debts', json={'name': 'Roof', 'type': 'home_improvement',
                                           'balance': 54941.93, 'apr': 11.9})
    check('create succeeds', r.status_code == 201, r.status_code)
    body = r.get_json()
    rid = body['id']
    check('a new APR is taken as read today',
          body.get('apr_as_of') == TODAY.isoformat(), body.get('apr_as_of'))
    check('to_dict reports apr_as_of', 'apr_as_of' in body, sorted(body))
    check('and reports its age, which is 0 on the day it was stated',
          body.get('apr_age_days') == 0, body.get('apr_age_days'))

    r = c.post('/api/finance/debts', json={'name': 'Promo card', 'type': 'credit_card',
                                           'balance': 1200.0, 'apr': 0})
    check('a 0% APR is stamped too -- a promo rate has an expiry, it is not a missing value',
          r.get_json().get('apr_as_of') == TODAY.isoformat(), r.get_json().get('apr_as_of'))

    r = c.post('/api/finance/debts', json={'name': 'Old quote', 'type': 'personal',
                                           'balance': 900.0, 'apr': 7.25,
                                           'apr_as_of': '2026-02-01'})
    check('an explicitly older rate date is honoured on create',
          r.get_json().get('apr_as_of') == '2026-02-01', r.get_json().get('apr_as_of'))

    x = A.Debt(user_id=UID, name='Never stated', type='other', balance=100.0, apr=6.0)
    db.session.add(x)
    db.session.commit()
    check('an unstamped APR reports age None, not a large number',
          x.apr_age_days() is None, x.apr_age_days())
    x.apr_as_of = date(2026, 1, 1)
    check('and counts real days once it is stated',
          x.apr_age_days(today=date(2026, 3, 2)) == 60,
          x.apr_age_days(today=date(2026, 3, 2)))

print('\n--- the two as-of dates move independently ---')
with app.app_context():
    c = client_for(UID)
    y = db.session.get(A.Debt, rid)
    y.apr_as_of = date(2026, 3, 3)
    y.balance_as_of = date(2026, 4, 4)
    db.session.commit()

    r = c.put('/api/finance/debts/%d' % rid, json={'balance': 54000.00})
    check('CORRECTING THE BALANCE DOES NOT RE-DATE THE APR',
          r.get_json().get('apr_as_of') == '2026-03-03', r.get_json().get('apr_as_of'))
    check('though it does re-date the balance',
          r.get_json().get('balance_as_of') == TODAY.isoformat(),
          r.get_json().get('balance_as_of'))

    r = c.put('/api/finance/debts/%d' % rid, json={'apr': 11.9})
    check('re-sending the SAME APR does not re-date it',
          r.get_json().get('apr_as_of') == '2026-03-03', r.get_json().get('apr_as_of'))

    r = c.put('/api/finance/debts/%d' % rid, json={'apr': 10.95})
    check('but a CHANGED APR is a fresh reading and restamps',
          r.get_json().get('apr_as_of') == TODAY.isoformat(), r.get_json().get('apr_as_of'))

    r = c.put('/api/finance/debts/%d' % rid, json={'apr': 9.5, 'apr_as_of': '2026-07-07'})
    check('an explicit rate date on an edit wins over today',
          r.get_json().get('apr_as_of') == '2026-07-07', r.get_json().get('apr_as_of'))

    y = db.session.get(A.Debt, rid)
    y.apr_as_of = date(2026, 3, 3)
    db.session.commit()
    r = c.put('/api/finance/debts/%d' % rid, json={'apr': 9.5004})
    check('a change below the stored precision is not a new reading',
          r.get_json().get('apr_as_of') == '2026-03-03', r.get_json().get('apr_as_of'))


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DEBT AS-OF CHECKS PASSED')
