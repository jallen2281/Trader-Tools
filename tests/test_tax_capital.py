"""Realized capital gains and losses reach the tax estimate.

The estimate saw wages and 1099 income and nothing else. A household with $7,049 of
realized losses on the ledger was still told it owed $2,639 at filing, computed as though
no sale had ever happened -- while the Tax Center, on another page, already had the lot
matching to know better.

The rules that matter: short- and long-term net against each other first; a net loss only
comes off ordinary income up to $3,000 ($1,500 MFS) and the rest carries forward; a net
gain keeps its character, with long-term taxed at preferential rates stacked on top of
ordinary income. And a sale must not move take-home pay or the cash-flow ledger.
"""
import os
import sys
import tempfile
from datetime import date, datetime

TMP = tempfile.mkdtemp(prefix='taxcap_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'c.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
YEAR = date.today().year


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


T = A._capital_gain_treatment
print('\n--- netting, as Schedule D does it ---')
r = T(-500, -1000, 'mfj')
check('a loss under the limit is deducted in full', r['loss_deducted'] == 1500.0, r)
check('with nothing carried forward', r['loss_carryforward'] == 0.0, r)
check('and it lowers AGI', r['agi_adjustment'] == -1500.0, r)

r = T(-12.22, -7037.01, 'mfj')
check('a loss over the limit is capped at $3,000', r['loss_deducted'] == 3000.0, r)
check('the rest carries forward', r['loss_carryforward'] == 4049.23, r)

r = T(-5000, 0, 'mfs')
check('married filing separately gets half the limit', r['loss_deducted'] == 1500.0, r)
check('and carries forward the other 3,500', r['loss_carryforward'] == 3500.0, r)

r = T(1000, 5000, 'mfj')
check('both gains keep their own character',
      (r['ordinary'], r['preferential']) == (1000.0, 5000.0), r)
r = T(1000, -400, 'mfj')
check('a long-term loss eats into short-term gain first',
      (r['ordinary'], r['preferential']) == (600.0, 0.0), r)
r = T(-400, 1000, 'mfj')
check('a short-term loss eats into long-term gain',
      (r['ordinary'], r['preferential']) == (0.0, 600.0), r)
r = T(500, -500, 'mfj')
check('exactly break-even changes nothing',
      (r['agi_adjustment'], r['loss_deducted']) == (0.0, 0.0), r)

P = A._preferential_tax
print('\n--- long-term gains stack on top of ordinary income ---')
check('straddling the 0% band: 6,700 free, 3,300 at 15%',
      P(90000, 10000, 'mfj') == 495.0, P(90000, 10000, 'mfj'))
check('already past the 0% band: all at 15%', P(150000, 10000, 'mfj') == 1500.0,
      P(150000, 10000, 'mfj'))
check('a low-income single filer pays nothing', P(20000, 5000, 'single') == 0.0,
      P(20000, 5000, 'single'))
check('the top band is 20%', P(600050, 10000, 'mfj') == 2000.0, P(600050, 10000, 'mfj'))

# ---------------------------------------------------------------- against a real ledger
with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    for uid in (1, 2, 3):
        db.session.add(A.User(id=uid, google_id='g%d' % uid, email='u%d@x.com' % uid,
                              name='U%d' % uid, role='admin', privacy_consent_at=now,
                              privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    for uid in (1, 2, 3):
        db.session.add(A.IncomeSource(user_id=uid, name='Salary', type='salary',
                                      annual_salary=150000, pay_frequency='biweekly',
                                      tax_form='W2', owner='me', active=True))
        db.session.add(A.TaxProfile(user_id=uid, filing_status='mfj',
                                    ytd_federal_withheld=6000, ytd_as_of=date(YEAR, 7, 31)))
    db.session.commit()


def acct(uid, name):
    a = A.PortfolioAccount(user_id=uid, name=name)
    db.session.add(a)
    db.session.flush()
    return a.id


def trade(uid, aid, sym, side, qty, px, when):
    db.session.add(A.Transaction(user_id=uid, account_id=aid, symbol=sym, asset_type='stock',
                                 transaction_type=side, quantity=qty, price=px,
                                 transaction_date=datetime.combine(when, datetime.min.time())))


with app.app_context():
    base = A._income_tax_estimate(1)
print('\n--- before any sales ---')
check('no sales, no capital section', base['capital_gains'] is None, base['capital_gains'])
check('and no effect on the bill', base['capital_gains_tax_effect'] == 0.0)
check('withholding is known, so the balance is real', base['withholding_known'] is True,
      base['withholding_source'])

print('\n--- the reported case: SNDL sold at a long-term loss, FIG at a short-term one ---')
with app.app_context():
    sofi = acct(1, 'Sofi')
    trade(1, sofi, 'SNDL', 'buy', 3000, 3.15, date(2022, 8, 29))
    trade(1, sofi, 'SNDL', 'sell', 3000, 1.34, date(YEAR, 6, 25))
    trade(1, sofi, 'FIG', 'buy', 1, 33.00, date(YEAR - 1, 7, 31))
    trade(1, sofi, 'FIG', 'sell', 1, 16.92, date(YEAR, 6, 25))
    db.session.commit()
    est = A._income_tax_estimate(1)
cg = est['capital_gains']
check('the sales are found', cg is not None and cg['disposal_count'] == 2, cg)
check('held since 2022 -> long-term', cg['long_term'] == -5430.0, cg)
check('held under a year -> short-term', cg['short_term'] == -16.08, cg)
check('$3,000 comes off income', cg['loss_deducted'] == 3000.0, cg)
check('the rest carries forward', cg['loss_carryforward'] == 2446.08, cg)
# $150k MFJ less the $30k standard deduction is $120k taxable, inside the 22% band either
# side of the deduction -- so the effect is exactly 22% of $3,000.
check('the bill drops by 22% of $3,000', est['capital_gains_tax_effect'] == -660.0,
      est['capital_gains_tax_effect'])
check('total federal tax reflects it',
      est['total_federal_tax'] == round(base['total_federal_tax'] - 660, 2),
      (base['total_federal_tax'], est['total_federal_tax']))
check('and so does the balance due',
      est['balance_due'] == round(base['balance_due'] - 660, 2),
      (base['balance_due'], est['balance_due']))
check('the state bill moves by the same capped amount',
      est['state_capital_effect'] == round(-3000 * float(est['state_tax_rate'] or 0) / 100, 2),
      est['state_capital_effect'])

print('\n--- but a stock sale is not a pay cut or a raise ---')
check('wage income tax is unchanged', est['federal_income_tax'] == base['federal_income_tax'])
check('taxable wages are unchanged', est['taxable_income'] == base['taxable_income'])
check('take-home is unchanged', est['take_home'] == base['take_home'])
check('state tax on wages is unchanged', est['state_tax'] == base['state_tax'])

print('\n--- the overview says why the number moved ---')
c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True
obs = {o['key']: o for o in c.get('/api/finance/overview').get_json()['observations']}
detail = obs.get('tax_due', {}).get('detail', '')
check('the owed warning mentions the losses', 'realized capital losses' in detail, detail)
check('and what carries forward', 'carries forward' in detail, detail)

r = c.get('/tax')
check('the tax page renders the capital gains tile',
      r.status_code == 200 and 'capital_gains_tax_effect' in r.get_data(as_text=True), r.status_code)

print('\n--- what must not count ---')
with app.app_context():
    k = acct(1, 'Transamerica 401k')
    trade(1, k, 'VTI', 'buy', 100, 300, date(YEAR - 3, 1, 5))
    trade(1, k, 'VTI', 'sell', 100, 200, date(YEAR, 3, 1))
    trade(1, sofi, 'OLD', 'buy', 10, 100, date(YEAR - 3, 1, 5))
    trade(1, sofi, 'OLD', 'sell', 10, 10, date(YEAR - 1, 3, 1))
    db.session.commit()
    est2 = A._income_tax_estimate(1)
check('a 401(k) sale is not a taxable event',
      est2['capital_gains']['long_term'] == -5430.0, est2['capital_gains'])
check("last year's sale is not this year's", est2['capital_gains']['disposal_count'] == 2,
      est2['capital_gains'])

print('\n--- gains cost money, at the right rate ---')
with app.app_context():
    a2 = acct(2, 'Brokerage')
    trade(2, a2, 'AMZN', 'buy', 100, 100, date(YEAR - 2, 1, 5))
    trade(2, a2, 'AMZN', 'sell', 100, 200, date(YEAR, 5, 1))
    a3 = acct(3, 'Brokerage')
    trade(3, a3, 'PLTR', 'buy', 10, 100, date(YEAR, 1, 5))
    trade(3, a3, 'PLTR', 'sell', 10, 200, date(YEAR, 5, 1))
    db.session.commit()
    lt_est = A._income_tax_estimate(2)
    st_est = A._income_tax_estimate(3)
check('a $10,000 long-term gain above the 0% band costs 15%',
      lt_est['capital_gains_tax_effect'] == 1500.0, lt_est['capital_gains_tax_effect'])
check('a $1,000 short-term gain costs the ordinary 22%',
      st_est['capital_gains_tax_effect'] == 220.0, st_est['capital_gains_tax_effect'])
check('neither touches take-home', lt_est['take_home'] == base['take_home']
      and st_est['take_home'] == base['take_home'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CAPITAL-GAINS TAX CHECKS PASSED')
