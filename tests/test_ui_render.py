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
# Every record the backend can tag to a book must have the selector, or the capability
# exists in the API and is unreachable -- income was taggable for weeks with no way to do it.
_TAGGABLE_MODALS = ('openIncome', 'openDebt', 'openAccount', 'openBill', 'openBudget',
                    'openTxn')
for _m in _TAGGABLE_MODALS:
    _body = b.split('function %s' % _m, 1)[-1].split(chr(10) + '    }', 1)[0]
    check('%s offers the books selector' % _m, 'shareEntityFields' in _body)
check('share/books fields injected into every taggable modal',
      b.count('shareEntityFields(e)') == len(_TAGGABLE_MODALS),
      b.count('shareEntityFields(e)'))
check('share select rendered by the helper', "id=\"xShare\"" in b)
check('books select rendered by the helper', "id=\"xEntity\"" in b)
check('modals apply them after saving',
      b.count('applyShareEntity(') >= len(_TAGGABLE_MODALS),
      b.count('applyShareEntity('))
check('entity + household state load on boot',
      'loadHouseholdState().then(loadEntities)' in b)
check('deductible is labelled as reported apart from expenses',
      'apart from total expenses' in b)
check('connected accounts are broken out, not just institutions',
      'renderPlaidAccounts' in b and 'linkPlaidAccount(' in b)
check('balances can be refreshed from the bank', 'refreshPlaidBalances(' in b)
check('history can be backfilled past the cursor', 'backfillPlaid(' in b)
check('receipts can be reconciled against the bank feed', 'reconcileReceipts(' in b)
check('each income carries its own payroll detail', 'iPayrollBox' in b)
check('with its own match schedule', 'collectIncTiers(' in b and 'id="iTiers"' in b)
check('and its own withholding', 'id="iYtdFed"' in b and 'id="iYtdAsOf"' in b)
check('deductions are line items entered per check', 'id="iDeductions"' in b
      and 'collectDeductions(' in b)
check('with the pre-tax vs post-tax difference spelled out',
      'escapes income tax' in b and 'reduces take-home only' in b)
check('cash-flow says it is net pay', 'net pay in vs bills out' in b)
check('a transaction can be paid from a credit card', 'Credit cards' in b
      and "paid_from:g('tAcct')" in b)
check('and the spending list shows where each came from', 'paidFromLabel(' in b)
check('bills offer a semiannual frequency', "'semiannual'" in b)
check('payoff plan card present', 'debtPlanBody' in b)
check('its strategy toggle and extra-payment input are wired',
      'planStrategy' in b and 'saveExtra(' in b)
check('a bill can be linked to the debt it pays', 'id="bDebt"' in b)
check('and to the account it is paid from', 'id="bAcct"' in b)
check('budgets separate limits from merely-tracked categories', 'budgetTracked' in b)
check('removing a limit says what will actually happen', 'only the limit goes' in b)
check('credit card present', 'creditBody' in b)
check('the score modal is wired', 'openScore()' in b and 'saveScore(' in b)
check('a credit limit can be entered on a debt', "id=\"dLimit\"" in b)
check('recurring-charges card present', 'recurringBody' in b)
check('its actions are wired', 'recAdopt(' in b and 'recDecide(' in b)
check('it is fetched alongside the rest of the budgeting load',
      "fetch('/api/finance/recurring'" in b)

print('\n--- the endpoints those controls call all answer ---')
for method, path, body in (
        ('GET', '/api/household', None),
        ('GET', '/api/finance/entities', None),
        ('GET', '/api/finance/entities/report', None),
        ('GET', '/api/finance/recurring', None),
        ('GET', '/api/finance/credit', None),
        ('GET', '/api/finance/debt-plan', None),
        ('GET', '/api/finance/income/reconciliation', None),
        ('GET', '/api/finance/deposits', None),
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
