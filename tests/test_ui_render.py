"""Do the pages carrying the new UI actually render, and is the plumbing present?

Template errors only surface at request time, and the JS syntax check cannot tell whether a
control was wired to anything. This renders each page as a signed-in user and asserts the
new elements and their handlers exist.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='uir_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'u.db').replace(os.sep, '/')
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
    now = A.datetime.utcnow()
    db.session.add(A.User(id=1, google_id='g1', email='u@x.com', name='U', role='admin',
                          privacy_consent_at=now, privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- /profile renders with the household card ---')
r = c.get('/profile')
check('200', r.status_code == 200, r.status_code)
b = r.get_data(as_text=True)
check('household card present', 'hhBody' in b)
check('create handler wired', 'createHousehold()' in b)
check('invite handler wired', 'inviteToHousehold(' in b)
check('accept/decline wired', 'respondInvite(' in b)
check('leave/remove wired', 'removeMember(' in b)
check('states that joining shares nothing by itself',
      'shares' in b and 'nothing' in b.lower())

print('\n--- /finances renders with the books card and modal fields ---')
r = c.get('/finances')
check('200', r.status_code == 200, r.status_code)
b = r.get_data(as_text=True)
check('books card present', 'entBody' in b)
check('add-books handler wired', 'openEntity(null)' in b)
check('per-year report selector present', 'entYear' in b)
check('share/books fields injected into modals', b.count('shareEntityFields(e)') == 4,
      b.count('shareEntityFields(e)'))
check('share select rendered by the helper', "id=\"xShare\"" in b)
check('books select rendered by the helper', "id=\"xEntity\"" in b)
check('modals apply them after saving', b.count('applyShareEntity(') >= 5,
      b.count('applyShareEntity('))
check('entity + household state load on boot',
      'loadHouseholdState().then(loadEntities)' in b)
check('deductible is labelled as reported apart from expenses',
      'apart from total expenses' in b)

print('\n--- the endpoints those controls call all answer ---')
for method, path, body in (
        ('GET', '/api/household', None),
        ('GET', '/api/finance/entities', None),
        ('GET', '/api/finance/entities/report', None),
):
    r = c.get(path) if method == 'GET' else c.post(path, json=body)
    check('%-5s %-34s -> 200' % (method, path), r.status_code == 200,
          (r.status_code, r.get_data()[:120]))

print('\n--- an end-to-end pass through the new controls ---')
r = c.post('/api/finance/entities', json={'name': 'Allen Farm', 'kind': 'farm'})
check('create books -> 201', r.status_code == 201, r.status_code)
eid = r.get_json()['id']
r = c.post('/api/finance/accounts', json={'name': 'Farm checking', 'type': 'checking',
                                          'balance': 1000})
check('create account -> 201', r.status_code == 201, r.status_code)
aid = r.get_json()['id']
r = c.put('/api/finance/entity/account/%d' % aid, json={'entity_id': eid})
check('tag the account to the farm', r.status_code == 200 and r.get_json()['entity_id'] == eid,
      r.get_json())
r = c.get('/api/finance/accounts')
acct = [a for a in r.get_json()['accounts'] if a['id'] == aid][0]
check('list reports the tag back (to_dict exposes entity_id)', acct.get('entity_id') == eid, acct)
check('and reports the share level', acct.get('share_level') == 'none', acct)
r = c.put('/api/household/share/account/%d' % aid, json={'share_level': 'view'})
check('sharing without a household is refused with a reason', r.status_code == 400,
      (r.status_code, r.get_json()))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL UI RENDER CHECKS PASSED')
