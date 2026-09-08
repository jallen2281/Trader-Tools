"""Credit utilization and score trends.

Pure logic, no database. The case that matters most is the one where readings from two
bureaus get mixed together: that is how a credit tracker invents a 40-point crash that
never happened, and it is silent when it does.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())

import credit as C  # noqa: E402

fails = []
TODAY = date(2026, 9, 7)


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def card(name, bal, limit, cid=None):
    return {'id': cid or name, 'name': name, 'balance': bal, 'credit_limit': limit}


def reading(d, score, bureau='equifax', scale='fico8'):
    return {'as_of': d, 'score': score, 'bureau': bureau, 'scale': scale}


print('\n--- utilization is balance over limit, per card and overall ---')
u = C.utilization([card('Visa', 1200, 5000), card('Amex', 300, 10000)])
check('overall ratio is the totals, not an average of the cards',
      u['pct'] == 10.0, u['pct'])          # 1500/15000, not (24% + 3%)/2
check('total limit summed', u['total_limit'] == 15000, u['total_limit'])
check('available credit reported', u['available'] == 13500, u['available'])
check('per-card ratios kept', u['cards'][0]['pct'] == 24.0, u['cards'])
check('worst card first', u['cards'][0]['name'] == 'Visa', [c['name'] for c in u['cards']])
check('and named directly', u['highest_card']['name'] == 'Visa')

print('\n--- a card with no limit recorded is unknown, never zero ---')
u2 = C.utilization([card('Visa', 1200, 5000), card('Store card', 900, 0)])
check('it does not contribute to the ratio', u2['pct'] == 24.0, u2['pct'])
check('its balance is not silently counted', u2['total_balance'] == 1200, u2['total_balance'])
check('but it is reported as missing',
      [c['name'] for c in u2['cards_without_limit']] == ['Store card'], u2['cards_without_limit'])
check('no cards at all yields no ratio rather than zero',
      C.utilization([])['ratio'] is None, C.utilization([]))
check('no limits anywhere also yields no ratio',
      C.utilization([card('X', 500, 0)])['ratio'] is None)
check('a negative balance (overpaid card) does not go below zero',
      C.utilization([card('X', -50, 1000)])['pct'] == 0.0)

print('\n--- the paydown figure is the actual move to make ---')
u3 = C.utilization([card('Visa', 4000, 10000)])
check('40% down to 30% is $1,000', C.paydown_to(u3) == 1000.0, C.paydown_to(u3))
check('already under target asks for nothing',
      C.paydown_to(C.utilization([card('Visa', 500, 10000)])) == 0.0)
check('a different target is honoured',
      C.paydown_to(u3, 0.10) == 3000.0, C.paydown_to(u3, 0.10))
check('no limit means no answer, not a divide by zero',
      C.paydown_to(C.utilization([card('X', 500, 0)])) == 0.0)

print('\n--- score bands ---')
for score, expect in ((810, 'exceptional'), (740, 'very good'), (700, 'good'),
                      (600, 'fair'), (520, 'poor')):
    check('%d is %s' % (score, expect), C.band(score) == expect, C.band(score))
check('no score has no band', C.band(None) is None)

print('\n--- readings from different bureaus are NEVER one line ---')
mixed = [reading(date(2026, 6, 1), 742, 'equifax', 'fico8'),
         reading(date(2026, 7, 1), 700, 'transunion', 'vantage3'),
         reading(date(2026, 8, 1), 748, 'equifax', 'fico8')]
s = C.series(mixed)
check('two separate series', len(s) == 2, [x['key'] for x in s])
eq = [x for x in s if x['bureau'] == 'equifax'][0]
check('the equifax trend compares equifax to equifax', eq['change'] == 6, eq['change'])
check('and does not see the vantage reading', eq['readings'] == 2, eq['readings'])
tu = [x for x in s if x['bureau'] == 'transunion'][0]
check('a single reading has no trend to report', tu['change'] is None, tu['change'])
check('the scale is named, since the number means nothing without it',
      tu['scale_label'] == 'VantageScore 3.0', tu['scale_label'])
check('a naive mix would have claimed a 42-point crash — it does not',
      not any(x['change'] is not None and x['change'] < 0 for x in s),
      [(x['key'], x['change']) for x in s])

print('\n--- a series reports latest, previous and all-time ---')
one = C.series([reading(date(2025, 1, 5), 640), reading(date(2025, 8, 5), 690),
                reading(date(2026, 8, 5), 715)])[0]
check('latest is the most recent by date, not by insertion order', one['latest'] == 715)
check('previous is the one before it', one['previous'] == 690, one['previous'])
check('change since last reading', one['change'] == 25, one['change'])
check('change since the first', one['change_all_time'] == 75, one['change_all_time'])
check('history is in date order for plotting',
      [h['score'] for h in one['history']] == [640, 690, 715], one['history'])
check('band from the latest', one['band'] == 'good', one['band'])

print('\n--- findings: high utilization is the loudest one ---')
f = C.findings(C.utilization([card('Visa', 6000, 10000)]), [], today=TODAY)
top = f[0]
check('flagged as a warning', top['severity'] == 'warning', top)
check('names the ratio', '60%' in top['title'], top['title'])
check('and states the dollars to move', top['amount'] == 3000.0, top['amount'])
f2 = C.findings(C.utilization([card('Visa', 3500, 10000)]), [], today=TODAY)
check('35% is a note, not a warning',
      [x for x in f2 if x['key'] == 'utilization_elevated'][0]['severity'] == 'note', f2)
f3 = C.findings(C.utilization([card('Visa', 1000, 10000)]), [], today=TODAY)
check('10% is quiet on utilization',
      not [x for x in f3 if x['kind'] == 'utilization'], f3)

print('\n--- one maxed card is a problem even when the total looks fine ---')
u4 = C.utilization([card('Small card', 980, 1000, 'c1'), card('Big card', 200, 20000, 'c2')])
check('overall is comfortable', u4['pct'] < 10, u4['pct'])
f4 = C.findings(u4, [], today=TODAY)
check('the maxed card is still called out',
      any(x['key'] == 'card_maxed:c1' for x in f4), [x['key'] for x in f4])
check('and the healthy card is not', not any(x['key'] == 'card_maxed:c2' for x in f4))
check('it is not repeated when the overall ratio already covers it',
      not any(x['key'].startswith('card_maxed') for x in
              C.findings(C.utilization([card('Only card', 980, 1000, 'c1')]), [], today=TODAY)),
      [x['key'] for x in C.findings(C.utilization([card('Only', 980, 1000, 'c1')]), [], today=TODAY)])

print('\n--- score moves ---')
drop = C.series([reading(date(2026, 5, 1), 745), reading(date(2026, 8, 1), 702)])
fd = C.findings(C.utilization([]), drop, today=TODAY)
d = [x for x in fd if x['key'].startswith('score_drop')][0]
check('a 43-point fall is a warning', d['severity'] == 'warning', d)
check('it says how far', '43 points' in d['title'], d['title'])
check('and names the scale, so it is not read against another bureau',
      'FICO 8' in d['detail'], d['detail'])
gain = C.series([reading(date(2026, 5, 1), 690), reading(date(2026, 8, 1), 725)])
fg = C.findings(C.utilization([]), gain, today=TODAY)
check('a rise is reported as a note', [x for x in fg if x['key'].startswith('score_gain')][0]['severity'] == 'note')
noise = C.series([reading(date(2026, 5, 1), 742), reading(date(2026, 8, 1), 748)])
check('a six-point wobble is not an event',
      not [x for x in C.findings(C.utilization([]), noise, today=TODAY)
           if x['kind'] == 'score'],
      C.findings(C.utilization([]), noise, today=TODAY))

print('\n--- stale and missing data are said plainly ---')
old = C.series([reading(date(2025, 11, 1), 720)])
check('a year-old reading is flagged stale',
      any(x['key'] == 'score_stale' for x in C.findings(C.utilization([]), old, today=TODAY)))
check('a recent one is not',
      not any(x['key'] == 'score_stale' for x in
              C.findings(C.utilization([]), C.series([reading(date(2026, 8, 20), 720)]),
                         today=TODAY)))
check('no scores at all is worth saying when there are cards',
      any(x['key'] == 'no_scores' for x in C.findings(C.utilization([]), [], today=TODAY)))
check('but not to someone with no revolving credit at all',
      not any(x['key'] == 'no_scores' for x in
              C.findings(C.utilization([]), [], today=TODAY, has_revolving=False)))
check('missing limits are reported',
      any(x['key'] == 'missing_limits' for x in
          C.findings(C.utilization([card('Store', 400, 0)]), [], today=TODAY)))

print('\n--- ordering puts warnings above notes ---')
f5 = C.findings(C.utilization([card('Visa', 6000, 10000), card('Store', 400, 0)]),
                C.series([reading(date(2026, 5, 1), 745), reading(date(2026, 8, 1), 702)]),
                today=TODAY)
check('every warning comes before every note',
      [x['severity'] for x in f5] == sorted([x['severity'] for x in f5],
                                            key=lambda s: {'warning': 0, 'note': 1}[s]),
      [(x['key'], x['severity']) for x in f5])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for x in fails:
        print('  - ' + x)
    sys.exit(1)
print('ALL CREDIT CHECKS PASSED')
