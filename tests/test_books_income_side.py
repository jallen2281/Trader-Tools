"""A set of books counts the income that actually arrived, not just the income that was typed in.

Reported from using the app: the Books section showed Chicken Tales LLC with 19 tagged
expenses and an income of $0.00, while the farm's egg money was sitting right there in the
ledger, correctly filed to the farm.

The cause was that income and expenses were read from different kinds of record. Expenses
came from actual transactions; income came from IncomeSource.gross_annual(), which for an
irregular source annualizes `trailing_12mo_received()` -- and that only ever summed
IncomeEvent rows. The app offers two ways to record irregular income (log it by hand, or
attribute a bank deposit to the source) and this counted exactly one of them. Egg sales are
recorded the other way, so the farm read as a pure loss.

The fix counts both, and still refuses to count a transfer: moving money from Chase to SoFi
is not farm revenue.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-books-income-side')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, Entity, IncomeSource, IncomeEvent, PlaidDeposit, SpendTransaction

UID = 1
TODAY = date.today()
YR = TODAY.year
JAN1 = date(YR, 1, 1)


def cli():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    return c

with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='books2@x.com', name='Books',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    farm = Entity(user_id=UID, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    realty = Entity(user_id=UID, name='Coldwell Banker Realty', kind='business', tax_form='Schedule C')
    home = Entity(user_id=UID, name='Personal finance', kind='personal')
    db.session.add_all([farm, realty, home])
    db.session.commit()

    # The farm: irregular, nothing logged by hand, no estimate -- exactly the live shape.
    eggs = IncomeSource(user_id=UID, name='Chicken Tales LLC', owner='joint',
                        type='self_employed', tax_form='none', irregular=True,
                        annual_salary=0, estimated_annual=0, active=True, entity_id=farm.id)
    # Realty: lumpy commissions, logged by hand as events.
    comm = IncomeSource(user_id=UID, name='Coldwell Banker - realty commissions', owner='me',
                        type='self_employed', tax_form='1099', irregular=True,
                        annual_salary=0, estimated_annual=0, active=True, entity_id=realty.id)
    # A salaried job, whose projection must not be disturbed by what happened to land.
    wages = IncomeSource(user_id=UID, name='Happy elephant - salary', owner='spouse',
                         type='salary', annual_salary=59000, pay_frequency='semimonthly',
                         tax_form='W2', active=True, entity_id=home.id)
    db.session.add_all([eggs, comm, wages])
    db.session.commit()

    n = [0]

    def deposit(amount, when, kind='income', src=None, entity=None):
        n[0] += 1
        d = PlaidDeposit(user_id=UID, external_id='t:%d' % n[0], posted_at=when,
                         description='row %d' % n[0], amount=amount, kind=kind,
                         income_source_id=(src.id if src else None),
                         entity_id=(entity.id if entity else None), source='manual')
        db.session.add(d)
        db.session.commit()
        return d

    print('--- the farm records income as deposits, and the books must see it ---')
    check('with nothing recorded the farm reports no income', eggs.gross_annual() == 0.0,
          eggs.gross_annual())
    deposit(6.00, TODAY - timedelta(days=20), src=eggs, entity=farm)
    deposit(4.50, TODAY - timedelta(days=13), src=eggs, entity=farm)
    deposit(15.00, TODAY - timedelta(days=12), src=eggs, entity=farm)
    # Filed to no book of its own: it still belongs to the farm, via its income source.
    untagged = deposit(12.00, TODAY - timedelta(days=17), src=eggs, entity=None)
    check('egg sales count toward the source', eggs.trailing_12mo_received() == 37.50,
          eggs.trailing_12mo_received())
    check('including the one with no book of its own',
          A._deposit_book(untagged, eggs, None) == farm.id,
          A._deposit_book(untagged, eggs, None))
    check('so the source annualizes off real money', eggs.gross_annual() == 37.50,
          eggs.gross_annual())

    rep = A._entity_report(UID, farm.id, YR)
    check('and the farm books report it as income', rep['income'] == 37.50, rep['income'])

    print('\n--- expenses still come from transactions, and net is the difference ---')
    db.session.add(SpendTransaction(user_id=UID, posted_at=TODAY - timedelta(days=30),
                                    description='Tractor Supply', amount=89.97,
                                    category='farm_feed', entity_id=farm.id))
    db.session.commit()
    rep = A._entity_report(UID, farm.id, YR)
    check('the expense side is unchanged', rep['expenses'] == 89.97, rep['expenses'])
    check('and net is income less expenses', rep['net'] == round(37.50 - 89.97, 2), rep['net'])

    print('\n--- a transfer between your own accounts is never income ---')
    deposit(3500.00, TODAY - timedelta(days=5), kind='transfer_in', src=eggs, entity=farm)
    deposit(1500.00, TODAY - timedelta(days=1), kind='card_payment', src=eggs, entity=farm)
    check('a Chase -> SoFi transfer does not become farm revenue',
          eggs.trailing_12mo_received() == 37.50, eggs.trailing_12mo_received())
    check('nor does a card payment', A._entity_report(UID, farm.id, YR)['income'] == 37.50,
          A._entity_report(UID, farm.id, YR)['income'])

    print('\n--- hand-logged events still count, and both sources of truth add up ---')
    db.session.add_all([
        IncomeEvent(user_id=UID, income_source_id=comm.id, date=TODAY - timedelta(days=60),
                    gross_amount=707.75, description='Russell Street'),
        IncomeEvent(user_id=UID, income_source_id=comm.id, date=TODAY - timedelta(days=40),
                    gross_amount=1690.40, description='Hume blvd'),
    ])
    db.session.commit()
    db.session.refresh(comm)
    check('logged commissions still annualize as before',
          comm.trailing_12mo_received() == 2398.15, comm.trailing_12mo_received())
    deposit(250.00, TODAY - timedelta(days=3), src=comm, entity=realty)
    db.session.refresh(comm)
    check('an attributed deposit adds to them rather than replacing them',
          comm.trailing_12mo_received() == 2648.15, comm.trailing_12mo_received())
    check('and the realty books agree',
          A._entity_report(UID, realty.id, YR)['income'] == 2648.15,
          A._entity_report(UID, realty.id, YR)['income'])

    print('\n--- tying a cheque to the payment it settles keeps one record of the money ---')
    ev = IncomeEvent.query.filter_by(income_source_id=comm.id, gross_amount=1690.40).first()
    cheque = deposit(1690.40, TODAY - timedelta(days=35), src=comm, entity=realty)
    db.session.refresh(comm)
    check('an untied cheque double-counts the commission',
          comm.trailing_12mo_received() == round(2648.15 + 1690.40, 2),
          comm.trailing_12mo_received())

    c = cli()
    r = c.put('/api/finance/deposits/%d' % cheque.id,
                json={'income_event_id': ev.id})
    check('the cheque can be tied to the logged payment', r.status_code == 200,
          (r.status_code, r.get_json()))
    db.session.refresh(comm)
    db.session.refresh(cheque)
    check('and the money is counted once again',
          comm.trailing_12mo_received() == 2648.15, comm.trailing_12mo_received())
    check('the link is recorded on the deposit', cheque.income_event_id == ev.id,
          cheque.income_event_id)
    check('the event knows which deposit settled it', ev.to_dict()['deposit_ids'] == [cheque.id],
          ev.to_dict())
    check('and how much of it has landed', ev.settled_amount() == 1690.40, ev.settled_amount())

    print('\n--- a tie is honest about what it joins ---')
    r = c.put('/api/finance/deposits/%d' % cheque.id, json={'income_event_id': 999999})
    check('an unknown payment is refused', r.status_code == 400, r.status_code)
    egg_src_event = IncomeEvent(user_id=UID, income_source_id=eggs.id,
                                date=TODAY - timedelta(days=9), gross_amount=5.00,
                                description='farmers market')
    db.session.add(egg_src_event)
    db.session.commit()
    r = c.put('/api/finance/deposits/%d' % cheque.id,
                json={'income_event_id': egg_src_event.id})
    check("a payment from another source is refused", r.status_code == 400,
          (r.status_code, r.get_json()))
    db.session.refresh(cheque)
    check('and the original tie is left intact', cheque.income_event_id == ev.id,
          cheque.income_event_id)

    print('\n--- a tie can be undone, and the ledger says what it is ---')
    row = [x for x in A._ledger_rows(UID, JAN1, TODAY)
           if x['kind'] == 'deposit' and x['id'] == cheque.id]
    check('the ledger marks it as settling logged income',
          row and row[0]['settles_logged_income'] is True, row)
    check('while still showing the money arriving', row and row[0]['direction'] == 'in', row)
    r = c.put('/api/finance/deposits/%d' % cheque.id, json={'income_event_id': None})
    check('the tie can be removed', r.status_code == 200, r.status_code)
    db.session.refresh(comm)
    check('and the cheque counts on its own again',
          comm.trailing_12mo_received() == round(2648.15 + 1690.40, 2),
          comm.trailing_12mo_received())
    # Put it back so the rest of the file reasons about a tidy book.
    c.put('/api/finance/deposits/%d' % cheque.id, json={'income_event_id': ev.id})
    db.session.delete(egg_src_event)
    db.session.commit()
    db.session.refresh(eggs)

    print('\n--- deleting a hand-written note never deletes the bank record ---')
    spare = IncomeEvent(user_id=UID, income_source_id=comm.id,
                        date=TODAY - timedelta(days=8), gross_amount=42.00,
                        description='scratch')
    db.session.add(spare)
    db.session.commit()
    tied = deposit(42.00, TODAY - timedelta(days=7), src=comm, entity=realty)
    c.put('/api/finance/deposits/%d' % tied.id, json={'income_event_id': spare.id})
    db.session.delete(spare)
    db.session.commit()
    kept = db.session.get(PlaidDeposit, tied.id)
    check('the deposit survives', kept is not None)
    check('with its link cleared rather than dangling',
          kept is not None and kept.income_event_id is None,
          kept and kept.income_event_id)
    db.session.delete(kept)
    db.session.commit()
    db.session.refresh(comm)

    print('\n--- windows are respected ---')
    deposit(99.00, TODAY - timedelta(days=400), src=eggs, entity=farm)
    check('a deposit older than 365 days is outside the trailing window',
          eggs.trailing_12mo_received() == 37.50, eggs.trailing_12mo_received())
    if TODAY.month > 1 or TODAY.day > 1:
        deposit(77.00, JAN1 - timedelta(days=1), src=eggs, entity=farm)
        check('and last year is outside year-to-date', eggs.ytd_received() == 37.50,
              eggs.ytd_received())

    print('\n--- a salaried projection is not disturbed by what happened to land ---')
    deposit(2458.33, TODAY - timedelta(days=15), src=wages, entity=home)
    deposit(2458.33, TODAY - timedelta(days=1), src=wages, entity=home)
    check('a scheduled source still projects from its salary',
          wages.gross_annual() == 59000.00, wages.gross_annual())
    check('while still reporting what actually arrived',
          wages.ytd_received() == 4916.66, wages.ytd_received())

    print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BOOKS INCOME-SIDE CHECKS PASSED')
