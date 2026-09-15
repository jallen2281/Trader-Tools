"""Transfers are recognised by finding both halves, not by guessing from the name.

"To Checking" names itself; "JPMORGAN CHASE BANK, NA" does not, and a $9,000 move from
savings to a Chase account read as $9,000 of spending. The reliable evidence is the other
half: the same amount arriving on another of the user's connected accounts a few days
later. Pairing is deliberately narrow -- a wrong match hides real spending -- and it
remembers what it paired, so an undo sticks.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='pair_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'p.db').replace(os.sep, '/')
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


S, D = A.SpendTransaction, A.PlaidDeposit
IDS = {}

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='u@x.com', name='U', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    chk_acct = A.FinanceAccount(user_id=1, name='Chase Checking', type='checking')
    sav_acct = A.FinanceAccount(user_id=1, name='SoFi Savings', type='savings')
    amex = A.Debt(user_id=1, name='Amex', type='credit_card', balance=35000, apr=24.49, min_payment=900)
    db.session.add_all([chk_acct, sav_acct, amex])
    db.session.flush()
    db.session.add_all([
        A.PlaidAccount(user_id=1, item_id=1, account_id='chk', name='TOTAL CHECKING', mask='1349',
                       type='depository', subtype='checking', linked_account_id=chk_acct.id),
        A.PlaidAccount(user_id=1, item_id=1, account_id='sav', name='SoFi Savings', mask='3808',
                       type='depository', subtype='savings', linked_account_id=sav_acct.id),
        A.PlaidAccount(user_id=1, item_id=1, account_id='amex', name='Amex', mask='2001',
                       type='credit', subtype='credit card', linked_debt_id=amex.id),
    ])
    IDS.update(chk=chk_acct.id, sav=sav_acct.id, amex=amex.id)

    def out(key, when, amt, acct, desc, **kw):
        t = S(user_id=1, posted_at=when, description=desc, category=kw.pop('category', 'other'),
              amount=amt, plaid_account_id=acct, source=kw.pop('source', 'plaid'), **kw)
        db.session.add(t)
        db.session.flush()
        IDS[key] = t.id

    def dep(key, when, amt, acct, desc, kind='transfer_in'):
        d = D(user_id=1, external_id='plaid:' + key, plaid_account_id=acct, posted_at=when,
              description=desc, amount=amt, kind=kind)
        db.session.add(d)
        db.session.flush()
        IDS[key] = d.id

    out('big_out', date(2026, 8, 25), 9000.00, 'sav', 'JPMORGAN CHASE BANK, NA')
    dep('big_in', date(2026, 8, 26), 9000.00, 'chk', 'SoFi Bank TRANSFER')

    out('early100', date(2026, 9, 1), 100.00, 'sav', 'To Checking')
    out('near100', date(2026, 9, 3), 100.00, 'sav', 'To Checking')
    dep('in100', date(2026, 9, 3), 100.00, 'chk', 'From Savings')

    out('same_out', date(2026, 9, 5), 250.00, 'chk', 'Something')
    dep('same_in', date(2026, 9, 5), 250.00, 'chk', 'Something back')

    out('far_out', date(2026, 9, 1), 400.00, 'sav', 'To Checking')
    dep('far_in', date(2026, 9, 6), 400.00, 'chk', 'From Savings')

    out('pay_out', date(2026, 9, 10), 777.00, 'sav', 'Bought something')
    dep('pay_in', date(2026, 9, 10), 777.00, 'chk', 'PAYROLL', kind='income')

    out('manual_out', date(2026, 9, 12), 300.00, None, 'Typed in', source='manual')
    dep('manual_in', date(2026, 9, 12), 300.00, 'chk', 'Deposit')

    out('card_out', date(2026, 9, 14), 263.92, 'chk', 'CHASE CARD PMT', category='debt')
    dep('card_in', date(2026, 9, 14), 263.92, 'amex', 'PAYMENT RECEIVED', kind='card_payment')

    out('refund', date(2026, 9, 14), -25.00, 'amex', 'Return')
    db.session.commit()


def row(key):
    with app.app_context():
        return db.session.get(S, IDS[key])


with app.app_context():
    made = A._pair_transfers(1)
    db.session.commit()      # the sync commits for it; a direct call must commit itself
print('\n--- the pairs that are real ---')
check('three pairs made', made == 3, made)
r = row('big_out')
check('a $9,000 move with a bank name for a description is a transfer', r.category == 'transfer', r.category)
check('it remembers the deposit it matched', r.paired_deposit_id == IDS['big_in'], r.paired_deposit_id)
check('and knows where the money went', r.to_account_id == IDS['chk'], r.to_account_id)
r = row('card_out')
check('a card payment pairs with its landing on the card', r.category == 'transfer'
      and r.to_debt_id == IDS['amex'], (r.category, r.to_debt_id))

print('\n--- one deposit, one outflow: the nearest ---')
check('the same-day $100 is paired', row('near100').category == 'transfer')
check('the earlier $100 is left as it was', row('early100').category == 'other'
      and row('early100').paired_deposit_id is None)

print('\n--- what must NOT pair ---')
check('the same account on both sides', row('same_out').category == 'other')
check('five days apart', row('far_out').category == 'other')
check('a matching amount arriving as income', row('pay_out').category == 'other')
check('a hand-entered row', row('manual_out').category == 'other')
check('a refund is untouched', row('refund').category == 'other')

print('\n--- running again changes nothing ---')
with app.app_context():
    n = A._pair_transfers(1)
    db.session.commit()
    check('no new pairs', n == 0, n)

print('\n--- an undo sticks ---')
with app.app_context():
    t = db.session.get(S, IDS['big_out'])
    t.category = 'other'                         # the user says it was not a transfer
    db.session.add(S(user_id=1, posted_at=date(2026, 8, 26), description='Another 9000',
                     category='other', amount=9000.00, plaid_account_id='amex', source='plaid'))
    db.session.commit()
    again = A._pair_transfers(1)
    db.session.commit()
check('the undone row is not re-paired', row('big_out').category == 'other', row('big_out').category)
check('and its deposit is not handed to a different outflow', again == 0, again)

print('\n--- a sync only looks back so far ---')
with app.app_context():
    db.session.add(S(user_id=1, posted_at=date(2026, 1, 10), description='Old move', category='other',
                     amount=55.55, plaid_account_id='sav', source='plaid'))
    db.session.add(D(user_id=1, external_id='plaid:old', plaid_account_id='chk',
                     posted_at=date(2026, 1, 11), description='Old in', amount=55.55, kind='transfer_in'))
    db.session.commit()
    recent = A._pair_transfers(1, since=date(2026, 9, 1))
    db.session.commit()
    everything = A._pair_transfers(1)
    db.session.commit()
check('a recent window leaves January alone', recent == 0, recent)
check('a full pass reaches it', everything == 1, everything)

print('\n--- the ledger shows the result ---')
c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True
rows = c.get('/api/finance/ledger?month=2026-09').get_json()['rows']
led = {r['description']: r for r in rows}
to_chk = [r for r in rows if r['description'] == 'To Checking']
check('of the three "To Checking" rows, only the paired one is a transfer',
      sorted(r['direction'] for r in to_chk) == ['out', 'out', 'transfer'],
      [(r['posted_at'], r['direction']) for r in to_chk])
check('the card payment is a transfer', led['CHASE CARD PMT']['direction'] == 'transfer')
check('and carries the pairing for the badge', led['CHASE CARD PMT']['txn']['paired_deposit_id'] == IDS['card_in'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL TRANSFER-PAIRING CHECKS PASSED')
