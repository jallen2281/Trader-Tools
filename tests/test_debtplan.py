"""Debt payoff simulation.

Pure logic, no database. The cases that carry weight are the ones a plausible-looking
simulation gets wrong: not rolling a cleared debt's payment into the next one (which
understates both strategies badly), charging interest after the payment instead of before
(which quietly makes every plan look cheaper than it is), and a minimum that never covers
its own interest (which loops forever unless something stops it).
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())

import debt_planner as P  # noqa: E402

fails = []
START = date(2026, 1, 15)


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def debt(did, name, bal, apr, minp):
    return {'id': did, 'name': name, 'balance': bal, 'apr': apr, 'min_payment': minp}


print('\n--- a single debt behaves like an ordinary loan ---')
one = [debt(1, 'Card', 1000.0, 0.0, 100.0)]
s = P.simulate(one, 0, 'avalanche', start=START)
check('no interest means ten payments of 100', s['months'] == 10, s['months'])
check('and no interest charged', s['total_interest'] == 0.0, s['total_interest'])
check('total paid is the balance', round(s['total_paid']) == 1000, s['total_paid'])
check('a payoff date is given', s['debt_free_on'] == '2026-11-15', s['debt_free_on'])
s2 = P.simulate([debt(1, 'Card', 1000.0, 24.0, 100.0)], 0, 'avalanche', start=START)
check('at 24% it takes longer than ten months', s2['months'] > 10, s2['months'])
check('and interest is actually charged', s2['total_interest'] > 0, s2['total_interest'])

print('\n--- interest is charged BEFORE the payment, as a lender does ---')
# 1000 at 12% for one month = 10 interest. Pay 1010 and it clears in one month, not before.
exact = P.simulate([debt(1, 'X', 1000.0, 12.0, 1010.0)], 0, 'avalanche', start=START)
check('a payment of balance+interest clears it in one month', exact['months'] == 1, exact['months'])
check('and that interest is reported', round(exact['total_interest'], 2) == 10.0,
      exact['total_interest'])
short = P.simulate([debt(1, 'X', 1000.0, 12.0, 1000.0)], 0, 'avalanche', start=START)
check('paying exactly the balance leaves the interest behind', short['months'] == 2,
      short['months'])

print('\n--- a cleared debt rolls its payment into the next one ---')
two = [debt(1, 'Small', 500.0, 0.0, 100.0), debt(2, 'Big', 1000.0, 0.0, 100.0)]
roll = P.simulate(two, 0, 'snowball', start=START)
# Without rolling: Small clears at 5, Big needs 10 -> 10 months.
# With rolling: Small clears at 5, then Big has 500 left and 200/mo -> 5+3 = 8.
check('rolling makes it 8 months, not the 10 it would be without', roll['months'] == 8,
      roll['months'])
check('the small one clears first', roll['order'][0]['name'] == 'Small', roll['order'])
check('every debt is reported in payoff order', len(roll['order']) == 2, roll['order'])
check('the monthly outlay stays flat all the way through',
      roll['monthly_outlay'] == 200.0, roll['monthly_outlay'])

print('\n--- avalanche and snowball differ only in order ---')
mix = [debt(1, 'Tiny card', 500.0, 5.0, 25.0),
       debt(2, 'Big card', 8000.0, 26.0, 200.0)]
c = P.compare(mix, 300, start=START)
check('avalanche attacks the 26% first',
      c['avalanche']['order'][0]['name'] == 'Big card', c['avalanche']['order'])
check('snowball attacks the small balance first',
      c['snowball']['order'][0]['name'] == 'Tiny card', c['snowball']['order'])
check('avalanche costs less interest',
      c['avalanche']['total_interest'] < c['snowball']['total_interest'],
      (c['avalanche']['total_interest'], c['snowball']['total_interest']))
check('the saving is reported as a positive number',
      c['interest_saved_by_avalanche'] > 0, c['interest_saved_by_avalanche'])
check('snowball closes its first account sooner — the point of it',
      c['first_payoff_months']['snowball'] < c['first_payoff_months']['avalanche'],
      c['first_payoff_months'])
check('both send the same amount out each month',
      c['avalanche']['monthly_outlay'] == c['snowball']['monthly_outlay'],
      (c['avalanche']['monthly_outlay'], c['snowball']['monthly_outlay']))

print('\n--- equal-rate debts make the two strategies agree ---')
same = [debt(1, 'A', 1000.0, 10.0, 50.0), debt(2, 'B', 2000.0, 10.0, 50.0)]
c2 = P.compare(same, 100, start=START)
check('same months either way', c2['avalanche']['months'] == c2['snowball']['months'],
      (c2['avalanche']['months'], c2['snowball']['months']))
check('and nothing meaningful saved',
      abs(c2['interest_saved_by_avalanche']) < 1.0, c2['interest_saved_by_avalanche'])

print('\n--- a payment that cannot cover its interest is caught, not looped on ---')
under = [debt(1, 'Underwater', 10000.0, 30.0, 100.0)]      # 250/mo interest, 100 paid
u = P.simulate(under, 0, 'avalanche', start=START)
check('it terminates rather than hanging', u is not None)
check('months is None because it never finishes', u['months'] is None, u['months'])
check('no payoff date is invented', u['debt_free_on'] is None, u['debt_free_on'])
check('the debt is named as never paying off',
      [d['name'] for d in u['never_pays_off']] == ['Underwater'], u['never_pays_off'])
check('and the balance has grown, not shrunk',
      u['never_pays_off'][0]['balance'] > 10000, u['never_pays_off'][0]['balance'])
fixed = P.simulate(under, 400, 'avalanche', start=START)
check('enough extra rescues it', fixed['months'] is not None and not fixed['never_pays_off'],
      (fixed['months'], fixed['never_pays_off']))

print('\n--- extra money is the lever, and its effect is quantified ---')
big = [debt(1, 'Card', 9000.0, 22.0, 250.0)]
imp = P.extra_payment_impact(big, (100, 300), start=START)
o100, o300 = imp['options'][0], imp['options'][1]
check('an extra 100 shortens it', o100['months_sooner'] > 0, o100)
check('and saves interest', o100['interest_saved'] > 0, o100)
check('an extra 300 does more of both',
      o300['months_sooner'] > o100['months_sooner']
      and o300['interest_saved'] > o100['interest_saved'], (o100, o300))
check('the base case is returned for comparison', imp['base']['months'] > o300['months'],
      (imp['base']['months'], o300['months']))

print('\n--- degenerate inputs do not explode ---')
check('no debts at all', P.simulate([], 500, start=START)['months'] == 0)
check('a paid-off debt is ignored',
      P.simulate([debt(1, 'Done', 0.0, 10.0, 50.0)], 0, start=START)['months'] == 0)
check('a negative balance is ignored too',
      P.simulate([debt(1, 'Credit', -50.0, 10.0, 50.0)], 0, start=START)['months'] == 0)
check('zero minimum with extra still pays off',
      P.simulate([debt(1, 'X', 500.0, 0.0, 0.0)], 100, start=START)['months'] == 5)
check('zero minimum and no extra never pays off',
      P.simulate([debt(1, 'X', 500.0, 0.0, 0.0)], 0, start=START)['months'] is None)
check('comparing nothing is safe',
      P.compare([], 0, start=START)['interest_saved_by_avalanche'] == 0.0)

print('\n--- month arithmetic survives month ends and leap years ---')
check('Jan 31 + 1 month is Feb 28 in 2026',
      P._add_months(date(2026, 1, 31), 1).isoformat() == '2026-02-28')
check('Jan 31 + 1 month is Feb 29 in 2028',
      P._add_months(date(2028, 1, 31), 1).isoformat() == '2028-02-29')
check('12 months forward is the same day next year',
      P._add_months(date(2026, 6, 15), 12).isoformat() == '2027-06-15')
check('rolls the year over correctly',
      P._add_months(date(2026, 11, 10), 3).isoformat() == '2027-02-10')

print('\n--- findings say the useful thing ---')
f = P.findings(P.compare(under, 0, start=START), under)
check('an unpayable debt is critical',
      [x for x in f if x['key'].startswith('never_pays_off')][0]['severity'] == 'critical', f)
f2 = P.findings(c, mix)
check('the strategy gap is reported when it is worth money',
      any(x['key'] == 'strategy_gap' for x in f2), [x['key'] for x in f2])
check('high-rate debt is NOT re-raised here — the outlook already says it',
      not any(x['key'] == 'high_rate_debt' for x in f2), [x['key'] for x in f2])
cheap = [debt(1, 'A', 1000.0, 4.0, 100.0), debt(2, 'B', 1100.0, 4.1, 100.0)]
check('a negligible strategy gap is not worth a finding',
      not any(x['key'] == 'strategy_gap'
              for x in P.findings(P.compare(cheap, 0, start=START), cheap)))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for x in fails:
        print('  - ' + x)
    sys.exit(1)
print('ALL DEBT PLAN CHECKS PASSED')
