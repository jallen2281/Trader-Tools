"""Receipts reconciled against the bank feed.

A card purchase can arrive twice: once as a photographed receipt and once from the bank. The
last four digits are what make them resolvable — two connected Visas are indistinguishable
by amount alone, and a last4 belonging to no connected card is positive evidence the
purchase is not in the feed at all rather than a failure to find it.

Attaching the receipt to the bank's own row, instead of creating a second transaction, kills
the double AND leaves the paper trail on the transaction that actually settled.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='rcpt_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'r.db').replace(os.sep, '/')
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


def bank(tid, acct, amount, name, days_ago=0):
    return A.SpendTransaction(user_id=1, external_id='plaid:%s' % tid, source='plaid',
                              plaid_account_id=acct, amount=amount, description=name,
                              merchant=name, category='other',
                              posted_at=TODAY - timedelta(days=days_ago))


def receipt(did, amount, merchant, last4=None, days_ago=0, deductible=False):
    return A.TaxDocument(id=did, user_id=1, doc_type='receipt', filename='r%d.jpg' % did,
                         content_type='image/jpeg', amount=amount, merchant=merchant,
                         card_last4=last4, purchase_date=TODAY - timedelta(days=days_ago),
                         category='other', deductible=deductible,
                         uploaded_at=A.datetime.utcnow())


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.PlaidItem(id=1, user_id=1, item_id='it', access_token_enc=b'x',
                               institution_name='Amex'))
    db.session.add_all([
        A.PlaidAccount(user_id=1, item_id=1, account_id='acc-amex', name='Amex',
                       mask='2001', type='credit', subtype='credit card'),
        A.PlaidAccount(user_id=1, item_id=1, account_id='acc-visa', name='Prime Visa',
                       mask='4831', type='credit', subtype='credit card'),
    ])
    db.session.add_all([
        bank('b1', 'acc-amex', 89.97, 'HOME DEPOT', days_ago=2),
        bank('b2', 'acc-visa', 12.50, 'STARBUCKS', days_ago=1),
        bank('b3', 'acc-visa', 40.00, 'SHELL', days_ago=1),
        bank('b4', 'acc-visa', 40.00, 'SHELL', days_ago=3),
    ])
    db.session.add_all([
        receipt(2, 89.97, 'Home Depot', last4='2001', days_ago=2, deductible=True),
        receipt(3, 12.50, 'Starbucks', last4=None, days_ago=1),
        receipt(4, 40.00, 'Shell', last4='4831', days_ago=2),      # equidistant: ambiguous
        receipt(5, 63.20, 'Cash Hardware', last4='9999', days_ago=1),   # unconnected card
        receipt(6, 250.00, 'Old Thing', last4='2001', days_ago=90),     # outside the window
    ])
    db.session.commit()

c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True

print('\n--- importing receipts no longer creates a second transaction ---')
r = c.post('/api/finance/transactions/import-receipts').get_json()
check('the ones the bank already has are matched, not imported',
      r['matched_to_bank'] == 2, r)
check('and the rest still import normally', r['imported'] == 3, r)
with app.app_context():
    check('no duplicate row was created for the Home Depot purchase',
          A.SpendTransaction.query.filter_by(external_id='receipt:2').first() is None)
    b1 = A.SpendTransaction.query.filter_by(external_id='plaid:b1').first()
    check('the receipt is attached to the bank transaction instead', b1.tax_document_id == 2,
          b1.tax_document_id)
    check('the ledger holds four bank rows plus three unmatched receipts',
          A.SpendTransaction.query.count() == 7, A.SpendTransaction.query.count())

print('\n--- the card digits decide which account, not just the amount ---')
with app.app_context():
    doc = A.TaxDocument.query.get(2)
    m, why = A._match_receipt_to_bank(doc, 1)
    check('a receipt on the Amex matches the Amex row', m.plaid_account_id == 'acc-amex',
          (m.plaid_account_id, why))
    doc.card_last4 = '4831'
    m, why = A._match_receipt_to_bank(doc, 1)
    check('the same amount on a DIFFERENT card does not match', m is None, (m, why))
    doc.card_last4 = '2001'

print('\n--- a card that is not connected is a definite answer ---')
with app.app_context():
    m, why = A._match_receipt_to_bank(A.TaxDocument.query.get(5), 1)
    check('no match is attempted', m is None)
    check('and the reason says why, rather than "not found"',
          'not a connected account' in why, why)

print('\n--- ambiguity attaches nothing ---')
with app.app_context():
    m, why = A._match_receipt_to_bank(A.TaxDocument.query.get(4), 1)
    check('two equally close identical charges match neither', m is None, (m, why))
    check('and it says so', 'equally well' in why, why)

print('\n--- the window is not unbounded ---')
with app.app_context():
    m, why = A._match_receipt_to_bank(A.TaxDocument.query.get(6), 1)
    check('a receipt 90 days from any charge does not match', m is None, why)

print('\n--- receipts use the purchase date, not the upload date ---')
with app.app_context():
    doc = A.TaxDocument.query.get(3)
    check('the purchase date wins when present',
          A._receipt_date(doc) == doc.purchase_date, A._receipt_date(doc))
    doc.purchase_date = None
    check('falling back to upload only when there is nothing better',
          A._receipt_date(doc) == doc.uploaded_at.date())
    doc.purchase_date = TODAY - timedelta(days=1)
    db.session.commit()

print('\n--- reconcile fixes a double that already exists ---')
with app.app_context():
    # The real case: a receipt imported before the bank feed caught up, then the bank
    # transaction arrives later and there are now two rows for one purchase.
    db.session.add(A.SpendTransaction(
        user_id=1, external_id='receipt:7', source='receipt', amount=75.40,
        description='Lowes', merchant='Lowes', category='other',
        posted_at=TODAY - timedelta(days=1), tax_document_id=7))
    db.session.add(receipt(7, 75.40, 'Lowes', last4='2001', days_ago=1))
    db.session.add(bank('b5', 'acc-amex', 75.40, 'LOWES', days_ago=1))
    db.session.commit()
    before = A.SpendTransaction.query.count()

r = c.post('/api/finance/receipts/reconcile').get_json()
check('the duplicate is removed', r['duplicates_removed'] == 1, r)
with app.app_context():
    check('the receipt-sourced row is gone',
          A.SpendTransaction.query.filter_by(external_id='receipt:7').first() is None)
    b5 = A.SpendTransaction.query.filter_by(external_id='plaid:b5').first()
    check('and the document is attached to the bank row', b5.tax_document_id == 7)
    check('the ledger shrank by exactly one', A.SpendTransaction.query.count() == before - 1,
          (before, A.SpendTransaction.query.count()))

print('\n--- and reconciling twice changes nothing ---')
with app.app_context():
    before = A.SpendTransaction.query.count()
r2 = c.post('/api/finance/receipts/reconcile').get_json()
check('no further duplicates found', r2['duplicates_removed'] == 0, r2)
with app.app_context():
    check('the ledger is unchanged', A.SpendTransaction.query.count() == before)
check('unmatched receipts are reported with a reason',
      all('result' in d for d in r2['details']), r2['details'][:2])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL RECEIPT MATCH CHECKS PASSED')
