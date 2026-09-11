"""A farm books its costs as Schedule F lines, not as household categories.

"Groceries" and "subscriptions" say nothing about seed, feed or custom hire, and at tax
time the return wants those lines specifically. Household categories stay available on a
farm's books on purpose — a farm still buys insurance through the same account, and forcing
a choice between the two vocabularies would make some spending unrecordable.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='farmcat_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'f.db').replace(os.sep, '/')
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


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- the Schedule F lines exist and are named as the form names them ---')
check('seed, feed and custom hire are all there',
      {'farm_seeds', 'farm_feed', 'farm_custom_hire'} <= set(A.FARM_CATEGORIES),
      sorted(A.FARM_CATEGORIES)[:5])
check('veterinary and breeding too', 'farm_vet' in A.FARM_CATEGORIES)
check('they read as the return words them',
      A.category_label('farm_custom_hire') == 'Custom hire (machine work)',
      A.category_label('farm_custom_hire'))
check('a household slug is left alone', A.category_label('food') == 'food')

print('\n--- farm slugs cannot collide with household ones that mean something else ---')
# insurance, utilities, taxes and repairs exist in both worlds and are not the same thing.
overlap = set(A.FARM_CATEGORIES) & set(A.HOUSEHOLD_CATEGORIES)
check('no slug is shared between the two sets', overlap == set(), overlap)
for both in ('insurance', 'utilities', 'taxes'):
    check('%s exists separately in each' % both,
          both in A.HOUSEHOLD_CATEGORIES and ('farm_' + both) in A.FARM_CATEGORIES)

print('\n--- a farm gets both vocabularies, a household only its own ---')
check('a farm can book seed', 'farm_seeds' in A.categories_for_entity('farm'))
check('and can still book insurance', 'insurance' in A.categories_for_entity('farm'))
check('a personal set of books gets no farm lines',
      'farm_seeds' not in A.categories_for_entity('personal'))
check('nor does an untagged record', 'farm_seeds' not in A.categories_for_entity(None))

print('\n--- the API offers the right set per kind of books ---')
r = c.get('/api/finance/entities').get_json()
check('household categories are published', len(r['household_categories']) > 10,
      len(r.get('household_categories', [])))
check('and the farm set alongside them', 'farm' in r['category_sets'], list(r['category_sets']))
farm = r['category_sets']['farm']
check('each carries a slug and a readable label',
      all('value' in x and 'label' in x for x in farm), farm[:2])
check('sorted by label, so the list reads alphabetically',
      [x['label'] for x in farm] == sorted(x['label'] for x in farm), [x['label'] for x in farm][:4])

print('\n--- transactions can actually be saved against a farm line ---')
r = c.post('/api/finance/entities', json={'name': 'Allen Farm', 'kind': 'farm'})
eid = r.get_json()['id']
r = c.post('/api/finance/transactions', json={'description': 'Seed corn', 'amount': 4200,
                                              'category': 'farm_seeds'})
check('the farm category is accepted, not coerced to other',
      r.get_json()['category'] == 'farm_seeds', r.get_json()['category'])
tid = r.get_json()['id']
r = c.put('/api/finance/entity/transaction/%d' % tid, json={'entity_id': eid})
check('and it can be tagged to the farm', r.get_json()['entity_id'] == eid, r.get_json())
check('an invented category is still refused',
      c.post('/api/finance/transactions',
             json={'description': 'X', 'amount': 1,
                   'category': 'farm_unicorns'}).get_json()['category'] == 'other')

print('\n--- a farm bill and budget take the same lines ---')
r = c.post('/api/finance/bills', json={'name': 'Feed store', 'category': 'farm_feed',
                                       'amount': 800, 'frequency': 'monthly'})
check('a bill can be a farm line', r.get_json()['category'] == 'farm_feed', r.get_json())
r = c.post('/api/finance/budgets', json={'category': 'farm_fertilizer',
                                         'monthly_limit': 1500})
check('so can a budget', r.get_json()['category'] == 'farm_fertilizer', r.get_json())

print('\n--- the report reads as Schedule F, not as slugs ---')
rep = c.get('/api/finance/entities/report').get_json()
farm_rep = [e for e in rep['entities'] if e['entity']['id'] == eid][0]
check('the farm books show the expense', farm_rep['expenses'] == 4200.0, farm_rep['expenses'])
line = [x for x in farm_rep['by_category'] if x['category'] == 'farm_seeds'][0]
check('the line is labelled for an accountant, not slugged',
      line['label'] == 'Seeds and plants', line)
check('and the raw slug is still there for anything that needs it',
      line['category'] == 'farm_seeds', line)
check('the books are marked as filing Schedule F',
      farm_rep['tax_form'] == 'Schedule F', farm_rep['tax_form'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL FARM CATEGORY CHECKS PASSED')
