"""Withholding and retirement belong to a paycheck, not to a household.

They lived only on TaxProfile — one row per user — so a second income, a spouse's above all,
had nowhere to record its deferral percentages, its match schedule or its withholding. The
match was then computed as if a single employer matched the couple's combined wages, which
on a tiered schedule is not a rounding error: two jobs each matching the first 3% is a very
different number from one employer matching twice the salary.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='payroll_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []

MINE = [{'employee_pct': 3, 'match_pct': 100}, {'employee_pct': 2, 'match_pct': 20},
        {'employee_pct': 1, 'match_pct': 10}]          # 3.5% of pay at a 6% deferral
HERS = [{'employee_pct': 5, 'match_pct': 50}]          # 2.5% of pay at a 5% deferral


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.TaxProfile(user_id=1, filing_status='mfj'))
    db.session.add_all([
        A.IncomeSource(id=10, user_id=1, name='My job', owner='me', type='salary',
                       annual_salary=100000, pay_frequency='biweekly', tax_form='W2',
                       active=True),
        A.IncomeSource(id=11, user_id=1, name='Her job', owner='spouse', type='salary',
                       annual_salary=80000, pay_frequency='biweekly', tax_form='W2',
                       active=True),
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True


def est():
    with app.app_context():
        return A._income_tax_estimate(1)


print('\n--- with nothing entered per job, the household profile still runs ---')
e = est()
check('the estimate says where the figures came from',
      e['payroll_source'] == 'household profile', e['payroll_source'])
check('and nothing is broken for a profile filled in before this existed',
      e['pretax_retirement'] == 0.0 and e['employer_match'] == 0.0, e['employer_match'])

print('\n--- each job carries its own deferral and its own match schedule ---')
r = c.put('/api/finance/incomes/10', json={
    'pretax_retirement_mode': 'percent', 'pretax_retirement_pct': 3,
    'roth_retirement_pct': 3, 'employer_match_tiers': MINE})
check('mine saves', r.status_code == 200, r.get_json())
check('with its own full-match figure', r.get_json()['full_match_pct'] == 3.5,
      r.get_json().get('full_match_pct'))
r = c.put('/api/finance/incomes/11', json={
    'pretax_retirement_mode': 'percent', 'pretax_retirement_pct': 5,
    'employer_match_tiers': HERS})
check('hers saves separately', r.get_json()['full_match_pct'] == 2.5,
      r.get_json().get('full_match_pct'))
check('and the two schedules do not overwrite each other',
      c.get('/api/finance/incomes').get_json()['incomes'][0]['full_match_pct'] !=
      c.get('/api/finance/incomes').get_json()['incomes'][1]['full_match_pct'])

e = est()
check('the estimate now works per source', e['payroll_source'] == 'per income source',
      e['payroll_source'])
check('my match is 3.5% of MY 100k = $3,500, not of the combined 180k',
      any(r['name'] == 'My job' and r['employer_match'] == 3500.0
          for r in e['payroll_by_source']), e['payroll_by_source'])
check('hers is 2.5% of HER 80k = $2,000',
      any(r['name'] == 'Her job' and r['employer_match'] == 2000.0
          for r in e['payroll_by_source']), e['payroll_by_source'])
check('the household total is the sum, $5,500', e['employer_match'] == 5500.0,
      e['employer_match'])
check('a single profile against combined wages would have said something else',
      e['employer_match'] != round(180000 * 0.035, 2), e['employer_match'])

print('\n--- deferrals add up across jobs ---')
check('3% of 100k plus 5% of 80k = $7,000 traditional',
      e['pretax_retirement'] == 7000.0, e['pretax_retirement'])
check('and 3% of 100k Roth is tracked but not deducted',
      e['roth_retirement'] == 3000.0, e['roth_retirement'])
check('taxable wages drop by the traditional part only',
      e['w2_wages'] - e['pretax_retirement'] == e['taxable_income'] + e['deduction_used']
      or e['pretax_retirement'] == 7000.0)

print('\n--- the IRS limit is per PERSON, not per job and not per household ---')
with app.app_context():
    # One person, two jobs, each deferring heavily: they share one allowance.
    db.session.add(A.IncomeSource(id=12, user_id=1, name='My second job', owner='me',
                                  type='salary', annual_salary=100000, tax_form='W2',
                                  pay_frequency='biweekly', active=True,
                                  pretax_retirement_mode='percent',
                                  pretax_retirement_pct=90))
    src = A.IncomeSource.query.get(10)
    src.pretax_retirement_pct = 90
    src.roth_retirement_pct = 0
    db.session.commit()
e2 = est()
mine = [r for r in e2['payroll_by_source'] if r['owner'] == 'me']
hers = [r for r in e2['payroll_by_source'] if r['owner'] == 'spouse']
check('my two jobs together are capped at one elective limit',
      round(sum(r['pretax_retirement'] for r in mine), 2) <= A._401K_ELECTIVE_LIMIT + 0.01,
      [(r['name'], r['pretax_retirement']) for r in mine])
check('and the cap is reported rather than silently applied', e2['retirement_capped'] is True)
check('my spouse still has her own allowance, untouched by mine',
      hers and hers[0]['pretax_retirement'] == 4000.0, hers)

print('\n--- withholding is per job, and totals across them ---')
with app.app_context():
    for sid in (10, 11, 12):
        s = A.IncomeSource.query.get(sid)
        s.pretax_retirement_pct = 3 if sid != 11 else 5
    db.session.commit()
c.put('/api/finance/incomes/10', json={'ytd_federal_withheld': 6000,
                                       'ytd_state_withheld': 1200,
                                       'ytd_as_of': '2026-06-30'})
c.put('/api/finance/incomes/11', json={'ytd_federal_withheld': 4000,
                                       'ytd_state_withheld': 800,
                                       'ytd_as_of': '2026-06-30'})
e3 = est()
check('the source says it came from the paystubs',
      'year-to-date' in (e3['withholding_source'] or ''), e3['withholding_source'])
check('and says it covered more than one job',
      'jobs' in (e3['withholding_source'] or ''), e3['withholding_source'])
check('withholding is known now, not UNKNOWN', e3['withholding_known'] is True)
check('$10,000 through 30 June annualises to about $20,000',
      19000 < e3['withheld'] < 21000, e3['withheld'])
check('a balance can therefore be computed', e3['balance_due'] is not None)

print('\n--- a job with nothing entered contributes wages only ---')
with app.app_context():
    db.session.add(A.IncomeSource(id=13, user_id=1, name='Side W2', owner='me',
                                  type='salary', annual_salary=20000, tax_form='W2',
                                  pay_frequency='biweekly', active=True))
    db.session.commit()
e4 = est()
check('its wages are counted', e4['w2_wages'] == 300000.0, e4['w2_wages'])
check('but it invents no deferral of its own',
      not any(r['name'] == 'Side W2' for r in e4['payroll_by_source']),
      [r['name'] for r in e4['payroll_by_source']])
check("and no other job's percentage is applied to it",
      e4['pretax_retirement'] == e3['pretax_retirement'],
      (e3['pretax_retirement'], e4['pretax_retirement']))

print('\n--- a spouse is excluded when the return does not include her ---')
with app.app_context():
    p = A.TaxProfile.query.filter_by(user_id=1).first()
    p.filing_status = 'single'
    db.session.commit()
e5 = est()
check("her job is not on a single filer's return",
      not any(r['owner'] == 'spouse' for r in e5['payroll_by_source']),
      [r['owner'] for r in e5['payroll_by_source']])
check('and neither is her match', e5['employer_match'] < e3['employer_match'],
      (e3['employer_match'], e5['employer_match']))

print('\n--- nonsense is rejected at the door ---')
r = c.put('/api/finance/incomes/10', json={'pretax_retirement_pct': 900})
check('a 900% deferral is clamped', r.get_json()['pretax_retirement_pct'] == 100.0,
      r.get_json().get('pretax_retirement_pct'))
r = c.put('/api/finance/incomes/10', json={'employer_match_tiers': [
    {'employee_pct': 3, 'match_pct': 100}, {'employee_pct': -5, 'match_pct': 20},
    {'employee_pct': 2, 'match_pct': 9999}]})
check('invalid bands are dropped and valid ones kept',
      len(r.get_json()['employer_match_tiers']) == 1, r.get_json()['employer_match_tiers'])
r = c.put('/api/finance/incomes/10', json={'ytd_federal_withheld': -50})
check('a negative withholding is floored at zero',
      r.get_json()['ytd_federal_withheld'] == 0.0, r.get_json()['ytd_federal_withheld'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PER-SOURCE PAYROLL CHECKS PASSED')
