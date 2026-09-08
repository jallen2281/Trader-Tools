"""Credit tracking wired into the application.

test_credit.py covers the arithmetic. This covers the attachment points: that a credit
limit round-trips through the debt endpoints and can be cleared back to unknown, that
readings are validated and de-duplicated per bureau/scale/day, that a household partner
only sees what was shared, and that the overview and the AI briefing both pick it up.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='credapi_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'c.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
TODAY = date.today()


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
    db.session.add_all([
        A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='partner@x.com', name='Partner', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.commit()

me, partner = client_for(1), client_for(2)


def credit(c=None):
    return (c or me).get('/api/finance/credit').get_json()


print('\n--- a credit limit round-trips through the debt endpoints ---')
r = me.post('/api/finance/debts', json={'name': 'Visa', 'type': 'credit_card',
                                        'balance': 4000, 'apr': 24.99,
                                        'min_payment': 120, 'credit_limit': 10000})
check('the debt is created', r.status_code == 201, r.get_json())
visa = r.get_json()
check('the limit comes back', visa['credit_limit'] == 10000.0, visa)
check('and utilization is derived on the record', visa['utilization_pct'] == 40.0, visa)
r = me.post('/api/finance/debts', json={'name': 'Store card', 'type': 'credit_card',
                                        'balance': 900, 'apr': 29.99})
store = r.get_json()
check('a card with no limit reports None, not zero', store['credit_limit'] is None, store)
check('and no utilization at all', store['utilization_pct'] is None, store)
r = me.post('/api/finance/debts', json={'name': 'Mortgage', 'type': 'mortgage',
                                        'balance': 210000, 'apr': 6.1, 'secured': True})
mortgage = r.get_json()

print('\n--- utilization counts cards, and only cards ---')
d = credit()
u = d['utilization']
check('the mortgage is not in the ratio', u['total_balance'] == 4000, u)
check('nor is its balance in the limit total', u['total_limit'] == 10000, u)
check('40% overall', u['pct'] == 40.0, u['pct'])
check('the limitless card is listed as unknown',
      [c['name'] for c in u['cards_without_limit']] == ['Store card'], u['cards_without_limit'])
check('the paydown figure is stated', d['paydown_to_30'] == 1000.0, d['paydown_to_30'])

print('\n--- clearing a limit puts the card back to unknown ---')
r = me.put('/api/finance/debts/%d' % visa['id'], json={'credit_limit': ''})
check('an empty limit clears rather than zeroing', r.get_json()['credit_limit'] is None,
      r.get_json())
check('so there is no ratio left to report', credit()['utilization']['ratio'] is None,
      credit()['utilization'])
r = me.put('/api/finance/debts/%d' % visa['id'], json={'credit_limit': 10000})
check('and setting it again restores the ratio', credit()['utilization']['pct'] == 40.0)
r = me.put('/api/finance/debts/%d' % mortgage['id'], json={'balance': 209000})
check('an update that omits credit_limit leaves it alone',
      r.get_json()['credit_limit'] is None, r.get_json())

print('\n--- recording score readings ---')
r = me.post('/api/finance/credit/scores',
            json={'score': 700, 'as_of': (TODAY - timedelta(days=90)).isoformat(),
                  'bureau': 'equifax', 'scale': 'fico8', 'source': 'Chase'})
check('a reading is accepted', r.status_code == 201, r.get_json())
me.post('/api/finance/credit/scores',
        json={'score': 742, 'as_of': TODAY.isoformat(), 'bureau': 'equifax',
              'scale': 'fico8'})
d = credit()
check('one series so far', len(d['series']) == 1, [s['key'] for s in d['series']])
s0 = d['series'][0]
check('latest is the newest reading', s0['latest'] == 742, s0)
check('the trend is +42', s0['change'] == 42, s0['change'])
check('band is reported', s0['band'] == 'very good', s0['band'])
check('history is ordered for plotting', [h['score'] for h in s0['history']] == [700, 742],
      s0['history'])
check('with one series there is an unambiguous headline', d['headline'] == 742, d['headline'])

print('\n--- a second bureau does not become part of the first trend ---')
me.post('/api/finance/credit/scores',
        json={'score': 698, 'as_of': TODAY.isoformat(), 'bureau': 'transunion',
              'scale': 'vantage3'})
d = credit()
check('now two separate series', len(d['series']) == 2, [s['key'] for s in d['series']])
eq = [s for s in d['series'] if s['bureau'] == 'equifax'][0]
check('equifax still reads +42, not a crash', eq['change'] == 42, eq['change'])
check('with two bureaus there is no single headline', d['headline'] is None, d['headline'])
check('and no drop is reported',
      not [f for f in d['findings'] if f['key'].startswith('score_drop')],
      [f['key'] for f in d['findings']])

print('\n--- the same bureau, scale and day is one reading, not two ---')
me.post('/api/finance/credit/scores',
        json={'score': 745, 'as_of': TODAY.isoformat(), 'bureau': 'equifax',
              'scale': 'fico8'})
d = credit()
eq = [s for s in d['series'] if s['bureau'] == 'equifax'][0]
check('still two readings in the series', eq['readings'] == 2, eq['readings'])
check('and the correction took effect', eq['latest'] == 745, eq['latest'])

print('\n--- nonsense readings are refused ---')
for label, body in (
        ('a score of 1200', {'score': 1200}),
        ('a score of 12', {'score': 12}),
        ('a non-numeric score', {'score': 'good'}),
        ('a missing score', {}),
        ('an unparseable date', {'score': 700, 'as_of': 'last tuesday'}),
        ('a reading dated in the future',
         {'score': 700, 'as_of': (TODAY + timedelta(days=1)).isoformat()}),
):
    r = me.post('/api/finance/credit/scores', json=body)
    check(label + ' is rejected', r.status_code == 400, (r.status_code, r.get_json()))
r = me.post('/api/finance/credit/scores', json={'score': 710, 'bureau': 'sneaky',
                                                'scale': 'made-up'})
check('an unknown bureau falls back to other rather than being stored raw',
      r.get_json()['bureau'] == 'other' and r.get_json()['scale'] == 'other', r.get_json())
check('a reading with no date defaults to today',
      r.get_json()['as_of'] == TODAY.isoformat(), r.get_json())
me.delete('/api/finance/credit/scores/%d' % r.get_json()['id'])

print('\n--- readings belong to one person unless shared ---')
check('the partner sees none of my scores', credit(partner)['series'] == [],
      credit(partner)['series'])
check('nor my cards', credit(partner)['utilization']['cards'] == [])
with app.app_context():
    h = A.Household(name='Home', created_by=1)
    db.session.add(h)
    db.session.flush()
    db.session.add_all([A.HouseholdMember(household_id=h.id, user_id=1, role='owner',
                                          status='active', invited_email='me@x.com'),
                        A.HouseholdMember(household_id=h.id, user_id=2, role='member',
                                          status='active', invited_email='partner@x.com')])
    db.session.commit()
check('a household alone shares nothing', credit(partner)['series'] == [],
      credit(partner)['series'])
with app.app_context():
    sid = A.CreditScore.query.filter_by(user_id=1, bureau='equifax').order_by(
        A.CreditScore.as_of.desc()).first().id
r = me.put('/api/household/share/credit_score/%d' % sid, json={'share_level': 'view'})
check('a score can be shared explicitly', r.status_code == 200, r.get_json())
check('and then the partner sees that one', len(credit(partner)['series']) == 1,
      credit(partner)['series'])
check('but not the ones still private',
      credit(partner)['series'][0]['readings'] == 1,
      credit(partner)['series'][0])
r = partner.delete('/api/finance/credit/scores/%d' % sid)
check('view-level sharing does not let them delete it', r.status_code == 404, r.status_code)

print('\n--- deleting my own reading works ---')
before = len(credit()['readings'])
r = me.delete('/api/finance/credit/scores/%d' % sid)
check('delete succeeds', r.status_code == 200, r.get_json())
check('and the reading is gone', len(credit()['readings']) == before - 1)
check('a second delete is a 404',
      me.delete('/api/finance/credit/scores/%d' % sid).status_code == 404)
check('signed-out requests are refused',
      app.test_client().get('/api/finance/credit').status_code in (401, 302))

print('\n--- the overview and the briefing pick it up ---')
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('40% utilization is a note about being over 30',
      obs.get('utilization_elevated', {}).get('severity') == 'note', list(obs))
check('the missing limit is reported', 'missing_limits' in obs, list(obs))
with app.app_context():
    d = A.Debt.query.filter_by(name='Visa').first()
    d.balance = 7000
    db.session.commit()
obs = {o['key']: o for o in me.get('/api/finance/overview').get_json()['observations']}
check('70% becomes a warning', obs.get('utilization_high', {}).get('severity') == 'warning',
      list(obs))
check('which names the dollars to move', obs['utilization_high']['amount'] == 4000.0,
      obs['utilization_high'])
with app.app_context():
    pic = A._finance_full_picture(1)
    facts = A._overview_facts(pic, A._finance_observations(pic))
check('the briefing has a credit section', '== CREDIT ==' in facts)
check('it states the utilization', 'Revolving utilization 70%' in facts,
      [l for l in facts.split('\n') if 'utilization' in l])
check('it names the card with no limit recorded',
      'credit limit NOT recorded' in facts,
      [l for l in facts.split('\n') if 'NOT recorded' in l])
check('and warns the model not to compare bureaus to each other',
      'not comparable to each other' in facts,
      [l for l in facts.split('\n') if 'comparable' in l])

print('\n--- someone with no cards is not nagged about scores ---')
r = partner.post('/api/finance/debts', json={'name': 'Car loan', 'type': 'auto',
                                             'balance': 12000, 'apr': 7.2})
check('no revolving credit means no prompt to record a score',
      not [f for f in credit(partner)['findings'] if f['key'] == 'no_scores'],
      [f['key'] for f in credit(partner)['findings']])
partner.post('/api/finance/debts', json={'name': 'My card', 'type': 'credit_card',
                                         'balance': 100, 'credit_limit': 3000})
with app.app_context():
    A.CreditScore.query.filter_by(user_id=1).delete()
    db.session.commit()
check('but once there is a card, it is worth asking for',
      any(f['key'] == 'no_scores' for f in credit(partner)['findings']),
      [f['key'] for f in credit(partner)['findings']])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CREDIT API CHECKS PASSED')
