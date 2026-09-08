"""Entities: separate books for the farm, kept distinct from household sharing.

The point of the whole feature is that "what I spent" and "what the farm spent" are
different numbers. The assertions that matter are the ones proving personal spending never
lands in the farm's totals, and that untagged records are visible rather than quietly
dropped.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='ent_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'e.db').replace(os.sep, '/')
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
    db.session.add_all([
        A.User(id=1, google_id='g1', email='j@x.com', name='J', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
        A.User(id=2, google_id='g2', email='p@x.com', name='P', role='admin',
               privacy_consent_at=now, privacy_consent_version=V),
    ])
    db.session.commit()

me, partner = client_for(1), client_for(2)

print('\n--- create the farm ---')
r = me.post('/api/finance/entities', json={'name': 'Allen Farm', 'kind': 'farm'})
check('create -> 201', r.status_code == 201, (r.status_code, r.get_json()))
FARM = r.get_json()['id']
check('farm defaults to Schedule F', r.get_json()['tax_form'] == 'Schedule F', r.get_json())
r = me.post('/api/finance/entities', json={'name': 'Rental', 'kind': 'rental'})
RENTAL = r.get_json()['id']
check('rental defaults to Schedule E', r.get_json()['tax_form'] == 'Schedule E', r.get_json())
r = me.post('/api/finance/entities', json={'name': ''})
check('name is required', r.status_code == 400, r.status_code)

print('\n--- tag some spending ---')
with app.app_context():
    for i, (amt, cat, desc) in enumerate([
            (1200.0, 'other', 'Seed and fertiliser'),
            (450.0, 'transportation', 'Tractor diesel'),
            (300.0, 'utilities', 'Barn electric'),
            (85.0, 'food', 'Family groceries'),          # personal, stays untagged
            (60.0, 'entertainment', 'Cinema'),            # personal, stays untagged
    ]):
        db.session.add(A.SpendTransaction(
            id=100 + i, user_id=1, posted_at=date(YEAR, 6, 1),
            description=desc, amount=amt, category=cat, source='manual'))
    db.session.add(A.TaxDocument(id=200, user_id=1, doc_type='receipt', tax_year=YEAR,
                                 merchant='Tractor Supply', amount=1200, deductible=True,
                                 filename='seed.pdf', content_type='application/pdf'))
    db.session.add(A.TaxDocument(id=201, user_id=1, doc_type='receipt', tax_year=YEAR,
                                 merchant='Target', amount=85, deductible=False,
                                 filename='groc.pdf', content_type='application/pdf'))
    db.session.add(A.IncomeSource(id=300, user_id=1, name='Crop sales', type='self_employed',
                                  annual_salary=48000, tax_form='1099', active=True))
    db.session.commit()

for rid in (100, 101, 102):
    r = me.put('/api/finance/entity/transaction/%d' % rid, json={'entity_id': FARM})
    check('tagged transaction %d' % rid, r.status_code == 200, (r.status_code, r.get_json()))
me.put('/api/finance/entity/document/200', json={'entity_id': FARM})
me.put('/api/finance/entity/income/300', json={'entity_id': FARM})

r = me.put('/api/finance/entity/transaction/100', json={'entity_id': 99999})
check('cannot tag to an entity that does not exist', r.status_code == 404, r.status_code)
r = me.put('/api/finance/entity/plaid/1', json={'entity_id': FARM})
check('untaggable kinds are refused', r.status_code == 400, (r.status_code, r.get_json()))

print('\n--- the farm books ---')
rep = me.get('/api/finance/entities/report?entity_id=%d&year=%d' % (FARM, YEAR)).get_json()
check('farm expenses are only the farm transactions', rep['expenses'] == 1950.0, rep['expenses'])
check('personal groceries are NOT in the farm books',
      all(c['category'] != 'food' for c in rep['by_category']), rep['by_category'])
check('farm income counted', rep['income'] == 48000.0, rep['income'])
check('net = income - expenses', rep['net'] == 48000.0 - 1950.0, rep['net'])
check('deductible receipts totalled separately', rep['deductible_receipts'] == 1200.0,
      rep['deductible_receipts'])
check('deductible is reported apart from total expenses',
      rep['deductible_receipts'] != rep['expenses'], rep)
check('labelled Schedule F', rep['tax_form'] == 'Schedule F', rep['tax_form'])
check('counts the transactions', rep['transactions'] == 3, rep['transactions'])

print('\n--- untagged spending is surfaced, not swallowed ---')
allrep = me.get('/api/finance/entities/report?year=%d' % YEAR).get_json()
un = allrep['unassigned']
check('unassigned bucket exists', un is not None)
check('it holds the personal spending', un['expenses'] == 145.0, un['expenses'])
check('and its non-deductible receipt', un['receipts_on_file'] == 1, un['receipts_on_file'])
check('the rental has nothing yet',
      [e for e in allrep['entities'] if e['entity']['id'] == RENTAL][0]['expenses'] == 0.0)
check('business entities are listed for tax purposes',
      {e['entity']['name'] for e in allrep['business_entities']} == {'Allen Farm', 'Rental'},
      [e['entity']['name'] for e in allrep['business_entities']])

print('\n--- entities are private until shared through a household ---')
check('partner sees none of my entities',
      len(partner.get('/api/finance/entities').get_json()['entities']) == 0)
r = me.post('/api/household', json={'name': 'Allen household'})
HID = r.get_json()['id']
r = me.post('/api/household/%d/invite' % HID, json={'email': 'p@x.com'})
partner.post('/api/household/invitations/%d' % r.get_json()['id'])
check('household membership alone does not share the farm',
      len(partner.get('/api/finance/entities').get_json()['entities']) == 0,
      partner.get('/api/finance/entities').get_json())
me.put('/api/finance/entities/%d' % FARM, json={'shared_with_household': True})
names = [e['name'] for e in partner.get('/api/finance/entities').get_json()['entities']]
check('sharing the farm makes it taggable by the partner', names == ['Allen Farm'], names)

print('\n--- entity and sharing are independent axes ---')
MONTH = '%d-06' % YEAR      # the seeded transactions are dated June, not this month
r = partner.get('/api/finance/transactions?month=' + MONTH)
check('partner still sees no transactions (none are shared)', r.get_json()['count'] == 0,
      r.get_json())
me.put('/api/household/share/transaction/100', json={'share_level': 'view'})
r = partner.get('/api/finance/transactions?month=' + MONTH)
d = r.get_json()
check('sharing one transaction shows exactly that one', d['count'] == 1, d)
check('the other farm transactions stay private',
      {t['description'] for t in d['transactions']} == {'Seed and fertiliser'},
      [t['description'] for t in d['transactions']])
check('a shared record keeps its entity tag — sharing and books are independent',
      d['transactions'][0].get('entity_id') == FARM,
      (d['transactions'][0].get('entity_id'), FARM))

print('\n--- deactivating an entity keeps the books intact ---')
r = me.delete('/api/finance/entities/%d' % RENTAL)
check('delete deactivates rather than destroying', r.get_json().get('deactivated') is True,
      r.get_json())
names = [e['name'] for e in me.get('/api/finance/entities').get_json()['entities']]
check('it disappears from the picker', 'Rental' not in names, names)
with app.app_context():
    check('but the row survives so tagged records keep their reference',
          db.session.get(A.Entity, RENTAL) is not None)
    check('and the farm tags are untouched',
          A.SpendTransaction.query.filter_by(entity_id=FARM).count() == 3)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL ENTITY CHECKS PASSED')
