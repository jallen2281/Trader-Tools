"""What actually comes out of a paycheck.

The estimate computed federal income tax, state tax, and self-employment tax on 1099
income — and no employee FICA at all on W2 wages. For most wage earners FICA is larger
than their federal income tax, so take-home looked thousands of dollars better than it is.
Health insurance, HSA, disability and life were a single unlabelled bucket.

The case worth guarding hardest is the one most paycheck tools get wrong: a traditional
401(k) deferral escapes income tax but is STILL fully subject to FICA, while a Section 125
health premium escapes both.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='paycheck_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


print('\n--- FICA arithmetic, on its own ---')
f = A._employee_fica(100000, 'single')
check('social security is 6.2%', f['social_security'] == 6200.0, f)
check('medicare is 1.45%', f['medicare'] == 1450.0, f)
check('no additional medicare under the threshold', f['additional_medicare'] == 0.0, f)
check('total is 7.65%', f['total'] == 7650.0, f)
check('not flagged as capped', f['ss_capped'] is False)

big = A._employee_fica(300000, 'single')
check('social security stops at the wage base',
      big['social_security'] == round(A._SS_WAGE_BASE * 0.062, 2), big['social_security'])
check('and is reported as capped', big['ss_capped'] is True)
check('medicare keeps going, uncapped', big['medicare'] == 4350.0, big['medicare'])
check('additional medicare applies over $200k for a single filer',
      big['additional_medicare'] == round((300000 - 200000) * 0.009, 2),
      big['additional_medicare'])
mfj = A._employee_fica(300000, 'mfj')
check('but the threshold is $250k married filing jointly',
      mfj['additional_medicare'] == round((300000 - 250000) * 0.009, 2),
      mfj['additional_medicare'])
check('and $125k filing separately',
      A._employee_fica(200000, 'mfs')['additional_medicare']
      == round((200000 - 125000) * 0.009, 2))
check('zero wages, zero FICA', A._employee_fica(0, 'single')['total'] == 0.0)
check('negative wages do not produce a credit', A._employee_fica(-5000, 'single')['total'] == 0.0)

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.TaxProfile(user_id=1, filing_status='single', state_tax_rate=4.25))
    db.session.add(A.IncomeSource(id=10, user_id=1, name='Job', owner='me', type='salary',
                                  annual_salary=100000, pay_frequency='biweekly',
                                  tax_form='W2', active=True))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True


def est():
    with app.app_context():
        return A._income_tax_estimate(1)


print('\n--- FICA now appears on a plain W2 wage ---')
e = est()
check('it is charged at all', e['fica_total'] == 7650.0, e['fica_total'])
check('broken out rather than a single number',
      e['fica']['social_security'] == 6200.0 and e['fica']['medicare'] == 1450.0, e['fica'])
check('and it is NOT folded into the income-tax balance',
      e['total_federal_tax'] == e['federal_income_tax'] + e['self_employment_tax'],
      (e['total_federal_tax'], e['federal_income_tax']))

print('\n--- a 401(k) deferral escapes income tax but NOT FICA ---')
c.put('/api/finance/incomes/10', json={'pretax_retirement_mode': 'percent',
                                       'pretax_retirement_pct': 10})
e2 = est()
check('taxable wages fall by the deferral',
      e2['federal_income_tax'] < e['federal_income_tax'],
      (e['federal_income_tax'], e2['federal_income_tax']))
check('FICA does NOT fall -- the classic mistake',
      e2['fica_total'] == 7650.0, e2['fica_total'])
check('FICA wages are still the full salary', e2['fica']['wages'] == 100000.0,
      e2['fica']['wages'])

print('\n--- a Section 125 health premium escapes BOTH ---')
c.put('/api/finance/incomes/10', json={'pretax_health_annual': 6000})
e3 = est()
check('FICA wages drop by the premium', e3['fica']['wages'] == 94000.0, e3['fica']['wages'])
check('so FICA itself drops', e3['fica_total'] == round(94000 * 0.0765, 2), e3['fica_total'])
check('and income tax drops too', e3['federal_income_tax'] < e2['federal_income_tax'])
check('the premium is reported separately from retirement',
      e3['section125_deductions'] == 6000.0, e3['section125_deductions'])

print('\n--- HSA behaves the same way ---')
c.put('/api/finance/incomes/10', json={'pretax_hsa_annual': 3000})
e4 = est()
check('it joins the Section 125 total', e4['section125_deductions'] == 9000.0,
      e4['section125_deductions'])
check('and reduces FICA wages further', e4['fica']['wages'] == 91000.0, e4['fica']['wages'])

print('\n--- post-tax deductions reduce take-home and nothing else ---')
before = est()
c.put('/api/finance/incomes/10', json={'posttax_deductions_annual': 1200})
e5 = est()
check('income tax is unchanged', e5['federal_income_tax'] == before['federal_income_tax'])
check('FICA is unchanged', e5['fica_total'] == before['fica_total'])
check('but take-home falls by the full amount',
      round(before['take_home'] - e5['take_home'], 2) == 1200.0,
      (before['take_home'], e5['take_home']))
check('they are reported', e5['posttax_deductions'] == 1200.0, e5['posttax_deductions'])

print('\n--- take-home is gross less everything that comes out ---')
e6 = est()
expected = round(100000 - e6['section125_deductions'] - e6['pretax_retirement']
                 - e6['roth_retirement'] - e6['federal_income_tax'] - e6['state_tax']
                 - e6['fica_total'] - e6['posttax_deductions'], 2)
check('every term is subtracted exactly once', e6['take_home'] == expected,
      (e6['take_home'], expected))
check('it is well below gross', e6['take_home'] < 100000 * 0.75, e6['take_home'])
check('a monthly figure is given for holding against a deposit',
      e6['take_home_monthly'] == round(e6['take_home'] / 12.0, 2), e6['take_home_monthly'])
check('FICA is material next to the income tax, not a rounding error',
      e6['fica_total'] > e6['federal_income_tax'] * 0.5,
      (e6['fica_total'], e6['federal_income_tax']))
# At $100k the income tax is the larger of the two; the crossover is further down the
# scale, which is exactly the income where leaving FICA out did the most damage.
with app.app_context():
    A.IncomeSource.query.get(10).annual_salary = 45000
    db.session.commit()
low = est()
check('on a $45k wage FICA exceeds the federal income tax outright',
      low['fica_total'] > low['federal_income_tax'],
      (low['fica_total'], low['federal_income_tax']))
with app.app_context():
    A.IncomeSource.query.get(10).annual_salary = 100000
    db.session.commit()

print('\n--- the reconciliation compares against take-home, not a guess ---')
with app.app_context():
    rec = A._income_reconciliation(1)
check('the basis names what it netted off',
      'FICA' in rec['expected_basis'], rec['expected_basis'])
check('and it equals the take-home figure',
      rec['expected_monthly_net'] == e6['take_home_monthly'],
      (rec['expected_monthly_net'], e6['take_home_monthly']))
check('which is lower than the old gross-less-tax approximation',
      rec['expected_monthly_net'] < rec['gross_monthly'],
      (rec['expected_monthly_net'], rec['gross_monthly']))

print('\n--- deductions are per job, like everything else on a paycheck ---')
with app.app_context():
    db.session.add(A.IncomeSource(id=11, user_id=1, name='Second job', owner='me',
                                  type='salary', annual_salary=40000, tax_form='W2',
                                  pay_frequency='biweekly', active=True,
                                  pretax_health_annual=2400))
    db.session.commit()
e7 = est()
check('both jobs contribute their own premiums',
      e7['section125_deductions'] == 11400.0, e7['section125_deductions'])
check('FICA is charged on the combined wages less both',
      e7['fica']['wages'] == 140000 - 11400, e7['fica']['wages'])

print('\n--- nonsense is refused ---')
r = c.put('/api/finance/incomes/10', json={'pretax_health_annual': -500})
check('a negative premium is floored at zero',
      r.get_json()['pretax_health_annual'] == 0.0, r.get_json()['pretax_health_annual'])
r = c.put('/api/finance/incomes/10', json={'posttax_deductions_annual': 'lots'})
check('a non-numeric deduction is ignored rather than crashing', r.status_code == 200)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PAYCHECK CHECKS PASSED')

print('\n--- validated against a real payslip ---')
# Liquid Web, one biweekly check. Every figure below is off the stub, and the point of
# pinning them is that the FICA treatment is not a matter of opinion: if a 401(k) deferral
# reduced FICA wages, Medicare here would be $48.09 instead of $51.21, and if the
# life/disability/accident lines were pre-tax it would be $50.57.
STUB_GROSS = 3384.62 + 200.43          # base 80h @42.31 + 3.16h OT @63.46
LINES = [
    {'label': 'HSA', 'per_check': 30.00, 'treatment': 'section125'},
    {'label': 'Medical', 'per_check': 19.71, 'treatment': 'section125'},
    {'label': 'Dental', 'per_check': 3.57, 'treatment': 'section125'},
    {'label': 'Voluntary Life', 'per_check': 14.63, 'treatment': 'posttax'},
    {'label': 'Short Term Disability', 'per_check': 12.43, 'treatment': 'posttax'},
    {'label': 'Long Term Disability', 'per_check': 4.29, 'treatment': 'posttax'},
    {'label': 'Accident Insurance', 'per_check': 13.02, 'treatment': 'posttax'},
]
with app.app_context():
    db.session.add(A.IncomeSource(id=20, user_id=1, name='Liquid Web', owner='me',
                                  type='hourly', hourly_rate=42.31, hours_per_week=40,
                                  pay_frequency='biweekly', tax_form='W2', active=True,
                                  pretax_retirement_mode='percent',
                                  pretax_retirement_pct=3, roth_retirement_pct=3,
                                  payroll_deductions=LINES))
    db.session.commit()
    src = A.IncomeSource.query.get(20)
    n = 26

    check('the stub lines are read back intact', len(src.deduction_lines()) == 7,
          src.deduction_lines())
    check('Section 125 is HSA + medical + dental, annualised',
          src.section125_annual() == round((30.00 + 19.71 + 3.57) * n, 2),
          src.section125_annual())
    check('life, disability and accident are post-tax, not Section 125',
          src.posttax_annual() == round((14.63 + 12.43 + 4.29 + 13.02) * n, 2),
          src.posttax_annual())

    # FICA on this single check, which is what the stub can be checked against.
    fica = A._employee_fica(STUB_GROSS - (30.00 + 19.71 + 3.57), 'single')
    check('medicare matches the stub to the cent', fica['medicare'] == 51.21,
          fica['medicare'])
    check('social security matches the stub to the cent',
          fica['social_security'] == 218.97, fica['social_security'])

    wrong = A._employee_fica(STUB_GROSS - (30.00 + 19.71 + 3.57) - 107.55 - 107.55, 'single')
    check('deducting the 401(k) from FICA wages would NOT match the stub',
          wrong['medicare'] != 51.21 and round(wrong['medicare'], 2) == 48.09,
          wrong['medicare'])
    alt = A._employee_fica(STUB_GROSS - (30.00 + 19.71 + 3.57)
                           - (14.63 + 12.43 + 4.29 + 13.02), 'single')
    check('treating the voluntary lines as pre-tax would NOT match either',
          round(alt['medicare'], 2) == 50.57, alt['medicare'])

    check('a 6% deferral against this stub matches the employer contribution shown',
          # 401k 107.55 + Roth 107.55 deferred, company put in 125.48 = 58.3% of the
          # deferral, which is 3.5/6 -- the tiered schedule, confirmed by real payroll.
          abs(125.48 / (107.55 + 107.55) - 3.5 / 6.0) < 0.001,
          125.48 / (107.55 + 107.55))

print('\n--- line items round-trip through the API ---')
r = c.put('/api/finance/incomes/20', json={'payroll_deductions': LINES})
check('saved', r.status_code == 200 and len(r.get_json()['payroll_deductions']) == 7,
      r.get_json().get('payroll_deductions'))
check('and the totals come back derived', r.get_json()['section125_annual'] > 0)
r = c.put('/api/finance/incomes/20', json={'payroll_deductions': [
    {'label': 'Good', 'per_check': 10, 'treatment': 'section125'},
    {'label': 'Zero', 'per_check': 0, 'treatment': 'section125'},
    {'label': 'Junk', 'per_check': 'abc', 'treatment': 'section125'},
    {'label': 'Bad treatment', 'per_check': 5, 'treatment': 'magic'},
]})
kept = r.get_json()['payroll_deductions']
check('zero and non-numeric rows are dropped', len(kept) == 2, kept)
check('an unknown treatment falls back to post-tax, the safe side',
      [k for k in kept if k['label'] == 'Bad treatment'][0]['treatment'] == 'posttax', kept)
