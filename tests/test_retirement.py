"""Retirement deferrals: percentage entry, the Roth/traditional split, and employer match.

The load-bearing assertion is that Roth does NOT reduce taxable wages. Treating a 6%
deferral as fully pre-tax when half of it is Roth understates the tax bill by real money.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='ret401_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'r.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
SALARY = 150000.0


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


def set_profile(**kw):
    with app.app_context():
        p = A.TaxProfile.query.filter_by(user_id=1).first()
        for k, v in kw.items():
            setattr(p, k, v)
        db.session.commit()


def est():
    with app.app_context():
        return A._income_tax_estimate(1)


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    db.session.add(A.User(id=1, google_id='g1', email='r@x.com', name='R', role='admin',
                          privacy_consent_at=now, privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.IncomeSource(user_id=1, name='Salary', type='salary',
                                  annual_salary=SALARY, pay_frequency='biweekly',
                                  tax_form='W2', active=True))
    db.session.add(A.TaxProfile(user_id=1, filing_status='mfj',
                                pretax_retirement_mode='amount'))
    db.session.commit()

c = client_for(1)

print('\n--- the reported setup: 6% split 3 traditional / 3 Roth ---')
set_profile(pretax_retirement_mode='percent', pretax_retirement_pct=3,
            roth_retirement_pct=3, employer_match_rate_pct=100,
            employer_match_limit_pct=6)
e = est()
check('traditional resolves to 3% of salary', e['pretax_retirement'] == 4500.0, e['pretax_retirement'])
check('Roth resolves to 3% of salary', e['roth_retirement'] == 4500.0, e['roth_retirement'])
check('ONLY traditional counts as a pre-tax deduction',
      e['pretax_deductions'] == 4500.0, e['pretax_deductions'])
check('taxable income = salary - traditional - MFJ standard deduction',
      e['taxable_income'] == SALARY - 4500 - 30000, e['taxable_income'])
check('total deferral reported as 6%', e['total_deferral_pct'] == 6.0, e['total_deferral_pct'])
check('basis is spelled out for the reader', '3% traditional' in e['retirement_basis']
      and 'Roth' in e['retirement_basis'], e['retirement_basis'])

print('\n--- treating Roth as pre-tax would have been wrong by real money ---')
set_profile(pretax_retirement_pct=6, roth_retirement_pct=0)
all_trad = est()
check('deducting all 6% lowers taxable by another 4500',
      all_trad['taxable_income'] == e['taxable_income'] - 4500, all_trad['taxable_income'])
check('and understates the tax owed',
      all_trad['total_federal_tax'] < e['total_federal_tax'],
      (all_trad['total_federal_tax'], e['total_federal_tax']))
print('     Roth counted correctly : taxable %s, federal tax %s' % (
    A._money(e['taxable_income']), A._money(e['total_federal_tax'])))
print('     Roth counted as pre-tax: taxable %s, federal tax %s  <- the bug avoided' % (
    A._money(all_trad['taxable_income']), A._money(all_trad['total_federal_tax'])))
set_profile(pretax_retirement_pct=3, roth_retirement_pct=3)

print('\n--- employer match ---')
e = est()
check('100% match up to 6% on a 6% deferral = 9000', e['employer_match'] == 9000.0, e['employer_match'])
check('nothing unclaimed at the cap', e['unclaimed_match'] == 0.0, e['unclaimed_match'])
check('match does NOT change taxable income — it was never in wages',
      e['taxable_income'] == SALARY - 4500 - 30000, e['taxable_income'])

set_profile(pretax_retirement_pct=1, roth_retirement_pct=1)
e2 = est()
check('deferring 2% collects only a third of the match', e2['employer_match'] == 3000.0, e2['employer_match'])
check('and reports the shortfall', e2['unclaimed_match'] == 6000.0, e2['unclaimed_match'])
r = c.get('/api/finance/overview')
obs = {o['key']: o for o in r.get_json()['observations']}
check('overview flags the unclaimed match as a warning',
      obs.get('unclaimed_match', {}).get('severity') == 'warning', list(obs))
check('and names the dollar figure', '$6,000' in (obs.get('unclaimed_match') or {}).get('detail', ''),
      (obs.get('unclaimed_match') or {}).get('detail'))

print('\n--- a 50% match is half as valuable ---')
set_profile(pretax_retirement_pct=3, roth_retirement_pct=3, employer_match_rate_pct=50)
check('50% on the first 6% = 4500', est()['employer_match'] == 4500.0, est()['employer_match'])
set_profile(employer_match_rate_pct=100)

print('\n--- the IRS elective limit covers traditional + Roth together ---')
set_profile(pretax_retirement_pct=90, roth_retirement_pct=0)
e3 = est()
check('an absurd deferral is capped, not deducted in full',
      e3['pretax_retirement'] == float(A._401K_ELECTIVE_LIMIT), e3['pretax_retirement'])
check('and the cap is reported', e3['retirement_capped'] is True, e3)
set_profile(pretax_retirement_pct=10, roth_retirement_pct=10)
e4 = est()
check('Roth consumes the allowance first, traditional gets the remainder',
      round(e4['pretax_retirement'] + e4['roth_retirement'], 2) <= A._401K_ELECTIVE_LIMIT + 0.01,
      (e4['pretax_retirement'], e4['roth_retirement']))

print('\n--- dollar mode still works ---')
set_profile(pretax_retirement_mode='amount', pretax_retirement_annual=12000,
            roth_retirement_annual=3000, pretax_retirement_pct=0, roth_retirement_pct=0)
e5 = est()
check('fixed amounts used verbatim', e5['pretax_retirement'] == 12000.0 and
      e5['roth_retirement'] == 3000.0, (e5['pretax_retirement'], e5['roth_retirement']))
check('deferral percent derived from wages for the match',
      e5['total_deferral_pct'] == 10.0, e5['total_deferral_pct'])

print('\n--- round-trips through the API ---')
r = c.put('/api/finance/tax-profile', json={
    'pretax_retirement_mode': 'percent', 'pretax_retirement_pct': 3,
    'roth_retirement_pct': 3, 'employer_match_rate_pct': 100,
    'employer_match_limit_pct': 6})
p = r.get_json()['profile']
check('mode saved', p['pretax_retirement_mode'] == 'percent', p)
check('roth percent saved', p['roth_retirement_pct'] == 3.0, p)
check('match saved', p['employer_match_rate_pct'] == 100.0 and
      p['employer_match_limit_pct'] == 6.0, p)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL RETIREMENT CHECKS PASSED')
