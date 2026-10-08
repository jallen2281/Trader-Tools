"""A declared bill that no longer matches what actually posts gets flagged.

A RecurringBill is a projection, so a stale one does real damage. The case that prompted
this: a mortgage configured to pay $3,107 on the 7th, actually paying $3,103.88 on the
1st. By the 7th the money had already gone, but the cash-flow calendar spent it again --
the projected low point read $2,085 against a true $5,192, and a $2,822 credit-card payoff
looked unaffordable when it was not.

Nothing in the app noticed, because nothing compared a bill to its own history.

What this pins down:
  * a bill that pays on a different day than configured is flagged, with the real day
  * a bill whose amount has moved is flagged, with the real amount
  * a bill that matches reality is NOT flagged (the expensive failure: a card that cries
    wolf gets ignored, and then the real drift is missed too)
  * day-of-month distance goes the short way round -- the 1st and the 30th are two days
    apart, not twenty-nine
  * one sighting is not enough to call something drift
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-bill-drift')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, RecurringBill, SpendTransaction

UID = 1
TODAY = date.today()


def months_back(n, day):
    """The given day-of-month for each of the last n whole months, oldest first."""
    out = []
    for k in range(n, 0, -1):
        mm, yy = TODAY.month - k, TODAY.year
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(date(yy, mm, min(day, 28)))
    return out


def post(merchant, when, amount, category='other'):
    db.session.add(SpendTransaction(user_id=UID, posted_at=when, merchant=merchant,
                                    description=merchant, category=category,
                                    amount=amount))


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='drift@x.com', name='Drift',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    print('--- day-of-month distance goes the short way ---')
    check('the 1st and the 7th are six apart', A._day_of_month_gap(1, 7) == 6)
    check('the 1st and the 30th are two apart', A._day_of_month_gap(1, 30) == 2,
          A._day_of_month_gap(1, 30))
    check('the 28th and the 2nd are five apart', A._day_of_month_gap(28, 2) == 5,
          A._day_of_month_gap(28, 2))
    check('a day is zero from itself', A._day_of_month_gap(15, 15) == 0)

    # The real case: configured 3107 on the 7th, actually 3103.88 on the 1st.
    mortgage = RecurringBill(user_id=UID, name='Mortgage', payee='United Wholesale',
                             category='housing', amount=3107.00, frequency='monthly',
                             due_day=7, active=True)
    # Amount drift only: budgeted off summer bills, winter arrived.
    electric = RecurringBill(user_id=UID, name='Electric', payee='DTE Energy',
                             category='utilities', amount=421.99, frequency='monthly',
                             due_day=20, active=True)
    # Honest bill. Must stay off the list.
    netflix = RecurringBill(user_id=UID, name='Netflix', payee='Netflix',
                            category='subscriptions', amount=26.99, frequency='monthly',
                            due_day=11, active=True)
    # Seen once. Not enough to call it anything.
    rare = RecurringBill(user_id=UID, name='Rare thing', payee='Rare Co',
                         category='other', amount=50.00, frequency='monthly',
                         due_day=5, active=True)
    db.session.add_all([mortgage, electric, netflix, rare])
    db.session.commit()

    for d in months_back(5, 1):
        post('United Wholesale', d, 3103.88, 'housing')
    for d in months_back(5, 20):
        post('DTE Energy', d, 521.20, 'utilities')
    for d in months_back(5, 11):
        post('Netflix', d, 26.99, 'subscriptions')
    post('Rare Co', months_back(2, 5)[0], 95.00)
    db.session.commit()

    res = A._bill_drift(UID)
    by_name = {r['name']: r for r in res['drifted']}
    print('\n--- what got flagged ---')
    for r in res['drifted']:
        print('     %-12s %s' % (r['name'], [i['kind'] for i in r['issues']]))

    print('\n--- the mortgage: right bill, wrong day ---')
    m = by_name.get('Mortgage')
    check('it is flagged', m is not None, list(by_name))
    if m:
        kinds = {i['kind']: i for i in m['issues']}
        check('for the due day', 'due_day' in kinds, list(kinds))
        if 'due_day' in kinds:
            check('reporting the configured 7th', kinds['due_day']['configured'] == 7, kinds)
            check('against the actual 1st', kinds['due_day']['actual'] == 1, kinds)
            check('six days apart', kinds['due_day']['delta'] == 6, kinds)
        check('and it suggests the real day', m['suggested'].get('due_day') == 1,
              m['suggested'])
        # $3.12 on $3,107 is a tenth of a percent -- noise, not drift.
        check('the trivial amount difference is not flagged', 'amount' not in kinds,
              kinds.get('amount'))

    print('\n--- the electric bill: right day, wrong amount ---')
    e = by_name.get('Electric')
    check('it is flagged', e is not None, list(by_name))
    if e:
        kinds = {i['kind']: i for i in e['issues']}
        check('for the amount', 'amount' in kinds, list(kinds))
        if 'amount' in kinds:
            check('showing what is configured', kinds['amount']['configured'] == 421.99, kinds)
            check('and what actually posts', kinds['amount']['actual'] == 521.20, kinds)
            check('with the yearly cost of the gap',
                  kinds['amount']['annual_impact'] > 1000, kinds)
        check('it suggests the real amount', e['suggested'].get('amount') == 521.20,
              e['suggested'])
        check('the day is not flagged', 'due_day' not in kinds, kinds.get('due_day'))

    print('\n--- bills that are fine stay off the list ---')
    check('an accurate bill is not flagged', 'Netflix' not in by_name, list(by_name))
    check('a single sighting is not drift', 'Rare thing' not in by_name, list(by_name))
    check('only the two real problems are reported', len(res['drifted']) == 2,
          [r['name'] for r in res['drifted']])
    check('it reports how many bills it checked', res['checked'] == 4, res['checked'])

    print('\n--- worst first ---')
    check('the electric bill outranks the mortgage on annual cost',
          res['drifted'][0]['name'] == 'Electric',
          [r['name'] for r in res['drifted']])

    print('\n--- the endpoint ---')
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    r = c.get('/api/finance/bills/drift')
    check('serves 200', r.status_code == 200, r.status_code)
    j = r.get_json()
    check('with the same findings', len(j['drifted']) == 2, j)

    print('\n--- applying the suggestion clears the finding ---')
    mortgage.due_day = 1
    db.session.commit()
    after = {r['name'] for r in A._bill_drift(UID)['drifted']}
    check('the mortgage drops off once corrected', 'Mortgage' not in after, after)
    check('and the electric bill is still there', 'Electric' in after, after)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BILL DRIFT CHECKS PASSED')
