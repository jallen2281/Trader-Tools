"""A one-off planned payment: lands once, on its date, and never raises the monthly floor.

The budget had only cadences -- weekly through annual -- so there was nowhere to put a
single planned lump (a card payoff, Christmas, a deductible). Forcing one in as 'annual'
would repeat it every year; forcing it in as 'monthly' would repeat it twelve times and
inflate the recurring floor that every affordability figure is built on.

What this pins down:
  * upcoming_due_dates returns exactly ONE date, not a cadence
  * a past one-off does not project into the future
  * monthly_amount is 0 -- it is not part of the recurring floor
  * the cash-flow projection shows it once, on the day, with the right running balance
  * a one-off PROPERTY TAX still counts once toward Schedule A, even though its
    FREQ_PER_YEAR is 0 (the one place 0 would have been silently wrong)
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-one-time-bills')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, RecurringBill

UID = 1

with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='onetime@x.com', name='One Time',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    today = date.today()
    soon = today + timedelta(days=10)
    past = today - timedelta(days=10)

    payoff = RecurringBill(user_id=UID, name='Discover payoff', category='debt',
                           amount=2822.17, frequency='one_time', next_due_date=soon)
    stale = RecurringBill(user_id=UID, name='Last year gifts', category='personal',
                          amount=900.00, frequency='one_time', next_due_date=past)
    monthly = RecurringBill(user_id=UID, name='Mortgage', category='housing',
                            amount=3107.00, frequency='monthly', next_due_date=soon)
    db.session.add_all([payoff, stale, monthly])
    db.session.commit()

    print('--- a one-off happens once ---')
    dates = payoff.upcoming_due_dates(12)
    check('asking for 12 occurrences returns 1', len(dates) == 1, dates)
    check('and it is the due date itself', dates == [soon], dates)
    check('a monthly bill still repeats', len(monthly.upcoming_due_dates(12)) == 12)

    print('\n--- it stays out of the recurring monthly floor ---')
    check('monthly_amount is 0', payoff.monthly_amount() == 0.0, payoff.monthly_amount())
    check('a monthly bill is unaffected', monthly.monthly_amount() == 3107.00, monthly.monthly_amount())
    check("'one_time' is an accepted frequency", 'one_time' in A.BILL_FREQUENCIES)

    print('\n--- the cash-flow projection ---')
    # No income, so the running balance is the starting balance less the one-off.
    proj = A._finance_cashflow(UID, days=60, starting_balance=10000.00)
    hits = [e for e in proj['events'] if e['label'] == 'Discover payoff']
    check('the payoff appears exactly once in 60 days', len(hits) == 1, len(hits))
    check('on its due date', hits and hits[0]['date'] == soon.isoformat(), hits)
    check('as an outflow of the full amount', hits and hits[0]['amount'] == -2822.17, hits)
    check('a due date in the past does not project',
          not [e for e in proj['events'] if e['label'] == 'Last year gifts'],
          [e['label'] for e in proj['events']])
    # 60 days of a monthly mortgage is 2 hits, plus the single payoff.
    mort = [e for e in proj['events'] if e['label'] == 'Mortgage']
    check('the monthly bill still recurs beside it', len(mort) >= 2, len(mort))
    expected = round(10000.00 - 2822.17 - 3107.00 * len(mort), 2)
    check('the ending balance counts the one-off once', proj['ending_balance'] == expected,
          (proj['ending_balance'], expected))

    print('\n--- 180 days: still once, not once a year ---')
    far = A._finance_cashflow(UID, days=180, starting_balance=10000.00)
    check('one hit over 180 days too',
          len([e for e in far['events'] if e['label'] == 'Discover payoff']) == 1,
          [e['date'] for e in far['events'] if e['label'] == 'Discover payoff'])

    print('\n--- a one-off property tax is still deductible once ---')
    # FREQ_PER_YEAR is 0 for one_time so the budget floor stays honest. Schedule A must NOT
    # take that literally: tax paid this year is deducted this year.
    db.session.add(RecurringBill(user_id=UID, name='Township property tax - winter',
                                 category='taxes', amount=6126.93, frequency='one_time',
                                 next_due_date=soon))
    db.session.commit()
    check('counted once, at face value', A._property_tax_annual(UID) == 6126.93,
          A._property_tax_annual(UID))

    db.session.add(RecurringBill(user_id=UID, name='Township property tax - summer',
                                 category='taxes', amount=2744.82, frequency='annual',
                                 next_due_date=soon))
    db.session.commit()
    check('alongside an annual one', A._property_tax_annual(UID) == round(6126.93 + 2744.82, 2),
          A._property_tax_annual(UID))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL ONE-TIME BILL CHECKS PASSED')
