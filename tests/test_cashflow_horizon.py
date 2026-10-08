"""The cash-flow projection reaches the whole horizon, and counts everyday spending.

Two defects, both of which made the projected balance wrong in the optimistic direction:

  1. The projection asked each income source and each bill for a fixed TWELVE
     occurrences. Twelve weekly bills cover 84 days; twelve biweekly paychecks cover 168.
     Ask for 180 days and the back end of the window had expenses still arriving with the
     paychecks already exhausted -- the ending balance read thousands of dollars low, and
     a weekly bill simply vanished for the last third of the chart.

  2. Only scheduled bills and paychecks were projected at all. Groceries, fuel, feed and
     the long tail of card charges -- the largest controllable outflow in most months --
     were absent, so the running balance drifted above reality the further out it went.

The second fix has a trap of its own: bills are BOTH projected ahead individually and
present in the trailing spend history as transactions. Measuring everyday spending without
subtracting them would charge the projection twice for the same mortgage. The last section
pins that down, because it is the failure that would be easy to ship and hard to see.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-cashflow-horizon')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, RecurringBill, IncomeSource, SpendTransaction

UID = 1
TODAY = date.today()

with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='cf@x.com', name='CF',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    print('--- how many occurrences cover the horizon ---')
    # The arithmetic the old hardcoded 12 got wrong.
    check('180 days of weekly needs more than 12', A._occurrences_for(180, 52) > 12,
          A._occurrences_for(180, 52))
    check('and enough to actually reach it', A._occurrences_for(180, 52) * 7 >= 180,
          A._occurrences_for(180, 52))
    check('180 days of biweekly needs more than 12', A._occurrences_for(180, 26) > 12,
          A._occurrences_for(180, 26))
    check('and enough to reach it', A._occurrences_for(180, 26) * 14 >= 180,
          A._occurrences_for(180, 26))
    check('monthly over 180 days stays small', A._occurrences_for(180, 12) <= 9,
          A._occurrences_for(180, 12))
    check('a one-off asks for exactly one', A._occurrences_for(180, 0) == 1,
          A._occurrences_for(180, 0))

    print('\n--- a 180-day projection reaches day 180 ---')
    db.session.add(IncomeSource(
        id=10, user_id=UID, name='Paycheck', owner='me', type='salary',
        annual_salary=104000, pay_frequency='biweekly', tax_form='W2', active=True,
        next_pay_date=TODAY + timedelta(days=2)))
    db.session.add(RecurringBill(user_id=UID, name='Weekly thing', category='other',
                                 amount=25.00, frequency='weekly',
                                 next_due_date=TODAY + timedelta(days=1)))
    db.session.add(RecurringBill(user_id=UID, name='Rent', category='housing',
                                 amount=1500.00, frequency='monthly',
                                 next_due_date=TODAY + timedelta(days=5)))
    db.session.commit()

    # No spend history yet, so this section sees bills and income only.
    far = A._finance_cashflow(UID, days=180, starting_balance=10000.0)
    last_80 = (TODAY + timedelta(days=100)).isoformat()
    inc_late = [e for e in far['events'] if e['type'] == 'income' and e['date'] > last_80]
    wk_late = [e for e in far['events'] if e['label'] == 'Weekly thing' and e['date'] > last_80]
    check('income is still arriving in the final third', len(inc_late) >= 4, len(inc_late))
    check('so is the weekly bill', len(wk_late) >= 8, len(wk_late))
    # A biweekly paycheck over 180 days is ~12-13 of them; 12 was right at the edge.
    inc_all = [e for e in far['events'] if e['type'] == 'income']
    check('the whole window has its paychecks', len(inc_all) >= 12, len(inc_all))
    wk_all = [e for e in far['events'] if e['label'] == 'Weekly thing']
    check('and all ~26 weekly charges, not 12', len(wk_all) >= 24, len(wk_all))

    print('\n--- everyday spending is projected, and bills are not counted twice ---')
    # A realistic 90 days. The bills really do land as transactions (three rents, thirteen
    # weekly charges) AND there is 20.00/day of groceries on top. Only the groceries are
    # unmodelled, so only the groceries may survive into the burn rate.
    #
    # The history has to be this complete on purpose: a window whose transactions fall
    # short of what the bills imply is indistinguishable from "no unmodelled spending",
    # and the guard correctly returns zero. That is right for production and useless as a
    # fixture.
    for i in range(1, 91):
        db.session.add(SpendTransaction(
            user_id=UID, posted_at=TODAY - timedelta(days=i), merchant='Groceries',
            description='Groceries', category='food', amount=20.00))
    for i in (10, 40, 70):
        db.session.add(SpendTransaction(
            user_id=UID, posted_at=TODAY - timedelta(days=i), merchant='Landlord',
            description='Rent', category='housing', amount=1500.00))
    weekly_hits = len(range(3, 91, 7))
    for i in range(3, 91, 7):
        db.session.add(SpendTransaction(
            user_id=UID, posted_at=TODAY - timedelta(days=i), merchant='Weekly thing',
            description='Weekly thing', category='other', amount=25.00))
    db.session.commit()

    GROCERIES = 90 * 20.00          # the only spending the bill calendar does not model
    burn, detail = A._variable_daily_burn(UID)
    check('a burn rate is produced', burn > 0, (burn, detail))
    check('it reports the window it measured', detail.get('window_days') == 90, detail)
    check('observed spend is every transaction in the window',
          detail.get('observed_spend') == round(GROCERIES + 4500 + weekly_hits * 25, 2),
          detail)
    check('bills are subtracted, not ignored', detail.get('bills_in_window', 0) > 0, detail)
    # The whole point: rent and the weekly bill are projected ahead on their own, so they
    # must not also ride along in the burn. Anything near the full observed spend means
    # the mortgage is being charged to the projection twice.
    check('the residual is the unmodelled spending, not the bills',
          abs(detail['residual'] - GROCERIES) < 150, (detail['residual'], GROCERIES))
    check('which is roughly the daily grocery run', abs(burn - 20.00) < 2.0, burn)
    check('and a monthly figure is reported',
          abs(detail['monthly'] - burn * 365 / 12) < 1.0, detail)

    print('\n--- it lands in the projection and moves the balance ---')
    with_var = A._finance_cashflow(UID, days=60, starting_balance=10000.0)
    without = A._finance_cashflow(UID, days=60, starting_balance=10000.0,
                                  include_variable=False)
    vevents = [e for e in with_var['events'] if e['type'] == 'variable']
    check('weekly buckets appear', len(vevents) >= 8, len(vevents))
    check('they are outflows', all(e['amount'] < 0 for e in vevents), vevents[:3])
    total_var = round(sum(-e['amount'] for e in vevents), 2)
    check('they sum to the burn rate across the whole window',
          abs(total_var - burn * 60) < 1.0, (total_var, burn * 60))
    check('no bucket runs past the horizon',
          max(e['date'] for e in vevents) <= (TODAY + timedelta(days=60)).isoformat(),
          max(e['date'] for e in vevents))
    check('the ending balance is lower than the bills-only view',
          with_var['ending_balance'] < without['ending_balance'],
          (with_var['ending_balance'], without['ending_balance']))
    check('by the projected spending',
          abs((without['ending_balance'] - with_var['ending_balance']) - total_var) < 1.0,
          (without['ending_balance'], with_var['ending_balance'], total_var))
    check('the opt-out really opts out',
          not [e for e in without['events'] if e['type'] == 'variable'])
    check('the burn figures are reported', with_var['variable_daily'] == burn,
          with_var.get('variable_daily'))

    print('\n--- the endpoint honours ?variable=0 ---')
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    on = c.get('/api/finance/cashflow?days=60').get_json()
    off = c.get('/api/finance/cashflow?days=60&variable=0').get_json()
    check('on by default', on['variable_daily'] > 0, on.get('variable_daily'))
    check('off when asked', off['variable_daily'] == 0, off.get('variable_daily'))
    check('and the balances differ accordingly',
          off['ending_balance'] > on['ending_balance'],
          (off['ending_balance'], on['ending_balance']))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CASHFLOW HORIZON CHECKS PASSED')
