"""Recurring-charge detection.

Pure logic, no database. The negative cases carry most of the weight: a detector that
reports the supermarket as a subscription because someone shops most weeks is worse than no
detector, because everything it says gets ignored.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())

import recurring_detector as R  # noqa: E402

fails = []
TODAY = date(2026, 9, 7)


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def series(label, amount, start, count, every_days, category='subscriptions', drift=0):
    """`drift` shifts each charge slightly, the way real billing slides across weekends."""
    out = []
    for i in range(count):
        d = start + timedelta(days=every_days * i + (i % 2) * drift)
        amt = amount(i) if callable(amount) else amount
        out.append({'posted_at': d, 'amount': amt, 'merchant': label, 'category': category})
    return out


print('\n--- merchant identity survives the noise banks add ---')
same = ['NETFLIX.COM', 'NETFLIX.COM 866-579-7172', 'SQ *NETFLIX.COM', 'NETFLIX.COM  CA']
keys = {R.merchant_key(x) for x in same}
check('one identity across processor prefixes, phone numbers and state tails',
      len(keys) == 1, keys)
check('store numbers do not split a merchant',
      R.merchant_key('WEGMANS #442') == R.merchant_key('WEGMANS #1180'),
      (R.merchant_key('WEGMANS #442'), R.merchant_key('WEGMANS #1180')))
check('terminal ids are stripped',
      R.merchant_key('SPOTIFY P0A1B2C3') == R.merchant_key('SPOTIFY XY99Z1'),
      (R.merchant_key('SPOTIFY P0A1B2C3'), R.merchant_key('SPOTIFY XY99Z1')))
check('genuinely different merchants stay different',
      R.merchant_key('NETFLIX.COM') != R.merchant_key('HULU'),
      (R.merchant_key('NETFLIX.COM'), R.merchant_key('HULU')))
check('empty input is handled', R.merchant_key(None) == '' and R.merchant_key('') == '')

print('\n--- a monthly subscription is found ---')
txns = series('NETFLIX.COM', 15.99, date(2026, 3, 3), 7, 30, drift=1)
[found] = R.detect(txns, today=TODAY)
check('cadence identified as monthly', found['cadence'] == 'monthly', found['cadence'])
check('typical amount is the median', found['typical_amount'] == 15.99, found['typical_amount'])
check('annualised correctly', 190 < found['annual_equivalent'] < 200, found['annual_equivalent'])
check('counted every occurrence', found['occurrences'] == 7, found['occurrences'])
check('still active', found['status'] == 'active', found['status'])
check('predicts the next charge', found['next_expected'] > found['last_seen'])

print('\n--- things that are NOT subscriptions are left alone ---')
groceries = []
for i in range(12):
    groceries.append({'posted_at': date(2026, 6, 1) + timedelta(days=i * 6 + (i % 3)),
                      'amount': 40 + i * 11, 'merchant': 'WEGMANS #442', 'category': 'food'})
check('a shop visited often at varying amounts is not recurring',
      R.detect(groceries, today=TODAY) == [], R.detect(groceries, today=TODAY))
check('two charges are not enough to establish a pattern',
      R.detect(series('ADOBE', 20.0, date(2026, 7, 1), 2, 30), today=TODAY) == [])
irregular = [{'posted_at': date(2026, 1, 5), 'amount': 30, 'merchant': 'X'},
             {'posted_at': date(2026, 2, 20), 'amount': 30, 'merchant': 'X'},
             {'posted_at': date(2026, 5, 9), 'amount': 30, 'merchant': 'X'}]
check('a steady amount at random intervals is not recurring',
      R.detect(irregular, today=TODAY) == [], R.detect(irregular, today=TODAY))
refunds = series('REFUNDER', -9.99, date(2026, 4, 1), 5, 30)
check('refunds and credits are ignored', R.detect(refunds, today=TODAY) == [])

print('\n--- other cadences ---')
for label, days, expect in (('weekly', 7, 'weekly'), ('biweekly', 14, 'biweekly'),
                            ('quarterly', 91, 'quarterly'), ('annual', 365, 'annual')):
    t = series(label.upper() + 'SVC', 25.0, date(2022, 1, 10), 4, days)
    got = R.detect(t, today=TODAY)
    check('%s cadence identified' % label,
          len(got) == 1 and got[0]['cadence'] == expect,
          got[0]['cadence'] if got else 'none found')

print('\n--- a price increase is spotted ---')
rising = series('SPOTIFY', lambda i: 10.99 if i < 5 else 12.99, date(2026, 2, 1), 7, 30)
[sp] = R.detect(rising, today=TODAY)
check('flagged as increased', sp['price_increased'] is True, sp)
check('reports the size of the rise', sp['price_change'] == 2.0, sp['price_change'])
steady = series('HULU', 17.99, date(2026, 2, 1), 7, 30)
check('a stable price is not flagged', R.detect(steady, today=TODAY)[0]['price_increased'] is False)

print('\n--- a charge that stopped is spotted ---')
gone = series('OLDGYM', 45.0, date(2025, 9, 1), 6, 30)     # last charge ~Feb 2026
[g] = R.detect(gone, today=TODAY)
check('marked stopped', g['status'] == 'stopped', g['status'])

print('\n--- findings, and what they exclude ---')
bills = [{'id': 7, 'name': 'Netflix', 'payee': 'NETFLIX.COM'}]
charges = R.detect(series('NETFLIX.COM', 15.99, date(2026, 3, 3), 7, 30), today=TODAY)
check('a charge already declared as a bill raises nothing',
      R.findings(charges, bills) == [], R.findings(charges, bills))
check('the same charge with no bill is reported as undeclared',
      [f['kind'] for f in R.findings(charges, [])] == ['undeclared'],
      R.findings(charges, []))
R.annotate_matches(charges, bills)
check('annotate_matches links a charge to its declared bill',
      charges[0].get('matched_bill_id') == 7, charges[0].get('matched_bill_id'))
R.annotate_matches(charges, [])
check('and clears it when no bill covers it',
      charges[0].get('matched_bill_id') is None, charges[0].get('matched_bill_id'))
check('a dismissed charge stays quiet',
      R.findings(charges, [], decisions={charges[0]['merchant_key']: 'dismissed'}) == [])
check('one linked by hand also stays quiet',
      R.findings(charges, [], decisions={charges[0]['merchant_key']: 'linked'}) == [])

print('\n--- an annual renewal is flagged before it lands ---')
soon = series('AMZNPRIME', 139.0, date(2022, 9, 20), 4, 365)
f = R.findings(R.detect(soon, today=TODAY), [])
kinds = {x['kind'] for x in f}
check('renewal_due raised for an annual charge coming up', 'renewal_due' in kinds, kinds)
far = series('DOMAINCO', 22.0, date(2022, 2, 1), 4, 365)
check('an annual charge months away is not nagged about',
      'renewal_due' not in {x['kind'] for x in R.findings(R.detect(far, today=TODAY), [])})

print('\n--- ordering puts the expensive problems first ---')
mixed = (series('BIGSVC', 99.0, date(2026, 3, 1), 6, 30)
         + series('TINYSVC', 2.0, date(2026, 3, 2), 6, 30))
f = R.findings(R.detect(mixed, today=TODAY), [])
check('the costlier undeclared subscription is listed first',
      f[0]['amount'] > f[1]['amount'], [(x['title'], x['amount']) for x in f])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for x in fails:
        print('  - ' + x)
    sys.exit(1)
print('ALL RECURRING DETECTION CHECKS PASSED')
