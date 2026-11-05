"""A payee the matcher does not know becomes 'other', and 'other' is where money hides.

On the real household book 'other' was $15,503.72 -- the second-largest category of all,
behind housing -- and most of it was not miscellaneous at all:

    $6,207.76  UWM / UNITEDWHOLESALE    the mortgage, under the servicer's name
    $3,826.86  interest, three wordings  a $10,048.95/yr rate, invisible
    $2,132.11  ASU tuition + fees        a recurring $515/mo with nowhere to go
    $1,270.00  SoFi Securities, Kraken   money invested, counted as spent
       $29.00  LATE FEE                  the cost of carrying the debt

None of it was a mystery; the keyword list had simply never been told. The mortgage rule
looked for the word 'mortgage' and the lender is called UWM, so four identical $3,103.88
payments landed in 'other' and only the two that were hand-corrected ever read as housing.

So this file pins the payees that actually occur, and -- more importantly -- the ORDER
traps, because the rules are first-match-wins and a new category placed carelessly steals
rows from an older one. 'student loan' is debt service, not education.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='catrules_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 't.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def guess(desc, want):
    got = A._guess_spend_category(desc)
    check('%-40s -> %-14s' % (repr(desc)[:40], want), got == want, got)


print('\n--- the mortgage, under every name the bank writes it ---')
# Both spellings appear in one 139-day feed: the servicer renamed itself mid-stream.
for d in ('UWM', 'UNITEDWHOLESALE', 'UWM MORTGAGE PYMT', 'Unitedwholesale Mtg'):
    guess(d, 'housing')
guess('RENT PAYMENT', 'housing')          # the old generic rule still works

print('\n--- interest and fees are debt, not miscellany ---')
for d in ('Interest Charge on Purchases', 'INTEREST CHARGED TO STANDARD PURCH',
          'INTEREST CHARGE:PURCHASES', 'LATE FEE'):
    guess(d, 'debt')

print('\n--- investing is moving money, not spending it ---')
for d in ('SOFI SECURITIES', 'Sofi Securities LLC', 'Kraken', 'KRAKEN.COM'):
    guess(d, 'transfer')
check('and the category it lands in is excluded from spending',
      'transfer' in A.NON_SPEND_CATEGORIES)

print('\n--- tuition has a category of its own ---')
check("'education' is a real household category", 'education' in A.HOUSEHOLD_CATEGORIES)
check('and is accepted on save', 'education' in A.BUDGET_CATEGORIES)
check('it is NOT excluded from spending -- tuition is a real cost',
      'education' not in A.NON_SPEND_CATEGORIES)
for d in ('ASU STUDENT ACCOUNTSTEMPE', 'NBS-ASU SERVICE FEE', 'FALL TUITION',
          'UNIV BURSAR OFFICE'):
    guess(d, 'education')

print('\n--- the order traps ---')
# Every one of these would be wrong if a rule were moved. They are the reason the
# education rule sits after debt and carries no bare 'student' or 'college'.
guess('STUDENT LOAN PAYMENT', 'debt')         # education must not claim debt service
guess('NELNET STUDENT LOAN', 'debt')
guess('COLLEGE STATION SHELL', 'transportation')   # a place name, not a school
guess('CASUAL DINING GRILL', 'other')         # 'asu' hides inside 'casual'
guess('ASURION TECH REPAIR', 'other')         # and inside 'Asurion'
# A card payment still beats everything, including the new interest words: the payment
# settles purchases already counted, while the interest is a new cost.
guess('AMEX EPAYMENT', 'transfer')
guess('PAYMENT TO CHASE CARD ENDING IN 4831', 'transfer')
check('and the dedicated card-payment check agrees',
      A._looks_like_card_payment('PAYMENT TO CHASE CARD ENDING IN 4831'))
check('while an interest charge is not a card payment',
      not A._looks_like_card_payment('Interest Charge on Purchases'))

print('\n--- an unknown payee still falls through to other, honestly ---')
for d in ('SP FLUENTPET 9483', 'BRIGHTON REC AREA', 'MUDFLAP'):
    guess(d, 'other')

print('\n--- every rule names a category that exists ---')
for cat, keys in A.SPEND_CATEGORY_RULES:
    check('rule %-16s targets a real category' % cat, cat in A.BUDGET_CATEGORIES, cat)
    check('rule %-16s has no empty keyword' % cat,
          all(k and k.strip() for k in keys), keys)

print('\n--- the UI offers what the server accepts ---')
# A category the server files rows into but the dropdown never lists is a row the user
# cannot re-file by hand, which is how 'other' grew in the first place.
import re  # noqa: E402
with open(os.path.join('templates', 'finances.html'), encoding='utf-8') as fh:
    html = fh.read()
m = re.search(r'const BUDGET_CATS = \[(.*?)\]', html)
check('the template declares BUDGET_CATS', bool(m))
if m:
    offered = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    # 'transfer' is deliberately absent: it is set by choosing a destination, not picked.
    missing = (set(A.HOUSEHOLD_CATEGORIES) - {'transfer'}) - offered
    check('every household category is offered in the dropdown', not missing, missing)
    check('and the dropdown invents none', not (offered - set(A.BUDGET_CATEGORIES)),
          offered - set(A.BUDGET_CATEGORIES))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CATEGORY RULE CHECKS PASSED')
