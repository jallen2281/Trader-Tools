"""Accounts inside a connection, and the deposits that used to be thrown away.

A PlaidItem is a login, not an account. Connecting Chase can return a checking account and
two credit cards, and before this they collapsed into one "connection" with every
transaction pooled. The deposits are the other half of the same problem: they were counted
and discarded with the message "income is tracked separately", which is right for a paycheck
and exactly backwards on a credit card, where an incoming amount is a payment TO the card.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='plaidacct_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['PLAID_ENCRYPTION_KEY'] = 'x' * 32
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402
import plaid_client as pc  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
TODAY = date.today()


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


ACCOUNTS = [
    {'account_id': 'acc-chk', 'name': 'Total Checking', 'official_name': 'CHASE TOTAL CHECKING',
     'mask': '1234', 'type': 'depository', 'subtype': 'checking',
     'balances': {'current': 2500.0, 'available': 2450.0, 'limit': None, 'iso_currency_code': 'USD'}},
    {'account_id': 'acc-prime', 'name': 'Prime Visa', 'official_name': 'CHASE PRIME VISA',
     'mask': '4321', 'type': 'credit', 'subtype': 'credit card',
     'balances': {'current': 471.0, 'available': 26529.0, 'limit': 27000.0, 'iso_currency_code': 'USD'}},
    {'account_id': 'acc-freedom', 'name': 'Freedom Visa', 'official_name': 'CHASE FREEDOM',
     'mask': '9876', 'type': 'credit', 'subtype': 'credit card',
     'balances': {'current': 46.89, 'available': 1253.11, 'limit': 1300.0, 'iso_currency_code': 'USD'}},
]


def txn(tid, acct, amount, name, pfc=None, day_offset=0):
    t = {'transaction_id': tid, 'account_id': acct, 'amount': amount, 'name': name,
         'date': (TODAY - timedelta(days=day_offset)).isoformat()}
    if pfc:
        t['personal_finance_category'] = {'primary': pfc, 'detailed': pfc + '_OTHER'}
    return t


class FakePlaid:
    available = True
    pages = []

    def accounts_get(self, token):
        return {'accounts': ACCOUNTS}

    def transactions_sync(self, token, cursor=None, count=500):
        return self.pages.pop(0) if self.pages else {
            'added': [], 'modified': [], 'removed': [], 'next_cursor': 'cur', 'has_more': False}


FAKE = FakePlaid()
A._plaid = lambda: FAKE
pc.decrypt_token = lambda blob: 'access-token'

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    # Records the user already keeps by hand, with stale figures.
    db.session.add_all([
        A.FinanceAccount(id=10, user_id=1, name='Chase', type='checking', balance=248.79),
        A.Debt(id=20, user_id=1, name='Prime visa', type='credit_card', balance=999.0,
               apr=24.99, credit_limit=None),
        A.Debt(id=21, user_id=1, name='Freedom Visa', type='credit_card', balance=0.0,
               apr=22.0, credit_limit=None),
        A.IncomeSource(id=30, user_id=1, name='Salary', type='salary', annual_salary=104000,
                       pay_frequency='biweekly', tax_form='W2', active=True),
        A.PlaidItem(id=1, user_id=1, item_id='it-1', access_token_enc=b'x',
                    institution_name='Chase'),
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

FAKE.pages = [{
    'added': [
        txn('t1', 'acc-prime', 51.20, 'STARBUCKS'),
        txn('t2', 'acc-prime', 122.00, 'HOME DEPOT'),
        txn('t3', 'acc-freedom', 9.99, 'NETFLIX'),
        txn('t4', 'acc-chk', 1800.00, 'RENT'),
        # money in: a paycheck into checking, and a payment onto each card
        txn('t5', 'acc-chk', -2400.00, 'ACME PAYROLL', pfc='INCOME'),
        txn('t6', 'acc-prime', -471.00, 'AUTOPAY THANK YOU', pfc='TRANSFER_IN'),
        txn('t7', 'acc-freedom', -46.89, 'PAYMENT THANK YOU', pfc='TRANSFER_IN'),
    ],
    'modified': [], 'removed': [], 'next_cursor': 'cur-1', 'has_more': False,
}]

with app.app_context():
    item = A.PlaidItem.query.get(1)
    result = A._plaid_sync_item(item)
    db.session.commit()

print('\n--- the connection is broken out into its accounts ---')
check('all three accounts imported', result['accounts'] == 3, result)
r = c.get('/api/plaid/accounts').get_json()
accts = {a['name']: a for a in r['accounts']}
check('checking, Prime and Freedom are all listed', len(accts) == 3, list(accts))
check('each carries the mask, which is the only way to tell two Visas apart',
      accts['Prime Visa']['mask'] == '4321' and accts['Freedom Visa']['mask'] == '9876', accts)
check('credit accounts are marked as such', accts['Prime Visa']['is_credit'] is True)
check('the checking account is not', accts['Total Checking']['is_credit'] is False)
check('balances came back', accts['Prime Visa']['current_balance'] == 471.0, accts['Prime Visa'])
check('so did the credit limit', accts['Freedom Visa']['credit_limit'] == 1300.0,
      accts['Freedom Visa'])
check('the institution is named on each', accts['Prime Visa']['institution_name'] == 'Chase')

print('\n--- transactions are attributed to the account they came from ---')
check('spending on Prime is counted', accts['Prime Visa']['transaction_count'] == 2, accts['Prime Visa'])
check('and on Freedom separately', accts['Freedom Visa']['transaction_count'] == 1, accts['Freedom Visa'])
check('and on checking', accts['Total Checking']['transaction_count'] == 1, accts['Total Checking'])
with app.app_context():
    check('none are left unattributed',
          A.SpendTransaction.query.filter_by(source='plaid', plaid_account_id=None).count() == 0)

print('\n--- linking is suggested but never applied on its own ---')
check('Prime Visa is matched to the debt of the same name',
      accts['Prime Visa']['suggested_link_id'] == 20, accts['Prime Visa'])
check('and Freedom Visa to its own, not to Prime',
      accts['Freedom Visa']['suggested_link_id'] == 21, accts['Freedom Visa'])
check('a card suggests a debt, not an asset account',
      accts['Prime Visa']['suggested_link_kind'] == 'debt')
check('checking suggests an account', accts['Total Checking']['suggested_link_kind'] == 'account')
with app.app_context():
    check('nothing is linked automatically',
          A.PlaidAccount.query.filter(A.PlaidAccount.linked_debt_id.isnot(None)).count() == 0)
    check('and the hand-entered balance is untouched until it is',
          float(A.Debt.query.get(20).balance) == 999.0)

print('\n--- a wrong suggestion is worse than none ---')
# Drawn from real data. Plaid returns the generic name "CREDIT CARD" for both Chase Visas,
# and the user separately tracks a "Citi Card". Matching on the shared word "card" suggested
# linking the Freedom Visa to the Citi Card — a different card, a different balance, and
# accepting it would have overwritten a real figure.
with app.app_context():
    class _PA:
        mask = None
        name = 'CREDIT CARD'
        official_name = None

        def is_credit(self):
            return True

    class _R:
        def __init__(self, i, n):
            self.id, self.name = i, n

    sid, score = A._suggest_link(_PA(), [_R(1, 'Citi Card'), _R(2, 'Amex')], [])
    check('a generic card name suggests nothing at all', sid is None, (sid, score))

    class _PA2(_PA):
        mask = '8547'

    sid, score = A._suggest_link(_PA2(), [_R(1, 'Citi Card'), _R(2, 'Freedom Visa 8547')], [])
    check('but the last four digits are decisive when the user recorded them',
          sid == 2, (sid, score))

    class _PA3(_PA):
        name = 'SoFi Savings'

        def is_credit(self):
            return False

    sid, score = A._suggest_link(_PA3(), [], [_R(1, 'Sofi'), _R(2, 'Sofi')])
    check('an ambiguous tie suggests nothing rather than guessing', sid is None, (sid, score))
    sid, score = A._suggest_link(_PA3(), [], [_R(1, 'Sofi Savings'), _R(2, 'Chase')])
    check('an unambiguous name still matches', sid == 1, (sid, score))

print('\n--- linking refreshes the balance and the credit limit ---')
r = c.put('/api/plaid/accounts/%d/link' % accts['Prime Visa']['id'],
          json={'kind': 'debt', 'id': 20})
check('link accepted', r.status_code == 200, r.get_json())
with app.app_context():
    d = A.Debt.query.get(20)
    check('the stale balance is replaced by the bank figure', float(d.balance) == 471.0, d.balance)
    check('the credit limit arrives too, which utilization needs',
          float(d.credit_limit) == 27000.0, d.credit_limit)
    check('the APR the user set is NOT overwritten', float(d.apr) == 24.99, d.apr)
    check('nor the name they chose', d.name == 'Prime visa', d.name)
r = c.put('/api/plaid/accounts/%d/link' % accts['Total Checking']['id'],
          json={'kind': 'account', 'id': 10})
with app.app_context():
    check('a depository account updates its FinanceAccount',
          float(A.FinanceAccount.query.get(10).balance) == 2500.0)

print('\n--- several accounts roll up into one record, summed ---')
# SoFi "Vaults" are separate accounts to Plaid -- distinct numbers, distinct balances -- but
# one savings pot to the person holding them. On the real data three of them were linked to
# a single record which then held whichever balance synced last: $14.67 of a real $151.49.
with app.app_context():
    db.session.add_all([
        A.FinanceAccount(id=11, user_id=1, name='Sofi Savings', type='savings', balance=0),
        A.PlaidAccount(user_id=1, item_id=1, account_id='v-main', name='SoFi Savings',
                       mask='3808', type='depository', subtype='savings',
                       current_balance=136.39),
        A.PlaidAccount(user_id=1, item_id=1, account_id='v-emg', name='Emergency Fund',
                       mask='4501', type='depository', subtype='cash management',
                       current_balance=0.43),
        A.PlaidAccount(user_id=1, item_id=1, account_id='v-tax', name='Taxes',
                       mask='4502', type='depository', subtype='cash management',
                       current_balance=14.67),
    ])
    db.session.commit()
    vaults = [p.id for p in
              A.PlaidAccount.query.filter(A.PlaidAccount.account_id.like('v-%')).all()]

for aid in vaults:
    r = c.put('/api/plaid/accounts/%d/link' % aid, json={'kind': 'account', 'id': 11})
    check('a second and third account may share a record', r.status_code == 200, r.get_json())
with app.app_context():
    check('the balance is the SUM, not the last one to arrive',
          float(A.FinanceAccount.query.get(11).balance) == 151.49,
          A.FinanceAccount.query.get(11).balance)

print('\n--- a re-sync keeps the sum rather than reverting to one vault ---')
FAKE.pages = []
with app.app_context():
    A._plaid_sync_item(A.PlaidItem.query.get(1))
    db.session.commit()
    check('still the total after a full sync',
          float(A.FinanceAccount.query.get(11).balance) == 151.49,
          A.FinanceAccount.query.get(11).balance)

print('\n--- the roll-up is reported so the total is explicable ---')
r = c.get('/api/plaid/accounts').get_json()
roll = [x for x in (r.get('rollups') or []) if x['id'] == 11]
check('it is listed as a roll-up', len(roll) == 1, r.get('rollups'))
check('naming all three', len(roll[0]['accounts']) == 3, roll)
obs = {o['key']: o for o in c.get('/api/finance/overview').get_json()['observations']}
key = [k for k in obs if k.startswith('link_rollup')]
check('and surfaced on the overview as a note, not a warning',
      bool(key) and obs[key[0]]['severity'] == 'note', list(obs))

print('\n--- a bank that reports no balance must not zero a real one ---')
with app.app_context():
    for pv in A.PlaidAccount.query.filter(A.PlaidAccount.account_id.like('v-%')).all():
        pv.current_balance = None
    db.session.commit()
    A._apply_plaid_balance(A.PlaidAccount.query.filter_by(account_id='v-main').first())
    db.session.commit()
    check('the record keeps its money',
          float(A.FinanceAccount.query.get(11).balance) == 151.49,
          A.FinanceAccount.query.get(11).balance)

print('\n--- linking refuses what it should ---')
check('an unknown debt is a 404',
      c.put('/api/plaid/accounts/%d/link' % accts['Freedom Visa']['id'],
            json={'kind': 'debt', 'id': 9999}).status_code == 404)
check('an invented kind is a 400',
      c.put('/api/plaid/accounts/%d/link' % accts['Freedom Visa']['id'],
            json={'kind': 'sideways', 'id': 21}).status_code == 400)
check('an unknown plaid account is a 404',
      c.put('/api/plaid/accounts/9999/link', json={'kind': 'debt', 'id': 20}).status_code == 404)
r = c.put('/api/plaid/accounts/%d/link' % accts['Prime Visa']['id'], json={'kind': ''})
check('unlinking works', r.get_json()['account']['linked_debt_id'] is None, r.get_json())
c.put('/api/plaid/accounts/%d/link' % accts['Prime Visa']['id'], json={'kind': 'debt', 'id': 20})

print('\n--- deposits are kept, and told apart by the account they landed in ---')
check('all three were recorded, not discarded', result['skipped_income'] == 3, result)
d = c.get('/api/finance/deposits').get_json()
kinds = {x['description']: x['kind'] for x in d['deposits']}
check('the paycheck into checking is income', kinds['ACME PAYROLL'] == 'income', kinds)
check('the Prime autopay is a card payment, NOT income',
      kinds['AUTOPAY THANK YOU'] == 'card_payment', kinds)
check('same for Freedom', kinds['PAYMENT THANK YOU'] == 'card_payment', kinds)
check('amounts are stored positive, not as negative deposits',
      all(x['amount'] > 0 for x in d['deposits']), d['deposits'])
check('each says which account it hit',
      any(x['account_name'] and '4321' in x['account_name'] for x in d['deposits']),
      [x['account_name'] for x in d['deposits']])
with app.app_context():
    check('and none of them leaked into the spending ledger',
          A.SpendTransaction.query.filter(A.SpendTransaction.amount < 0).count() == 0)
    check('spending only counts the four real purchases',
          A.SpendTransaction.query.filter_by(source='plaid').count() == 4)

print('\n--- deposits are measured against the income estimate ---')
with app.app_context():
    rec = A._income_reconciliation(1)
check('card payments are excluded from income',
      rec['by_kind']['card_payment']['count'] == 2, rec['by_kind'])
check('only the paycheck counts', rec['counted_deposits'] == 1, rec)
check('an expectation exists to compare against', rec['has_estimate'] is True)
check('the expectation is take-home, NOT the gross salary -- IncomeSource.net_monthly()',
      0 < rec['expected_monthly_net'] < rec['gross_monthly'],
      (rec['expected_monthly_net'], rec['gross_monthly'], rec['expected_basis']))
check('and it says what basis it used, now that FICA and benefits are modelled',
      rec['expected_basis'] == 'take-home after tax, FICA, benefits and retirement',
      rec['expected_basis'])
check('gross is reported alongside so the deduction is visible',
      rec['gross_monthly'] == round(104000 / 12.0, 2), rec['gross_monthly'])
check('a variance is reported', rec['variance'] is not None, rec)
check('and as a percentage', rec['variance_pct'] is not None, rec)

print('\n--- a deposit can be attributed to the source it came from ---')
dep = [x for x in d['deposits'] if x['description'] == 'ACME PAYROLL'][0]
r = c.put('/api/finance/deposits/%d/attribute' % dep['id'], json={'income_source_id': 30})
check('attribution accepted', r.status_code == 200 and r.get_json()['deposit']['income_source_id'] == 30,
      r.get_json())
check('an unknown source is refused',
      c.put('/api/finance/deposits/%d/attribute' % dep['id'],
            json={'income_source_id': 9999}).status_code == 404)
r = c.put('/api/finance/deposits/%d/attribute' % dep['id'], json={'income_source_id': None})
check('and it can be cleared', r.get_json()['deposit']['income_source_id'] is None)

print('\n--- re-syncing does not duplicate anything ---')
FAKE.pages = []
with app.app_context():
    before_accounts = A.PlaidAccount.query.count()
    item = A.PlaidItem.query.get(1)
    again = A._plaid_sync_item(item)
    db.session.commit()
    # The three from accounts_get, plus the investment one and the three vaults added by
    # the fixtures above — counted rather than hardcoded so adding a case does not break it.
    check('no new accounts', A.PlaidAccount.query.count() == before_accounts,
          (before_accounts, A.PlaidAccount.query.count()))
    check('no new deposits', A.PlaidDeposit.query.count() == 3, A.PlaidDeposit.query.count())
    check('no new transactions', A.SpendTransaction.query.count() == 4)
    check('but balances were refreshed again', again['accounts'] == 3, again)
    check('and the link survived a re-sync',
          A.PlaidAccount.query.filter_by(account_id='acc-prime').first().linked_debt_id == 20)

print('\n--- an investment account links to the portfolio, not to a FinanceAccount ---')
with app.app_context():
    db.session.add(A.PortfolioAccount(id=50, user_id=1, name='Sofi', cash_balance=9.65))
    db.session.flush()
    db.session.add(A.Portfolio(user_id=1, account_id=50, symbol='VOO', asset_type='etf', quantity=40,
                               average_cost=400.0, current_price=500.0))
    inv = A.PlaidAccount(user_id=1, item_id=1, account_id='acc-inv',
                         name='SoFi Self-directed', mask='5930', type='investment',
                         subtype='brokerage', current_balance=31546.27)
    db.session.add(inv)
    db.session.commit()
    inv_id = inv.id

r = c.get('/api/plaid/accounts').get_json()
check('portfolio accounts are offered at all', 'portfolios' in r['linkable'], list(r['linkable']))
check('and the one being managed is in the list',
      any(x['name'] == 'Sofi' for x in r['linkable']['portfolios']), r['linkable']['portfolios'])
check('its value is holdings plus cash, not cash alone',
      r['linkable']['portfolios'][0]['value'] == round(9.65 + 40 * 500.0, 2),
      r['linkable']['portfolios'][0])
inv_row = [a for a in r['accounts'] if a['id'] == inv_id][0]
check('the plaid account is marked as an investment', inv_row['is_investment'] is True, inv_row)
check('and not as credit', inv_row['is_credit'] is False)

rr = c.put('/api/plaid/accounts/%d/link' % inv_id, json={'kind': 'portfolio', 'id': 50})
check('linking to a portfolio is accepted', rr.status_code == 200, rr.get_json())
check('an unknown portfolio is refused',
      c.put('/api/plaid/accounts/%d/link' % inv_id,
            json={'kind': 'portfolio', 'id': 9999}).status_code == 404)
with app.app_context():
    check('the portfolio cash was NOT overwritten by the bank balance',
          float(A.PortfolioAccount.query.get(50).cash_balance) == 9.65)
    check('and the holding is untouched',
          A.Portfolio.query.filter_by(account_id=50).count() == 1)
r = c.get('/api/plaid/accounts').get_json()
inv_row = [a for a in r['accounts'] if a['id'] == inv_id][0]
check('the two are compared instead', inv_row['portfolio_value'] == 20009.65, inv_row)
check('and the gap is reported',
      inv_row['portfolio_variance'] == round(31546.27 - 20009.65, 2), inv_row)

print('\n--- backfill replays history the cursor has already passed ---')
# The situation this exists for: deposits that arrived while the app was discarding them are
# behind the cursor, and an ordinary sync will never offer them again.
with app.app_context():
    A.PlaidDeposit.query.delete()
    # A category the user fixed by hand. A replay must not undo that.
    t = A.SpendTransaction.query.filter_by(external_id='plaid:t1').first()
    t.category = 'entertainment'
    t.notes = 'recategorised by hand'
    db.session.commit()
    before_txns = A.SpendTransaction.query.count()

FAKE.pages = [{
    'added': [
        txn('t1', 'acc-prime', 51.20, 'STARBUCKS'),          # already have it
        txn('t8', 'acc-chk', 42.00, 'OLD PURCHASE', day_offset=200),   # missed before
        txn('t5', 'acc-chk', -2400.00, 'ACME PAYROLL', pfc='INCOME'),  # the lost deposit
    ],
    'modified': [], 'removed': [], 'next_cursor': 'cur-backfill', 'has_more': False,
}]
r = c.post('/api/plaid/items/1/backfill')
res = r.get_json()
check('backfill runs', r.status_code == 200, res)
check('it reports itself as one', res.get('backfill') is True, res)
check('the lost deposit is recovered', res['skipped_income'] == 1, res)
check('a genuinely missing transaction is added', res['added'] == 1, res)
check('one already held is left alone, not rewritten', res['unchanged'] == 1, res)
check('nothing needed re-attributing here', res.get('attributed') == 0, res)
check('and it did not run out of pages', res.get('truncated') is False, res)
with app.app_context():
    check('the hand-set category survived the replay',
          A.SpendTransaction.query.filter_by(external_id='plaid:t1').first().category
          == 'entertainment')
    check('as did the note',
          A.SpendTransaction.query.filter_by(external_id='plaid:t1').first().notes
          == 'recategorised by hand')
    check('the deposit is back', A.PlaidDeposit.query.count() == 1)
    check('and nothing was duplicated',
          A.SpendTransaction.query.count() == before_txns + 1,
          (before_txns, A.SpendTransaction.query.count()))

print('\n--- backfill fills an EMPTY account id, which is a gap and not a choice ---')
# Rows imported before plaid_account_id existed have none. Leaving them alone on a replay
# meant the account breakout applied to nothing but the newest transactions — 165 of 238
# rows unattributed on the real data.
with app.app_context():
    old_row = A.SpendTransaction.query.filter_by(external_id='plaid:t1').first()
    old_row.plaid_account_id = None
    old_row.category = 'entertainment'          # a hand edit that must survive
    db.session.commit()
FAKE.pages = [{
    'added': [txn('t1', 'acc-prime', 51.20, 'STARBUCKS')],
    'modified': [], 'removed': [], 'next_cursor': 'c', 'has_more': False,
}]
res3 = c.post('/api/plaid/items/1/backfill').get_json()
check('the missing attribution is filled in', res3.get('attributed') == 1, res3)
with app.app_context():
    row = A.SpendTransaction.query.filter_by(external_id='plaid:t1').first()
    check('the row now knows its account', row.plaid_account_id == 'acc-prime',
          row.plaid_account_id)
    check('but the hand-set category is STILL untouched', row.category == 'entertainment',
          row.category)

print('\n--- and running it twice finds nothing new ---')
FAKE.pages = [{
    'added': [txn('t1', 'acc-prime', 51.20, 'STARBUCKS'),
              txn('t8', 'acc-chk', 42.00, 'OLD PURCHASE', day_offset=200),
              txn('t5', 'acc-chk', -2400.00, 'ACME PAYROLL', pfc='INCOME')],
    'modified': [], 'removed': [], 'next_cursor': 'cur-backfill', 'has_more': False,
}]
res2 = c.post('/api/plaid/items/1/backfill').get_json()
check('a second run adds nothing', res2['added'] == 0, res2)
check('it just recognises what it already has', res2['unchanged'] == 2, res2)
with app.app_context():
    check('deposits are not duplicated either', A.PlaidDeposit.query.count() == 1)

print('\n--- the overview picks it up ---')
obs = {o['key']: o for o in c.get('/api/finance/overview').get_json()['observations']}
check('an income variance this large is raised', 'income_variance' in obs, list(obs))
with app.app_context():
    pic = A._finance_full_picture(1)
    check('utilization now uses the refreshed limit',
          pic['credit']['utilization']['total_limit'] >= 27000.0,
          pic['credit']['utilization'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID ACCOUNT CHECKS PASSED')
