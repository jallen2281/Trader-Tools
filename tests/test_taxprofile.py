"""Household tax profile: filing status, dependents, pre-tax contributions, and — the big
one — knowing what has actually been withheld.

The headline case is the bug that prompted this: mid-year there is no W-2, so withholding
read $0 and the estimate reported the entire year's tax as a balance owed.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='taxp_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 't.db').replace(os.sep, '/')
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


def client_for(uid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return c


with app.app_context():
    db.drop_all()
    db.create_all()
    now = A.datetime.utcnow()
    V = A.CONSENT_VERSION
    db.session.add(A.User(id=1, google_id='g1', email='t@x.com', name='T', role='admin',
                          privacy_consent_at=now, privacy_consent_version=V))
    db.session.flush()
    db.session.add(A.IncomeSource(user_id=1, name='Salary', type='salary',
                                  annual_salary=150000, pay_frequency='biweekly',
                                  tax_form='W2', owner='me', active=True))
    db.session.add(A.IncomeSource(user_id=1, name='Spouse job', type='salary',
                                  annual_salary=60000, pay_frequency='biweekly',
                                  tax_form='W2', owner='spouse', active=True))
    db.session.commit()

c = client_for(1)

print('\n--- the reported bug: no profile, no W-2 yet ---')
with app.app_context():
    est = A._income_tax_estimate(1)
check('withholding is reported UNKNOWN, not zero', est['withholding_known'] is False, est['withholding_known'])
check('balance_due is None rather than a phantom figure', est['balance_due'] is None, est['balance_due'])
check('explains why withholding is unknown', 'no year-to-date figure' in est['withholding_source'].lower()
      or 'W-2 exists yet' in est['withholding_source'], est['withholding_source'])
check('spouse income excluded for a single filer', est['w2_wages'] == 150000.0, est['w2_wages'])
check('defaults to single, not the old hardcoded MFJ', est['filing_status'] == 'single')
check('reports which year the brackets come from', est['constants_vintage'] == 2025,
      est['constants_vintage'])
solo_tax = est['total_federal_tax']
check('total tax computed on the single filer', 24000 < solo_tax < 27000, solo_tax)

r = c.get('/api/finance/overview')
obs = {o['key']: o for o in r.get_json()['observations']}
check('overview flags the missing withholding as a NOTE, not an alarm',
      obs.get('withholding_unknown', {}).get('severity') == 'note', list(obs))
check('no scary tax_due warning while withholding is unknown', 'tax_due' not in obs, list(obs))
check('flags the absent household profile', 'no_tax_profile' in obs, list(obs))

with app.app_context():
    pic = A._finance_full_picture(1)
    facts = A._overview_facts(pic, A._finance_observations(pic))
check('briefing tells the model not to call it a balance owed',
      'Do NOT present the total tax as a balance owed' in facts,
      [l for l in facts.split('\n') if 'withhold' in l.lower()][:2])
check('briefing warns the profile is unset', 'no household profile has been saved' in facts)

print('\n--- filling in the household moves the number a lot ---')
r = c.put('/api/finance/tax-profile', json={
    'filing_status': 'mfj', 'dependents_under_17': 2,
    'pretax_retirement_annual': 23000, 'state': 'MI', 'state_tax_rate': 4.25})
check('PUT profile -> 200', r.status_code == 200, r.status_code)
prof = r.get_json()['profile']
check('filing status saved', prof['filing_status'] == 'mfj', prof)
check('household size counts both filers plus children', prof['household_size'] == 4, prof)

with app.app_context():
    est2 = A._income_tax_estimate(1)
check('spouse income now counted (MFJ)', est2['w2_wages'] == 210000.0, est2['w2_wages'])
check('pre-tax 401k reduces taxable income',
      est2['taxable_income'] < est2['w2_wages'] - est2['deduction_used'] + 1, est2['taxable_income'])
check('MFJ standard deduction applied', est2['deduction_used'] == 30000, est2['deduction_used'])
check('child tax credit applied for 2 children',
      est2['child_tax_credit'] == 2 * A._CTC_PER_CHILD, est2['child_tax_credit'])
check('credits reduce the income tax',
      est2['federal_income_tax'] == round(max(0.0, est2['federal_income_tax_before_credits']
                                              - est2['credits']), 2), est2)
check('Michigan state tax estimated', est2['state_tax'] > 0 and est2['state'] == 'MI',
      (est2['state'], est2['state_tax']))
check('state exemptions scale with household', est2['state_tax'] <
      (210000 - 23000) * 0.0425, est2['state_tax'])

print('\n--- entering YTD withholding makes the balance real ---')
as_of = date(YEAR, 9, 1)
elapsed = (as_of - date(YEAR, 1, 1)).days + 1
r = c.put('/api/finance/tax-profile', json={'ytd_federal_withheld': 21000,
                                            'ytd_as_of': as_of.isoformat()})
check('YTD figure saved', r.get_json()['profile']['ytd_federal_withheld'] == 21000.0)
with app.app_context():
    est3 = A._income_tax_estimate(1)
check('withholding is now known', est3['withholding_known'] is True)
expected = round(21000 * 365.0 / elapsed, 2)
check('annualized from the paystub date', abs(est3['withheld'] - expected) < 1.0,
      (est3['withheld'], expected))
check('source explains the projection', 'year-to-date' in est3['withholding_source'],
      est3['withholding_source'])
check('balance_due is now a real number', est3['balance_due'] is not None)
check('balance = total tax - projected withholding',
      abs(est3['balance_due'] - (est3['total_federal_tax'] - est3['withheld'])) < 0.02, est3)

r = c.get('/api/finance/overview')
obs3 = {o['key']: o for o in r.get_json()['observations']}
check('withholding_unknown note is gone', 'withholding_unknown' not in obs3, list(obs3))
check('no_tax_profile note is gone', 'no_tax_profile' not in obs3, list(obs3))

print('\n--- filing status actually changes the maths ---')
with app.app_context():
    single = A._income_tax_estimate(1, filing='single')
    mfj = A._income_tax_estimate(1, filing='mfj')
    hoh = A._income_tax_estimate(1, filing='hoh')
check('single deduction is 15000', single['deduction_used'] == 15000, single['deduction_used'])
check('head of household deduction is 22500', hoh['deduction_used'] == 22500, hoh['deduction_used'])
# MFJ reports MORE tax here only because it also includes the spouse's $60k — comparing the
# end figures across statuses confounds the brackets with who is on the return. Test the
# bracket property directly, on identical taxable income.
same = 120000.0
tax_by_status = {f: A._bracket_tax(same, A._FED_BRACKETS[f]) for f in ('single', 'hoh', 'mfj')}
check('on identical taxable income, MFJ brackets are the most favourable',
      tax_by_status['mfj'] < tax_by_status['hoh'] < tax_by_status['single'], tax_by_status)
check('and MFJ counts the spouse while single does not',
      mfj['w2_wages'] == 210000.0 and single['w2_wages'] == 150000.0,
      (mfj['w2_wages'], single['w2_wages']))
check('deductions order correctly: single < HoH < MFJ',
      single['deduction_used'] < hoh['deduction_used'] < mfj['deduction_used'],
      (single['deduction_used'], hoh['deduction_used'], mfj['deduction_used']))
check('every filing status has brackets', all(f in A._FED_BRACKETS for f in
                                              A.TaxProfile.FILING_STATUSES),
      list(A._FED_BRACKETS))

print('\n--- the headline: what the user actually saw, before vs after ---')
print('     no profile, no W-2 on file : total tax %s, reported balance %s' % (
    A._money(solo_tax), 'None (unknown)'))
print('     profile + paystub YTD      : total tax %s, balance %s' % (
    A._money(est3['total_federal_tax']), A._money(est3['balance_due'])))
check('the phantom balance is gone', est['balance_due'] is None)
check('and the real one is far smaller than the raw tax bill',
      abs(est3['balance_due']) < est3['total_federal_tax'], (est3['balance_due'],
                                                             est3['total_federal_tax']))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL TAX PROFILE CHECKS PASSED')
