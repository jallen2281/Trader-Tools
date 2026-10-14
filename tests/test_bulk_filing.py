"""Unfiled rows stay findable, and can be filed in bulk.

Three faults that compounded into one complaint: "$6,310 in unassigned expenses I can't
locate".

  1. THE DEFAULT BOOK HID THEM. Adding a fallback book meant the ledger's book_id was
     never empty again, so the "No book" filter matched nothing. The default made unfiled
     spending invisible instead of solving it -- strictly worse than leaving it unfiled,
     because at least an empty book could be searched for.

  2. FILING WAS ONE ROW AT A TIME. Everything that syncs arrives unfiled, so the backlog
     grows by a month every month, and nobody opens sixty modals.

  3. A WAREHOUSE CLUB IS NOT A GROCER. The fallback name rule forced anything matching
     "costco" or "walmart" to 'food'. Both sell fuel under the same merchant name, so a
     tank of petrol landed in the grocery budget whenever Plaid had no category of its own.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-bulk-filing')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, Entity, SpendTransaction, PlaidDeposit

UID = 1
TODAY = date.today()


def cli():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    return c


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='bulk@x.com', name='Bulk',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()
    farm = Entity(user_id=UID, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    home = Entity(user_id=UID, name='Personal finance', kind='personal')
    db.session.add_all([farm, home])
    db.session.commit()

    print('--- a warehouse club is not a grocer ---')
    check("'costco' is no longer forced to food",
          A._guess_spend_category('Costco') != 'food', A._guess_spend_category('Costco'))
    check('nor is costco gas', A._guess_spend_category('COSTCO GAS') != 'food',
          A._guess_spend_category('COSTCO GAS'))
    check("'walmart' likewise", A._guess_spend_category('Walmart') != 'food',
          A._guess_spend_category('Walmart'))
    check('a real grocer still is', A._guess_spend_category('Kroger') == 'food')
    check('a filling station still is transportation',
          A._guess_spend_category('Sunoco') == 'transportation')

    filed = SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=2),
                             description='Feed', merchant='Tractor Supply',
                             category='farm_feed', amount=120.00, entity_id=farm.id)
    unfiled = [SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=i),
                                description='Fuel', merchant='Costco',
                                category='other', amount=60.00 + i)
               for i in range(1, 5)]
    dep = PlaidDeposit(user_id=UID, external_id='plaid:x1', posted_at=TODAY,
                       description='Egg money', merchant='Cash', amount=75.00, kind='income')
    db.session.add_all([filed] + unfiled + [dep])
    db.session.commit()

    print('\n--- unfiled rows are findable, with or without a default ---')
    def not_filed():
        r = cli().get('/api/finance/ledger?month=%s&book=none' % TODAY.strftime('%Y-%m'))
        return r.get_json()['rows']

    check('found before a default exists', len(not_filed()) == 5, len(not_filed()))
    cli().put('/api/finance/default-book', json={'entity_id': home.id})
    after = not_filed()
    check('and still found once a default is set', len(after) == 5, len(after))
    check('the filed one is not among them',
          all((r.get('merchant') or '') != 'Tractor Supply' for r in after),
          [r.get('merchant') for r in after])
    # The regression this guards: the fallback made book_id always truthy.
    check('they do show the default book', all(r['book'] == 'Personal finance' for r in after),
          [r['book'] for r in after])
    check('but are flagged as filed by assumption',
          all(r['book_default'] for r in after), [r['book_default'] for r in after])

    print('\n--- filing many at once ---')
    ids = [t.id for t in unfiled]
    r = cli().post('/api/finance/transactions/bulk',
                   json={'spend_ids': ids, 'entity_id': farm.id, 'category': 'transportation'})
    check('the call succeeds', r.status_code == 200, (r.status_code, r.get_json()))
    check('every row is counted', r.get_json()['changed'] == 4, r.get_json())
    rows = SpendTransaction.query.filter(SpendTransaction.id.in_(ids)).all()
    check('all moved to the chosen book', all(t.entity_id == farm.id for t in rows))
    check('and the chosen category', all(t.category == 'transportation' for t in rows))
    check('they drop off the unfiled list', len(not_filed()) == 1, len(not_filed()))

    print('\n--- book and category are independent ---')
    solo = SpendTransaction(user_id=UID, posted_at=TODAY, description='Thing',
                            merchant='Shop', category='other', amount=10.00)
    db.session.add(solo)
    db.session.commit()
    cli().post('/api/finance/transactions/bulk', json={'spend_ids': [solo.id], 'category': 'personal'})
    db.session.refresh(solo)
    check('a category-only change leaves the book alone',
          solo.category == 'personal' and solo.entity_id is None, (solo.category, solo.entity_id))
    cli().post('/api/finance/transactions/bulk', json={'spend_ids': [solo.id], 'entity_id': home.id})
    db.session.refresh(solo)
    check('a book-only change leaves the category alone',
          solo.entity_id == home.id and solo.category == 'personal', (solo.entity_id, solo.category))

    print('\n--- income can be filed too ---')
    r = cli().post('/api/finance/transactions/bulk',
                   json={'deposit_ids': [dep.id], 'entity_id': farm.id})
    check('a deposit takes a book', r.status_code == 200 and r.get_json()['changed'] == 1,
          r.get_json())
    db.session.refresh(dep)
    check('and it sticks', dep.entity_id == farm.id, dep.entity_id)

    print('\n--- a request that would do nothing says so ---')
    check('no rows is a 400',
          cli().post('/api/finance/transactions/bulk', json={'spend_ids': []}).status_code == 400)
    check('no change is a 400',
          cli().post('/api/finance/transactions/bulk',
                     json={'spend_ids': [solo.id]}).status_code == 400)
    check('an unknown category is a 400',
          cli().post('/api/finance/transactions/bulk',
                     json={'spend_ids': [solo.id], 'category': 'wombat'}).status_code == 400)
    check('an unknown book is a 404',
          cli().post('/api/finance/transactions/bulk',
                     json={'spend_ids': [solo.id], 'entity_id': 9999}).status_code == 404)

    print('\n--- a card payment outranks Plaid; a transfer to a person does not ---')
    # Plaid classifies a credit-card payment as LOAN_PAYMENTS, which this app maps to
    # 'debt' -- spending. So the payment counted AND the purchases it settled counted
    # again when the card was used. These wordings have to beat Plaid's own category.
    for name in ('PAYMENT TO CHASE CARD ENDING IN 4807', 'AMEX EPAYMENT',
                 'Payment Thank You-Mobile', 'CITI AUTOPAY', 'MOBILE PAYMENT - THANK YOU'):
        check('card payment recognised: %s' % name[:28], A._looks_like_card_payment(name), name)

    # The general transfer words must NOT get that precedence. "Online Transfer to
    # CHK ...08" was repaying a family member on the household this came from -- real
    # spending wearing a transfer's clothes. Promoting it would hide it.
    for name in ('Online Transfer to CHK ...08', 'Zelle Payment to Jeff Allen',
                 'To Savings - 3808', 'Kroger', 'Costco Gas'):
        check('not treated as a card payment: %s' % name[:28],
              not A._looks_like_card_payment(name), name)

    # and the ordinary rules still behave
    check('a card payment still reads as a transfer by name',
          A._guess_spend_category('AMEX EPAYMENT') == 'transfer')
    check('a payment to a person does not read as spending-free',
          A._guess_spend_category('Zelle Payment to Jeff Allen') != 'transfer',
          A._guess_spend_category('Zelle Payment to Jeff Allen'))

    print('\n--- a category a person chose survives the next sync ---')
    # Plaid re-sends a transaction in `modified` whenever it goes from pending to posted
    # or the merchant name gets enriched, and the ordinary sync path rewrote the category
    # every time. A hand-correction lasted until the next routine update, silently.
    hand = SpendTransaction(user_id=UID, posted_at=TODAY, description='Fuel',
                            merchant='Costco', category='other', amount=58.00,
                            source='plaid', external_id='plaid:costco-gas-1')
    db.session.add(hand)
    db.session.commit()
    check('a fresh row is not locked', not hand.category_locked)

    cli().post('/api/finance/transactions/bulk',
               json={'spend_ids': [hand.id], 'category': 'transportation'})
    db.session.refresh(hand)
    check('filing it by hand locks it', hand.category_locked is True)
    check('and sets what was asked for', hand.category == 'transportation', hand.category)

    # what the sync does on a `modified` for this row
    guessed = A._guess_spend_category('Costco Fuel')
    if not hand.category_locked:
        hand.category = guessed
    db.session.commit()
    db.session.refresh(hand)
    check('a later sync leaves it alone', hand.category == 'transportation',
          (hand.category, guessed))

    # an untouched row still takes the bank's improved category
    auto = SpendTransaction(user_id=UID, posted_at=TODAY, description='Shop',
                            merchant='Kroger', category='other', amount=20.00,
                            source='plaid', external_id='plaid:kroger-1')
    db.session.add(auto)
    db.session.commit()
    if not auto.category_locked:
        auto.category = A._guess_spend_category('Kroger')
    db.session.commit()
    db.session.refresh(auto)
    check('a row nobody touched still updates', auto.category == 'food', auto.category)

    print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BULK FILING CHECKS PASSED')
