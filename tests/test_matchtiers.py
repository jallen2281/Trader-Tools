"""Tiered employer 401(k) match.

Real plans stack bands — "100% of the first 3%, 20% of the next 2%, 10% of the next 1%" —
and that cannot be expressed as a single rate up to a cap. The schedule under test here is
a real one, but nothing about it is hardcoded: it is entered as data, and the generic cases
below check that other shapes work equally well.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='match_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'm.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
SALARY = 100000.0        # round number so the percentages read directly as dollars

CURRENT = [{'employee_pct': 3, 'match_pct': 100},
           {'employee_pct': 2, 'match_pct': 20},
           {'employee_pct': 1, 'match_pct': 10}]
ENHANCED = [{'employee_pct': 3, 'match_pct': 100},
            {'employee_pct': 2, 'match_pct': 25}]


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
    db.session.add(A.User(id=1, google_id='g1', email='m@x.com', name='M', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.IncomeSource(user_id=1, name='Salary', type='salary',
                                  annual_salary=SALARY, pay_frequency='biweekly',
                                  tax_form='W2', active=True))
    db.session.add(A.TaxProfile(user_id=1, filing_status='mfj',
                                pretax_retirement_mode='percent'))
    db.session.commit()

c = client_for(1)

print('\n--- the current schedule: 3%@100 + 2%@20 + 1%@10 ---')
set_profile(employer_match_tiers=CURRENT, pretax_retirement_pct=3, roth_retirement_pct=3)
e = est()
check('full match is 3.5% of pay, as the plan states', e['full_match_pct'] == 3.5,
      e['full_match_pct'])
check('needs a 6% deferral to fill every band', e['deferral_for_full_match'] == 6.0,
      e['deferral_for_full_match'])
check('at 6% the match is $3,500', e['employer_match'] == 3500.0, e['employer_match'])
check('nothing left unclaimed', e['unclaimed_match'] == 0.0, e['unclaimed_match'])

print('\n--- bands fill in order, which is the whole point ---')
set_profile(pretax_retirement_pct=3, roth_retirement_pct=0)      # 3% total
e3 = est()
check('3% deferral earns the full 100% band only: $3,000',
      e3['employer_match'] == 3000.0, e3['employer_match'])
check('and leaves $500 unclaimed', e3['unclaimed_match'] == 500.0, e3['unclaimed_match'])
set_profile(pretax_retirement_pct=4, roth_retirement_pct=0)      # 3% @100 + 1% @20
e4 = est()
check('4% earns 3.0% + 0.2% = $3,200', e4['employer_match'] == 3200.0, e4['employer_match'])
set_profile(pretax_retirement_pct=5, roth_retirement_pct=0)
e5 = est()
check('5% earns 3.0% + 0.4% = $3,400', e5['employer_match'] == 3400.0, e5['employer_match'])
check('a flat "100% up to 6%" model would have said $5,000 — the bug this replaces',
      e5['employer_match'] != 5000.0)

print('\n--- traditional and Roth both count toward the match ---')
set_profile(pretax_retirement_pct=3, roth_retirement_pct=3)
check('3% traditional + 3% Roth fills all six points', est()['employer_match'] == 3500.0,
      est()['employer_match'])

print('\n--- the enhanced schedule reaches the same 3.5% one point sooner ---')
set_profile(employer_match_tiers=ENHANCED, pretax_retirement_pct=5, roth_retirement_pct=0)
en = est()
check('also 3.5% of pay in total', en['full_match_pct'] == 3.5, en['full_match_pct'])
check('but needs only a 5% deferral', en['deferral_for_full_match'] == 5.0,
      en['deferral_for_full_match'])
check('5% collects the whole $3,500', en['employer_match'] == 3500.0, en['employer_match'])
set_profile(pretax_retirement_pct=6, roth_retirement_pct=0)
check('a 6th percent earns nothing extra under Enhanced',
      est()['employer_match'] == 3500.0, est()['employer_match'])

print('\n--- the overview names the schedule, not a single cap ---')
set_profile(employer_match_tiers=CURRENT, pretax_retirement_pct=2, roth_retirement_pct=0)
obs = {o['key']: o for o in c.get('/api/finance/overview').get_json()['observations']}
o = obs.get('unclaimed_match', {})
check('flags the unclaimed match', o.get('severity') == 'warning', list(obs))
check('quotes the deferral needed for the full match', '6' in o.get('detail', ''), o.get('detail'))
check('quotes the plan total of 3.5%', '3.5' in o.get('detail', ''), o.get('detail'))
with app.app_context():
    pic = A._finance_full_picture(1)
    facts = A._overview_facts(pic, A._finance_observations(pic))
check('AI briefing spells out every band', '3% of pay matched at 100%' in facts
      and '1% of pay matched at 10%' in facts,
      [l for l in facts.split('\n') if 'match' in l.lower()][:2])

print('\n--- nothing is hardcoded: other shapes work too ---')
set_profile(employer_match_tiers=[{'employee_pct': 6, 'match_pct': 50}],
            pretax_retirement_pct=6, roth_retirement_pct=0)
check('a simple 50%-of-first-6% plan = 3.0% of pay', est()['full_match_pct'] == 3.0,
      est()['full_match_pct'])
set_profile(employer_match_tiers=[{'employee_pct': 4, 'match_pct': 100},
                                  {'employee_pct': 4, 'match_pct': 50}],
            pretax_retirement_pct=8, roth_retirement_pct=0)
check('a two-band 100%/50% plan = 6.0% of pay', est()['full_match_pct'] == 6.0,
      est()['full_match_pct'])
set_profile(employer_match_tiers=None, employer_match_rate_pct=100,
            employer_match_limit_pct=6, pretax_retirement_pct=6, roth_retirement_pct=0)
check('a legacy flat profile still works as one band', est()['employer_match'] == 6000.0,
      est()['employer_match'])
set_profile(employer_match_tiers=None, employer_match_rate_pct=0, employer_match_limit_pct=0)
check('no match configured means no match and no false warning',
      est()['employer_match'] == 0.0 and est()['unclaimed_match'] == 0.0, est()['employer_match'])

print('\n--- the API round-trips and rejects nonsense bands ---')
r = c.put('/api/finance/tax-profile', json={'employer_match_tiers': CURRENT})
p = r.get_json()['profile']
check('tiers saved', len(p['employer_match_tiers']) == 3, p.get('employer_match_tiers'))
check('and the derived total comes back', p['full_match_pct'] == 3.5, p.get('full_match_pct'))
r = c.put('/api/finance/tax-profile', json={'employer_match_tiers': [
    {'employee_pct': 3, 'match_pct': 100}, {'employee_pct': -5, 'match_pct': 20},
    {'employee_pct': 2, 'match_pct': 9999}, {'employee_pct': 'x', 'match_pct': 'y'}]})
kept = r.get_json()['profile']['employer_match_tiers']
check('invalid bands are dropped, valid ones kept', len(kept) == 1
      and kept[0]['employee_pct'] == 3, kept)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL MATCH TIER CHECKS PASSED')
