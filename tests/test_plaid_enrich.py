"""The one Plaid call billed per transaction, and the two gates in front of it.

Every other product on this install is a flat subscription: six linked institutions at
$0.30 each, and a sync that runs every six hours costs exactly the same as one that never
runs at all. Enrich is not like that. At $2.00 per thousand, the number of rows IS the
bill, which makes a loop over the ledger the only way this app can spend real money by
accident.

So there are two gates, and they are independent on purpose:

  * DRY RUN BY DEFAULT. Asking what the backlog is and what clearing it would cost calls
    Plaid not at all, so the question is always free to ask.
  * `apply: true` still refuses unless PLAID_ENRICH_ENABLED is set. A flag alone would be
    one typo from an invoice; a default alone would make the cost invisible until after
    it was spent.

And a hard cap of 500 rows a call, which is a cap rather than a warning because the
failure being guarded against is automation, and automation does not read warnings.

What it may touch is deliberately narrow. Rows that arrived through /transactions/sync
already carry a personal_finance_category covered by the per-item subscription, so paying
to classify them again buys the same answer twice. Rows filed anywhere other than 'other'
represent somebody's decision, possibly a hand correction, and this is not the place to
overrule one.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='enrich_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'e.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['TT_BACKGROUND_JOBS'] = '0'
sys.path.insert(0, os.getcwd())

from cryptography.fernet import Fernet            # noqa: E402
os.environ['PLAID_ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from datetime import date, timedelta              # noqa: E402

import app as A                                    # noqa: E402
import plaid_client as pc                          # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
UID = 1


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


# ----------------------------------------------------------------- pure request shaping
print('\n--- the price is quotable before anything is spent ---')
check('54 rows is 11 cents', pc.enrich_cost(54) == 0.11, pc.enrich_cost(54))
check('a thousand is exactly two dollars', pc.enrich_cost(1000) == 2.0, pc.enrich_cost(1000))
check('nothing costs nothing', pc.enrich_cost(0) == 0.0)
check('and a part-cent rounds UP, never down -- an estimate that understates is worse '
      'than useless', pc.enrich_cost(1) == 0.01, pc.enrich_cost(1))

print('\n--- one signed amount becomes an amount plus a direction ---')
req = pc.enrich_request([{'id': 5, 'description': 'MUDFLAP', 'amount': 174.70},
                         {'id': 6, 'description': 'WALMART REFUND', 'amount': -9.48}])
out = req['transactions']
check('money leaving is an OUTFLOW with a positive amount',
      (out[0]['direction'], out[0]['amount']) == ('OUTFLOW', 174.7), out[0])
check('money arriving is an INFLOW, and the sign is dropped not negated',
      (out[1]['direction'], out[1]['amount']) == ('INFLOW', 9.48), out[1])
check('ids are strings, because that is how the response keys them',
      out[0]['id'] == '5', out[0]['id'])
check('account_type applies to the whole request', req['account_type'] == 'depository')

print('\n--- an answer Plaid could not give is absent, not blank ---')
got = pc.enrichment_rows({'enriched_transactions': [
    {'id': '5', 'enrichments': {'merchant_name': 'Mudflap',
                                'personal_finance_category': {
                                    'primary': 'TRANSPORTATION',
                                    'detailed': 'TRANSPORTATION_GAS'}}},
    {'id': '6', 'enrichments': {'personal_finance_category': {'primary': 'INCOME'}}},
    {'id': '7', 'enrichments': {}},
    {'id': '8'}]})
check('the row it placed comes back', got['5']['category'] == 'transportation', got.get('5'))
check('with the merchant', got['5']['merchant'] == 'Mudflap')
check('an INCOME row is dropped -- that belongs to the income module, not this ledger',
      '6' not in got, sorted(got))
check('a row with no category is dropped rather than returned empty',
      '7' not in got and '8' not in got, sorted(got))
check('so the caller can never blank a real category with a non-answer', sorted(got) == ['5'])

check('the electric bill is still utilities, through the shared mapping',
      pc.enrichment_rows({'enriched_transactions': [{'id': '1', 'enrichments': {
          'personal_finance_category': {
              'primary': 'RENT_AND_UTILITIES',
              'detailed': 'RENT_AND_UTILITIES_GAS_AND_ELECTRICITY'}}}]})['1']['category']
      == 'utilities')
check('and the mortgage is housing',
      pc.enrichment_rows({'enriched_transactions': [{'id': '1', 'enrichments': {
          'personal_finance_category': {
              'primary': 'RENT_AND_UTILITIES',
              'detailed': 'RENT_AND_UTILITIES_MORTGAGE'}}}]})['1']['category'] == 'housing')


# ------------------------------------------------------------------ against the database
class FakeEnrich:
    """Returns a category for every id it is given, and counts what it was billed for."""

    def __init__(self, raises=None):
        self.seen = []
        self.raises = raises
        self.calls = 0

    def transactions_enrich(self, transactions, account_type='depository'):
        self.calls += 1
        if self.raises:
            raise self.raises
        self.seen.extend(t['id'] for t in transactions)
        return {'enriched_transactions': [
            {'id': t['id'], 'enrichments': {
                'merchant_name': 'Resolved Co',
                'personal_finance_category': {'primary': 'FOOD_AND_DRINK',
                                              'detailed': 'FOOD_AND_DRINK_GROCERIES'}}}
            for t in transactions]}


TODAY = date.today()
with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.FinanceAccount(id=1, user_id=UID, name='Chase', type='checking',
                                    balance=1000.0))
    rows = [
        # Candidates: unfiled, and never carried a Plaid category.
        (1, 'csv', 'other', 'MUDFLAP 1234', 174.70),
        (2, 'csv', None, 'SOME SHOP', 22.10),
        (3, 'manual', '', 'CASH THING', 40.00),
        # Not candidates.
        (4, 'plaid', 'other', 'ALREADY PAID FOR', 55.00),
        (5, 'csv', 'food', 'FILED BY HAND', 18.00),
        (6, 'csv', 'transportation', 'ALSO FILED', 61.00),
    ]
    for tid, src, cat, desc, amt in rows:
        db.session.add(A.SpendTransaction(
            id=tid, user_id=UID, account_id=1, source=src, category=cat,
            description=desc, amount=amt, posted_at=TODAY - timedelta(days=tid)))
    # Another household member's row must not be swept up in a bulk write.
    db.session.add(A.User(id=2, google_id='g2', email='you@x.com', name='You', role='user',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.SpendTransaction(id=7, user_id=2, source='csv', category='other',
                                      description='NOT MINE', amount=9.0, posted_at=TODAY))
    db.session.commit()

print('\n--- the dry run is free, and says what it would cost ---')
with app.app_context():
    c = client_for(UID)
    r = c.post('/api/finance/spend/enrich', json={})
    body = r.get_json()
    check('200', r.status_code == 200, (r.status_code, body))
    check('it says it did nothing', body.get('dry_run') is True, body)
    check('three candidates -- not the plaid row, not the two already filed',
          body.get('candidates') == 3, body.get('candidates'))
    check('it quotes the price up front', body.get('estimated_cost') == 0.01, body)
    check('and the rate, so the number can be checked',
          '2.00 per 1000' in (body.get('rate') or ''), body.get('rate'))
    check('it reports that applying is currently switched off',
          body.get('enabled') is False, body.get('enabled'))
    check('a sample is included so the rows can be eyeballed first',
          len(body.get('sample') or []) == 3, body.get('sample'))
    check('another user\'s row is not in it',
          'NOT MINE' not in str(body.get('sample')), body.get('sample'))

print('\n--- applying refuses while the flag is off, and still costs nothing ---')
with app.app_context():
    c = client_for(UID)
    fake = FakeEnrich()
    A._plaid = lambda: fake
    r = c.post('/api/finance/spend/enrich', json={'apply': True})
    check('403, not a silent no-op', r.status_code == 403, r.status_code)
    check('and it names the switch',
          'PLAID_ENRICH_ENABLED' in (r.get_json() or {}).get('error', ''), r.get_json())
    check('it still tells you the size of the job',
          r.get_json().get('candidates') == 3, r.get_json())
    check('NOTHING WAS CALLED', fake.calls == 0, fake.calls)
    with app.app_context():
        check('and nothing was recategorized',
              db.session.get(A.SpendTransaction, 1).category == 'other')

print('\n--- with the flag on, only the right rows are touched ---')
with app.app_context():
    saved = A.Config.PLAID_ENRICH_ENABLED
    A.Config.PLAID_ENRICH_ENABLED = True
    try:
        c = client_for(UID)
        fake = FakeEnrich()
        A._plaid = lambda: fake
        r = c.post('/api/finance/spend/enrich', json={'apply': True})
        body = r.get_json()
        check('200', r.status_code == 200, (r.status_code, body))
        check('three rows were billed for', body.get('billed_rows') == 3, body)
        check('and three changed', body.get('applied') == 3, body)
        check('the spend is reported', body.get('spent') == 0.01, body)
        check('the diff names each row, not just a count',
              sorted(x['id'] for x in body['changes']) == [1, 2, 3], body['changes'])
        check('and says what it moved from and to',
              body['changes'][0]['from'] in ('other', None, '')
              and body['changes'][0]['to'] == 'food', body['changes'][0])
        with app.app_context():
            check('the unfiled rows are filed',
                  db.session.get(A.SpendTransaction, 1).category == 'food')
            check('THE PLAID ROW WAS NEVER SENT -- its category is already paid for',
                  '4' not in fake.seen and
                  db.session.get(A.SpendTransaction, 4).category == 'other', fake.seen)
            check('A ROW FILED BY HAND IS NOT OVERRULED',
                  db.session.get(A.SpendTransaction, 5).category == 'food'
                  and '5' not in fake.seen, fake.seen)
            check('and the other household member is untouched',
                  db.session.get(A.SpendTransaction, 7).category == 'other')
            check('the merchant was filled in while it was empty',
                  db.session.get(A.SpendTransaction, 1).merchant == 'Resolved Co')
    finally:
        A.Config.PLAID_ENRICH_ENABLED = saved

print('\n--- a merchant the user typed is not replaced by a guess ---')
with app.app_context():
    saved = A.Config.PLAID_ENRICH_ENABLED
    A.Config.PLAID_ENRICH_ENABLED = True
    try:
        t = A.SpendTransaction(id=10, user_id=UID, account_id=1, source='csv',
                               category='other', description='X', amount=5.0,
                               merchant='Mine, typed by hand', posted_at=TODAY)
        db.session.add(t)
        db.session.commit()
        fake = FakeEnrich()
        A._plaid = lambda: fake
        client_for(UID).post('/api/finance/spend/enrich', json={'apply': True})
        with app.app_context():
            check('the typed merchant survives',
                  db.session.get(A.SpendTransaction, 10).merchant == 'Mine, typed by hand',
                  db.session.get(A.SpendTransaction, 10).merchant)
            check('though the category was still filed',
                  db.session.get(A.SpendTransaction, 10).category == 'food')
    finally:
        A.Config.PLAID_ENRICH_ENABLED = saved

print('\n--- the cap is a cap, not a suggestion ---')
with app.app_context():
    c = client_for(UID)
    r = c.post('/api/finance/spend/enrich', json={'limit': 100000})
    check('an absurd limit is clamped to the hard cap',
          r.get_json().get('limit') == A.ENRICH_HARD_CAP, r.get_json().get('limit'))
    check('and the cap is reported so the ceiling is visible',
          r.get_json().get('hard_cap') == 500, r.get_json())
    check('the cap is worth exactly one dollar at this rate',
          pc.enrich_cost(A.ENRICH_HARD_CAP) == 1.0, pc.enrich_cost(A.ENRICH_HARD_CAP))
    r = c.post('/api/finance/spend/enrich', json={'limit': 0})
    check('zero is floored to one, never to unlimited',
          r.get_json().get('limit') == 1, r.get_json().get('limit'))
    r = c.post('/api/finance/spend/enrich', json={'limit': 'lots'})
    check('a non-number is refused rather than coerced', r.status_code == 400, r.status_code)

print('\n--- a failure part-way through stops, and keeps what it paid for ---')
with app.app_context():
    saved = A.Config.PLAID_ENRICH_ENABLED
    A.Config.PLAID_ENRICH_ENABLED = True
    try:
        for tid in (20, 21):
            db.session.add(A.SpendTransaction(
                id=tid, user_id=UID, account_id=1, source='csv', category='other',
                description='PENDING %d' % tid, amount=1.0, posted_at=TODAY))
        db.session.commit()
        fake = FakeEnrich(raises=pc.PlaidError('rate limited', code='RATE_LIMIT'))
        A._plaid = lambda: fake
        r = client_for(UID).post('/api/finance/spend/enrich', json={'apply': True})
        check('502, with the reason', r.status_code == 502, r.status_code)
        check('it reports what it had already spent',
              r.get_json().get('spent') == 0.0, r.get_json())
        check('and the error code is passed through',
              r.get_json().get('code') == 'RATE_LIMIT', r.get_json())
        with app.app_context():
            check('nothing was half-written', db.session.get(A.SpendTransaction, 20).category
                  == 'other')
    finally:
        A.Config.PLAID_ENRICH_ENABLED = saved

print('\n--- an empty backlog is not an error ---')
with app.app_context():
    saved = A.Config.PLAID_ENRICH_ENABLED
    A.Config.PLAID_ENRICH_ENABLED = True
    try:
        A.SpendTransaction.query.filter(
            A.SpendTransaction.user_id == UID,
            A.SpendTransaction.category.in_(['other', ''])).delete(synchronize_session=False)
        A.SpendTransaction.query.filter(
            A.SpendTransaction.user_id == UID,
            A.SpendTransaction.category.is_(None)).delete(synchronize_session=False)
        db.session.commit()
        fake = FakeEnrich()
        A._plaid = lambda: fake
        r = client_for(UID).post('/api/finance/spend/enrich', json={'apply': True})
        check('200 with nothing done', r.status_code == 200 and r.get_json()['applied'] == 0,
              r.get_json())
        check('and Plaid was never called for an empty list', fake.calls == 0, fake.calls)
    finally:
        A.Config.PLAID_ENRICH_ENABLED = saved

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL ENRICH CHECKS PASSED')
