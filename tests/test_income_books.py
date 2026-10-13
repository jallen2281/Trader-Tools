"""Income gets a book, can be entered by hand, and hand-tracked debts can be paid.

Four gaps, all reported from using the app:

  1. EVERY DEPOSIT READ AS UNASSIGNED. A deposit's book came entirely from the income
     source behind it, and nothing ever linked a deposit to a source -- 61 of 63 on the
     reporting household. So the books had a complete expense side and no income side.

  2. NAME MATCHING CANNOT FIX THAT. The payroll line says "GENESEE CHRISTIA PAYROLL PPD"
     and the source is called "Happy elephant - salary"; the hosting income arrives as
     "NEXCESS" against "Liquid web - hourly". No string distance bridges those, and a
     wrong guess files income in the wrong book, which is worse than leaving it alone.
     So attribution LEARNS: name one deposit from a payer and the rest follow.

  3. INCOME COULD ONLY COME FROM PLAID. Cash for eggs, a commission cheque -- there was
     no way to record income that never touched a connected account, so the farm and
     realty books had no income at all.

  4. A HAND-TRACKED DEBT COULD NOT BE PAID. A synced card gets its balance from the bank;
     a tuition plan does not, so its balance never moved.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-income-books')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, Entity, IncomeSource, PlaidDeposit, Debt, FinanceAccount, SpendTransaction

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
    db.session.add(A.User(id=UID, google_id='g1', email='books@x.com', name='Books',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    farm = Entity(user_id=UID, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    home = Entity(user_id=UID, name='Personal finance', kind='personal')
    db.session.add_all([farm, home])
    db.session.commit()

    wages = IncomeSource(user_id=UID, name='Happy elephant - salary', owner='spouse',
                         type='salary', annual_salary=45150, pay_frequency='semimonthly',
                         tax_form='W2', active=True, entity_id=home.id,
                         next_pay_date=TODAY + timedelta(days=5))
    db.session.add(wages)
    db.session.commit()

    def deposit(desc, amount, when, kind='income'):
        d = PlaidDeposit(user_id=UID, external_id='plaid:%s:%s' % (desc, when),
                         plaid_account_id='chk', posted_at=when, description=desc,
                         merchant=desc, amount=amount, kind=kind)
        db.session.add(d)
        return d

    pay1 = deposit('GENESEE CHRISTIA PAYROLL PPD', 1881.28, TODAY - timedelta(days=30))
    pay2 = deposit('GENESEE CHRISTIA PAYROLL PPD', 1881.28, TODAY - timedelta(days=15))
    pay3 = deposit('GENESEE CHRISTIA PAYROLL PPD', 1881.28, TODAY - timedelta(days=1))
    mover = deposit('From Savings - 3808', 500.00, TODAY - timedelta(days=4), 'transfer_in')
    db.session.commit()

    print('--- a payer that looks nothing like its source is not guessed at ---')
    check('nothing is attributed on names alone', A._attribute_deposits(UID) == 0)
    check('so the deposits stay unlinked', pay1.income_source_id is None)

    print('\n--- teach it once, and the rest follow ---')
    r = cli().put('/api/finance/deposits/%d/attribute' % pay1.id,
                  json={'income_source_id': wages.id})
    check('one deposit can be attributed by hand', r.status_code == 200, r.status_code)
    n = A._attribute_deposits(UID)
    db.session.commit()
    check('the other two are picked up', n == 2, n)
    check('and point at the same source',
          pay2.income_source_id == wages.id and pay3.income_source_id == wages.id,
          (pay2.income_source_id, pay3.income_source_id))
    check('a transfer is never given an income source', mover.income_source_id is None)

    print('\n--- which puts the income in a book ---')
    rows = A._ledger_rows(UID, TODAY - timedelta(days=40), TODAY)
    pay_rows = [r for r in rows if r['kind'] == 'deposit' and 'GENESEE' in (r['merchant'] or '')]
    check('all three paychecks are in the ledger', len(pay_rows) == 3, len(pay_rows))
    check('each filed under the book of its source',
          all(r['book'] == 'Personal finance' for r in pay_rows),
          [r['book'] for r in pay_rows])

    print('\n--- a default book catches whatever is left ---')
    tr = [r for r in rows if r['kind'] == 'deposit' and 'Savings' in (r['merchant'] or '')][0]
    check('the transfer has no book yet', tr['book'] is None, tr['book'])
    r = cli().put('/api/finance/default-book', json={'entity_id': home.id})
    check('a default can be set', r.status_code == 200, (r.status_code, r.get_json()))
    check('and read back', cli().get('/api/finance/default-book').get_json()['entity_id'] == home.id)
    rows2 = A._ledger_rows(UID, TODAY - timedelta(days=40), TODAY)
    tr2 = [r for r in rows2 if r['kind'] == 'deposit' and 'Savings' in (r['merchant'] or '')][0]
    check('now it falls to the default', tr2['book'] == 'Personal finance', tr2['book'])
    check('and says so, rather than pretending it was filed', tr2['book_default'] is True, tr2)
    check('an explicitly filed row is not marked as a default',
          all(r['book_default'] is False for r in rows2
              if r['kind'] == 'deposit' and 'GENESEE' in (r['merchant'] or '')),
          [(r['merchant'], r['book_default']) for r in rows2 if r['kind'] == 'deposit'])
    r = cli().put('/api/finance/default-book', json={'entity_id': 9999})
    check('an unknown book is rejected', r.status_code == 400, r.status_code)

    print('\n--- income can be entered by hand ---')
    r = cli().post('/api/finance/deposits', json={
        'posted_at': TODAY.isoformat(), 'description': 'Egg sales - farmers market',
        'merchant': 'Cash', 'amount': 240.00, 'entity_id': farm.id})
    check('it is created', r.status_code == 201, (r.status_code, r.get_json()))
    made = r.get_json()
    check('marked as hand-entered', made['source'] == 'manual', made)
    check('and filed to the book asked for', made['entity_id'] == farm.id, made)
    check('a zero amount is refused',
          cli().post('/api/finance/deposits', json={'amount': 0}).status_code == 400)
    check('so is a negative one',
          cli().post('/api/finance/deposits', json={'amount': -5}).status_code == 400)

    rows3 = A._ledger_rows(UID, TODAY - timedelta(days=40), TODAY)
    egg = [r for r in rows3 if (r.get('description') or '').startswith('Egg sales')]
    check('it shows in the ledger as money in', egg and egg[0]['direction'] == 'in', egg)
    check('under the farm book', egg and egg[0]['book'] == 'Chicken Tales LLC', egg)
    check("its own book beats the default", egg and egg[0]['book_default'] is False, egg)

    print('\n--- editing and deleting income ---')
    r = cli().put('/api/finance/deposits/%d' % made['id'], json={'amount': 265.50})
    check('a hand-entered row can be edited', r.status_code == 200, r.status_code)
    check('and the change sticks', r.get_json()['amount'] == 265.50, r.get_json())
    r = cli().put('/api/finance/deposits/%d' % pay1.id, json={'entity_id': farm.id})
    check('a synced row can be re-filed', r.status_code == 200, r.status_code)
    check('and its own book now wins over the source',
          [x for x in A._ledger_rows(UID, TODAY - timedelta(days=40), TODAY)
           if x.get('id') == pay1.id and x['kind'] == 'deposit'][0]['book'] == 'Chicken Tales LLC')
    check('a synced row cannot be deleted',
          cli().delete('/api/finance/deposits/%d' % pay1.id).status_code == 400)
    check('a hand-entered one can be',
          cli().delete('/api/finance/deposits/%d' % made['id']).status_code == 200)

    print('\n--- paying a debt the bank does not report ---')
    acct = FinanceAccount(user_id=UID, name='Checking', type='checking', balance=5000)
    asu = Debt(user_id=UID, name="Tricia's ASU Bachelors degree", type='student',
               balance=10270.45, apr=0)
    db.session.add_all([acct, asu])
    db.session.commit()

    r = cli().post('/api/finance/debts/%d/payment' % asu.id,
                   json={'amount': 515.00, 'from_account_id': acct.id,
                         'posted_at': TODAY.isoformat()})
    check('the payment is recorded', r.status_code == 201, (r.status_code, r.get_json()))
    j = r.get_json()
    check('the balance comes down', j['balance'] == 9755.45, j)
    check('and it reports what it was', j['balance_before'] == 10270.45, j)
    txn = SpendTransaction.query.get(j['transaction_id'])
    check('the money leaving is recorded too', txn is not None)
    check('as a transfer, never as spending', txn and txn.category == 'transfer', txn and txn.category)
    check('pointed at the debt it paid', txn and txn.to_debt_id == asu.id)
    spend = A._spend_actuals(UID, TODAY - timedelta(days=1), TODAY)
    check('so it adds nothing to the budget', 'transfer' not in spend, spend)
    check('a zero payment is refused',
          cli().post('/api/finance/debts/%d/payment' % asu.id,
                     json={'amount': 0}).status_code == 400)
    r = cli().post('/api/finance/debts/%d/payment' % asu.id, json={'amount': 99999})
    check('overpaying floors the balance at zero rather than going negative',
          r.get_json()['balance'] == 0.0, r.get_json())

    print('\n--- a card is never paid down from the payment side alone ---')
    # An installment loan only goes down, so payment minus interest is the new balance.
    # A card goes up too, and when the card itself is not connected the only side visible
    # is the payment leaving the bank -- the purchases land on the card. Applying half of
    # a two-sided account walks the balance confidently wrong.
    from models import RecurringBill
    card = Debt(user_id=UID, name='PayPal mastercard', type='credit_card',
                balance=2333.50, apr=18.49)
    loan = Debt(user_id=UID, name='Roof Loan', type='home_improvement',
                balance=56000.00, apr=11.9)
    db.session.add_all([card, loan])
    db.session.commit()
    db.session.add_all([
        RecurringBill(user_id=UID, name='Paypal Mastercard', payee='Syncrony Paypal',
                      category='debt', amount=29.00, frequency='monthly',
                      linked_debt_id=card.id, active=True),
        RecurringBill(user_id=UID, name='Roof Loan', payee='Watercress',
                      category='debt', amount=750.00, frequency='monthly',
                      linked_debt_id=loan.id, active=True),
    ])
    db.session.add_all([
        SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=3),
                         description='PAYPAL', merchant='PAYPAL', category='debt',
                         amount=29.00, source='plaid', external_id='plaid:pp1'),
        SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=2),
                         description='Watercress Financial', merchant='Watercress Financial',
                         category='debt', amount=750.00, source='plaid',
                         external_id='plaid:wc1'),
    ])
    db.session.commit()

    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(card)
    db.session.refresh(loan)
    check('the credit card is untouched', float(card.balance) == 2333.50, card.balance)
    check('the installment loan moves', float(loan.balance) < 56000.00, loan.balance)
    # 11.9% on 56,000 is 555.33 of interest, leaving 194.67 of principal -- not 750.
    check('by principal only, not the whole payment',
          abs(float(loan.balance) - (56000.00 - 194.67)) < 0.02, loan.balance)

    print('\n--- escrow and PMI are not principal ---')
    # A mortgage payment carries escrowed tax, insurance and PMI. Treating the whole
    # non-interest part as principal flatters the biggest number on the balance sheet --
    # by $66 every month on the loan this came from, compounding for the life of it.
    mort = Debt(user_id=UID, name='1st Mortgage', type='mortgage', balance=342000.00,
                apr=6.0, escrow_monthly=66.00)
    db.session.add(mort)
    db.session.commit()
    db.session.add(RecurringBill(user_id=UID, name='Mortgage', payee='UWM',
                                 category='housing', amount=3103.88, frequency='monthly',
                                 linked_debt_id=mort.id, active=True))
    db.session.add(SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=1),
                                    description='UWM', merchant='UWM', category='housing',
                                    amount=3103.88, source='plaid',
                                    external_id='plaid:uwm1'))
    db.session.commit()
    interest, principal = A._split_payment(mort, 3103.88)
    check('interest is one month at the note rate', abs(interest - 1710.00) < 0.01, interest)
    # 3103.88 - 1710.00 interest - 66.00 escrow = 1327.88
    check('escrow comes out before principal', abs(principal - 1327.88) < 0.01, principal)
    check('which is exactly 66 less than ignoring it would give',
          abs((3103.88 - 1710.00) - principal - 66.00) < 0.01, principal)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(mort)
    check('and the balance moves by principal only',
          abs(float(mort.balance) - (342000.00 - 1327.88)) < 0.02, mort.balance)

    print('\n--- and a payment is never applied twice ---')
    before = float(loan.balance)
    A._apply_debt_payments(UID)
    db.session.commit()
    db.session.refresh(loan)
    check('a second pass changes nothing', float(loan.balance) == before, (before, loan.balance))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL INCOME BOOK CHECKS PASSED')
