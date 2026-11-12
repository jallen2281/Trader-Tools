"""Issuer-reported terms and positions: the two paid products, and what they may touch.

Two things here are easy to get wrong and expensive when you do.

THE RATE A CARD IS ACTUALLY PAYING. A card does not have one APR -- Plaid returns a list,
and each entry carries the slice of the balance it applies to. Taking the first, or always
taking purchase_apr, misreads the case that matters most: a card parked on a 0% balance
transfer reads as 24%, and one whose promo just expired reads as 0%. Both make a payoff
plan that is fiction.

WHAT A SYNC IS ALLOWED TO DESTROY. A Portfolio row carries the user's own tags -- intent,
ipo_lock_until, stop_loss_pct -- that Plaid knows nothing about. So holdings are upserted
and never deleted: a flaky institution returning half its positions must not be able to
delete a trading plan. A position Plaid stops reporting is reported, not removed.

And the as-of rule inverts here, on purpose. Through the API, re-sending an unchanged APR
does NOT restamp apr_as_of -- a person re-saving a form has checked nothing. From the
issuer it DOES: a bank confirming today that the rate is still 24.490% is a fresh reading.
The roof loan is why that matters. It was recorded at 11.900%, which was correct when it
was entered and silently wrong months later, and nothing could tell the two apart.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='plaidliab_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'l.db').replace(os.sep, '/')
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
TODAY = date.today()


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


# --------------------------------------------------------------- pure normalization
print('\n--- the rate a card is ACTUALLY paying, out of the list ---')

check('a 0% balance transfer holding the balance wins over the purchase rate',
      pc.apr_for_card({'aprs': [
          {'apr_percentage': 24.49, 'apr_type': 'purchase_apr', 'balance_subject_to_apr': 0},
          {'apr_percentage': 0.0, 'apr_type': 'balance_transfer_apr',
           'balance_subject_to_apr': 4200.0}]}) == (0.0, 'balance_transfer_apr'),
      pc.apr_for_card({'aprs': [{'apr_percentage': 24.49, 'apr_type': 'purchase_apr',
                                 'balance_subject_to_apr': 0}]}))

check('and once the promo balance is paid off, the purchase rate takes over',
      pc.apr_for_card({'aprs': [
          {'apr_percentage': 24.49, 'apr_type': 'purchase_apr',
           'balance_subject_to_apr': 1500.0},
          {'apr_percentage': 0.0, 'apr_type': 'balance_transfer_apr',
           'balance_subject_to_apr': 0.0}]}) == (24.49, 'purchase_apr'))

check('with no balances reported at all it falls back to purchase_apr, not the first entry',
      pc.apr_for_card({'aprs': [
          {'apr_percentage': 29.99, 'apr_type': 'cash_apr'},
          {'apr_percentage': 24.49, 'apr_type': 'purchase_apr'}]}) == (24.49, 'purchase_apr'))

check('a card with no rate reported is unknown, NOT interest-free',
      pc.apr_for_card({'aprs': []}) == (None, None),
      pc.apr_for_card({'aprs': []}))

check('an entry with a null percentage is ignored rather than read as zero',
      pc.apr_for_card({'aprs': [{'apr_percentage': None, 'apr_type': 'purchase_apr'},
                                {'apr_percentage': 18.0, 'apr_type': 'cash_apr'}]})
      == (18.0, 'cash_apr'))

print('\n--- the three liability shapes normalize to one ---')
credit = pc.liability_terms({'account_id': 'c1', 'minimum_payment_amount': 40.0,
                             'last_statement_balance': 1708.77,
                             'next_payment_due_date': '2026-12-01',
                             'aprs': [{'apr_percentage': 24.49, 'apr_type': 'purchase_apr',
                                       'balance_subject_to_apr': 1708.77}]}, 'credit')
check('a card carries rate, minimum and statement balance',
      (credit['apr'], credit['min_payment'], credit['last_statement_balance'],
       credit['next_due']) == (24.49, 40.0, 1708.77, '2026-12-01'), credit)

mortgage = pc.liability_terms({'account_id': 'm1',
                               'interest_rate': {'percentage': 6.125, 'type': 'fixed'},
                               'next_monthly_payment': 3100.0,
                               'maturity_date': '2040-07-18',
                               'ytd_interest_paid': 12300.0,
                               'next_payment_due_date': '2026-12-15'}, 'mortgage')
check("a mortgage's scheduled payment IS its minimum -- there is no separate field",
      (mortgage['apr'], mortgage['min_payment'], mortgage['apr_type']) == (6.125, 3100.0, 'fixed'),
      mortgage)
check('and it carries maturity and YTD interest',
      (mortgage['maturity_date'], mortgage['ytd_interest_paid']) == ('2040-07-18', 12300.0))

student = pc.liability_terms({'account_id': 's1', 'interest_rate_percentage': 5.25,
                              'minimum_payment_amount': 515.0}, 'student')
check('a student loan spells its rate differently and still lands in the same slot',
      (student['apr'], student['min_payment']) == (5.25, 515.0), student)

check('an absent value stays None and is never zeroed',
      pc.liability_terms({'account_id': 'x'}, 'credit')['min_payment'] is None)

rows = pc.liability_rows({'liabilities': {
    'credit': [{'account_id': 'c1', 'aprs': []}, {'account_id': None}],
    'mortgage': [{'account_id': 'm1', 'interest_rate': {'percentage': 6.0}}],
    'student': []}})
check('flattening keeps only entries that name an account',
      [r['account_id'] for r in rows] == ['c1', 'm1'], rows)

print('\n--- holdings: cash is cash, and an unquotable line is skipped ---')
hrows, hcash = pc.holdings_rows({
    'holdings': [
        {'account_id': 'b1', 'security_id': 's1', 'quantity': 10,
         'institution_price': 12.5, 'institution_value': 125.0, 'cost_basis': 100.0},
        {'account_id': 'b1', 'security_id': 'cash', 'quantity': 300,
         'institution_price': 1.0, 'institution_value': 300.0},
        {'account_id': 'b1', 'security_id': 'noticker', 'quantity': 5,
         'institution_value': 50.0},
        {'account_id': 'b1', 'security_id': 's1', 'quantity': 0,
         'institution_value': 0.0}],
    'securities': [
        {'security_id': 's1', 'ticker_symbol': 'kmi', 'name': 'Kinder Morgan',
         'type': 'equity'},
        {'security_id': 'cash', 'is_cash_equivalent': True, 'ticker_symbol': 'CUR:USD'},
        {'security_id': 'noticker', 'name': 'Some private fund', 'type': 'other'}]})
check('one real position survives', [r['symbol'] for r in hrows] == ['KMI'], hrows)
check('the ticker is upper-cased', hrows[0]['symbol'] == 'KMI')
check('cost basis is a TOTAL, so average cost is derived',
      hrows[0]['average_cost'] == 10.0, hrows[0]['average_cost'])
check('the cash equivalent became cash, not a holding called CUR:USD',
      hcash == {'b1': 300.0}, hcash)
check('an instrument with no ticker is skipped rather than invented', 'NOTICKER' not in str(hrows))
check('and a zero-quantity line never divides by zero', len(hrows) == 1, hrows)


# --------------------------------------------------------------- against the database
class FakeClient:
    """Stands in for PlaidClient. `raises` lets a product fail on demand."""

    def __init__(self, liabilities=None, holdings=None, raises=None):
        self._liabilities = liabilities or {}
        self._holdings = holdings or {}
        self.raises = raises or {}
        self.calls = []

    def liabilities_get(self, token, account_ids=None):
        self.calls.append('liabilities')
        if 'liabilities' in self.raises:
            raise self.raises['liabilities']
        return self._liabilities

    def investments_holdings_get(self, token, account_ids=None):
        self.calls.append('investments')
        if 'investments' in self.raises:
            raise self.raises['investments']
        return self._holdings


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(A.PlaidItem(id=1, user_id=UID, item_id='item-1',
                               institution_name='Amex', status='active',
                               access_token_enc=pc.encrypt_token('tok-1')))
    # A card whose rate the app recorded months ago, and still believes.
    db.session.add(A.Debt(id=1, user_id=UID, name='Amex', type='credit_card',
                          balance=37074.11, apr=24.49, min_payment=986.0,
                          apr_as_of=date(2026, 3, 1), balance_as_of=date(2026, 3, 1)))
    db.session.add(A.Debt(id=2, user_id=UID, name='Unlinked card', type='credit_card',
                          balance=100.0, apr=9.99, min_payment=25.0,
                          apr_as_of=date(2026, 3, 1)))
    db.session.add(A.PlaidAccount(id=1, user_id=UID, item_id=1, account_id='c1',
                                  name='Amex EveryDay', type='credit',
                                  subtype='credit card', linked_debt_id=1))
    # Connected, but the user has not said what it corresponds to.
    db.session.add(A.PlaidAccount(id=2, user_id=UID, item_id=1, account_id='c2',
                                  name='Some other card', type='credit',
                                  subtype='credit card'))
    db.session.add(A.RecurringBill(id=1, user_id=UID, name='Amex payment', payee='Amex',
                                   category='debt', amount=986.0, frequency='monthly',
                                   linked_debt_id=1, active=True,
                                   next_due_date=date(2026, 1, 5)))
    db.session.add(A.PortfolioAccount(id=1, user_id=UID, name='SoFi', cash_balance=0.0))
    db.session.add(A.PlaidAccount(id=3, user_id=UID, item_id=1, account_id='b1',
                                  name='SoFi Self-directed', type='investment',
                                  subtype='brokerage', linked_portfolio_id=1))
    # Held with a trading plan on it, and a cost basis the user entered by hand.
    db.session.add(A.Portfolio(id=1, user_id=UID, account_id=1, symbol='KMI',
                               asset_type='stock', quantity=100, average_cost=22.1234,
                               intent='long_term', stop_loss_pct=8.0))
    # A position this sync will not report back.
    db.session.add(A.Portfolio(id=2, user_id=UID, account_id=1, symbol='MNKD',
                               asset_type='stock', quantity=50, average_cost=4.0,
                               intent='speculative'))
    db.session.commit()

LIABS = {'liabilities': {'credit': [
    {'account_id': 'c1', 'minimum_payment_amount': 1050.0,
     'next_payment_due_date': None,
     'aprs': [{'apr_percentage': 26.99, 'apr_type': 'purchase_apr',
               'balance_subject_to_apr': 37074.11}]},
    # Connected but unlinked: must be ignored, not guessed at.
    {'account_id': 'c2', 'minimum_payment_amount': 15.0,
     'aprs': [{'apr_percentage': 31.0, 'apr_type': 'purchase_apr',
               'balance_subject_to_apr': 500.0}]}]}}

print('\n--- the issuer corrects a rate the app has believed since March ---')
with app.app_context():
    item = db.session.get(A.PlaidItem, 1)
    n = A._sync_plaid_liabilities(item, client=FakeClient(liabilities=LIABS), token='tok')
    db.session.commit()
    d = db.session.get(A.Debt, 1)
    check('one debt was touched', n == 1, n)
    check('the APR is the issuer\'s now', float(d.apr) == 26.99, d.apr)
    check('and it is stamped today, not left at the March date',
          d.apr_as_of == TODAY, d.apr_as_of)
    check('the minimum payment follows too', float(d.min_payment) == 1050.0, d.min_payment)
    check('the BALANCE date is untouched -- liabilities says nothing about it',
          d.balance_as_of == date(2026, 3, 1), d.balance_as_of)
    other = db.session.get(A.Debt, 2)
    check('a connected-but-unlinked account changes nothing',
          float(other.apr) == 9.99 and other.apr_as_of == date(2026, 3, 1),
          (other.apr, other.apr_as_of))

print('\n--- an UNCHANGED rate still advances the date, unlike an API edit ---')
with app.app_context():
    d = db.session.get(A.Debt, 1)
    d.apr_as_of = date(2026, 3, 1)
    db.session.commit()
    A._sync_plaid_liabilities(db.session.get(A.PlaidItem, 1),
                              client=FakeClient(liabilities=LIABS), token='tok')
    db.session.commit()
    d = db.session.get(A.Debt, 1)
    check('the rate is the same', float(d.apr) == 26.99, d.apr)
    check('but the issuer confirmed it TODAY, so the date moves',
          d.apr_as_of == TODAY, d.apr_as_of)
    check('and apr_age_days reports 0', d.apr_age_days() == 0, d.apr_age_days())

print('\n--- the due date the issuer gives beats the rolling guess ---')
with app.app_context():
    future = (TODAY + timedelta(days=12)).isoformat()
    liabs = {'liabilities': {'credit': [
        {'account_id': 'c1', 'next_payment_due_date': future, 'aprs': []}]}}
    A._sync_plaid_liabilities(db.session.get(A.PlaidItem, 1),
                              client=FakeClient(liabilities=liabs), token='tok')
    db.session.commit()
    b = db.session.get(A.RecurringBill, 1)
    check('the linked bill now carries the real due date',
          b.next_due_date.isoformat() == future, b.next_due_date)

    past = (TODAY - timedelta(days=20)).isoformat()
    liabs = {'liabilities': {'credit': [
        {'account_id': 'c1', 'next_payment_due_date': past, 'aprs': []}]}}
    A._sync_plaid_liabilities(db.session.get(A.PlaidItem, 1),
                              client=FakeClient(liabilities=liabs), token='tok')
    db.session.commit()
    b = db.session.get(A.RecurringBill, 1)
    check('a date in the PAST is refused -- that is the last due date under another name',
          b.next_due_date.isoformat() == future, b.next_due_date)

    liabs = {'liabilities': {'credit': [
        {'account_id': 'c1', 'aprs': [], 'minimum_payment_amount': None}]}}
    A._sync_plaid_liabilities(db.session.get(A.PlaidItem, 1),
                              client=FakeClient(liabilities=liabs), token='tok')
    db.session.commit()
    d = db.session.get(A.Debt, 1)
    check('a response with no rate does not zero the one on file',
          float(d.apr) == 26.99, d.apr)
    check('nor does a null minimum zero the payment',
          float(d.min_payment) == 1050.0, d.min_payment)

HOLD = {
    'holdings': [
        {'account_id': 'b1', 'security_id': 's1', 'quantity': 120,
         'institution_price': 28.5, 'institution_value': 3420.0, 'cost_basis': 2400.0},
        {'account_id': 'b1', 'security_id': 's2', 'quantity': 40,
         'institution_price': 210.0, 'institution_value': 8400.0, 'cost_basis': 7000.0},
        {'account_id': 'b1', 'security_id': 'cash', 'quantity': 2851.59,
         'institution_value': 2851.59}],
    'securities': [
        {'security_id': 's1', 'ticker_symbol': 'KMI', 'type': 'equity'},
        {'security_id': 's2', 'ticker_symbol': 'AMZN', 'type': 'equity'},
        {'security_id': 'cash', 'is_cash_equivalent': True}]}

print('\n--- holdings are upserted, and the user\'s own work is left alone ---')
with app.app_context():
    item = db.session.get(A.PlaidItem, 1)
    wrote, cash_wrote, unreported = A._sync_plaid_holdings(
        item, client=FakeClient(holdings=HOLD), token='tok')
    db.session.commit()
    check('both reported positions were written', wrote == 2, wrote)
    kmi = A.Portfolio.query.filter_by(user_id=UID, account_id=1, symbol='KMI').first()
    check('the quantity is the custodian\'s', float(kmi.quantity) == 120.0, kmi.quantity)
    check('and so is the price', float(kmi.current_price) == 28.5, kmi.current_price)
    check('THE HAND-ENTERED COST BASIS IS NOT OVERWRITTEN',
          round(float(kmi.average_cost), 4) == 22.1234, kmi.average_cost)
    check('and the trading plan on the row survives',
          (kmi.intent, float(kmi.stop_loss_pct)) == ('long_term', 8.0),
          (kmi.intent, kmi.stop_loss_pct))
    amzn = A.Portfolio.query.filter_by(user_id=UID, account_id=1, symbol='AMZN').first()
    check('a position the app did not have is created', amzn is not None)
    check('and a NEW row does take the custodian\'s basis',
          amzn is not None and round(float(amzn.average_cost), 4) == 175.0,
          amzn.average_cost if amzn else None)
    check('the cash equivalent landed on the account, not in the positions',
          float(db.session.get(A.PortfolioAccount, 1).cash_balance) == 2851.59,
          db.session.get(A.PortfolioAccount, 1).cash_balance)
    check('one cash balance was written', cash_wrote == 1, cash_wrote)

    mnkd = A.Portfolio.query.filter_by(user_id=UID, account_id=1, symbol='MNKD').first()
    check('A POSITION PLAID DID NOT REPORT IS STILL THERE', mnkd is not None)
    check('and is reported as unreported rather than deleted',
          unreported == ['MNKD'], unreported)

print('\n--- an unlinked portfolio is never touched ---')
with app.app_context():
    db.session.add(A.PortfolioAccount(id=2, user_id=UID, name='Transamerica 401k',
                                      cash_balance=0.0))
    db.session.add(A.Portfolio(id=9, user_id=UID, account_id=2, symbol='TRLUMP',
                               asset_type='stock', quantity=1, average_cost=140504.51))
    db.session.commit()
    A._sync_plaid_holdings(db.session.get(A.PlaidItem, 1),
                           client=FakeClient(holdings=HOLD), token='tok')
    db.session.commit()
    lump = db.session.get(A.Portfolio, 9)
    check('the hand-tracked 401k lump is untouched',
          float(lump.average_cost) == 140504.51 and float(lump.quantity) == 1.0,
          (lump.quantity, lump.average_cost))

print('\n--- a product that was never consented to is not a failure ---')
with app.app_context():
    item = db.session.get(A.PlaidItem, 1)
    fc = FakeClient(liabilities=LIABS, holdings=HOLD, raises={
        'liabilities': pc.PlaidError('no liabilities', code='PRODUCTS_NOT_SUPPORTED')})
    out = A._pull_plaid_extras(item, fc, 'tok')
    check('it is reported as needing a re-link',
          out['relink'] == [{'product': 'liabilities', 'code': 'PRODUCTS_NOT_SUPPORTED'}],
          out['relink'])
    check('NOT as an error', out['extra_errors'] == [], out['extra_errors'])
    check('and the other product still ran', out['holdings'] == 2, out)

print('\n--- a real outage IS an error, and still does not stop the sync ---')
with app.app_context():
    item = db.session.get(A.PlaidItem, 1)
    fc = FakeClient(liabilities=LIABS, holdings=HOLD, raises={
        'investments': pc.PlaidError('upstream down', code='INSTITUTION_DOWN')})
    out = A._pull_plaid_extras(item, fc, 'tok')
    check('it is recorded as an error', len(out['extra_errors']) == 1, out['extra_errors'])
    check('it names the product', out['extra_errors'][0]['product'] == 'investments')
    check('and liabilities still ran', out['liabilities'] == 1, out)

    fc = FakeClient(raises={'liabilities': ValueError('something unforeseen')})
    out = A._pull_plaid_extras(item, fc, 'tok')
    check('an unexpected exception is caught too -- extras never break a sync',
          len(out['extra_errors']) == 1, out['extra_errors'])

print('\n--- nothing is called unless it is paid for ---')
with app.app_context():
    item = db.session.get(A.PlaidItem, 1)
    saved = A.Config.PLAID_CALLABLE_PRODUCTS
    try:
        A.Config.PLAID_CALLABLE_PRODUCTS = ['transactions']
        fc = FakeClient(liabilities=LIABS, holdings=HOLD)
        out = A._pull_plaid_extras(item, fc, 'tok')
        check('with only transactions enabled, neither endpoint is called',
              fc.calls == [], fc.calls)
        check('and nothing is reported as broken',
              out['relink'] == [] and out['extra_errors'] == [], out)
        A.Config.PLAID_CALLABLE_PRODUCTS = ['transactions', 'liabilities']
        fc = FakeClient(liabilities=LIABS, holdings=HOLD)
        A._pull_plaid_extras(item, fc, 'tok')
        check('enabling one enables exactly one', fc.calls == ['liabilities'], fc.calls)
    finally:
        A.Config.PLAID_CALLABLE_PRODUCTS = saved

print('\n--- consent is requested at link time, without being required ---')


class TokenSpy:
    def __init__(self):
        self.payload = None

    def _post(self, path, payload):
        self.payload = payload
        return {'link_token': 'lt', 'expiration': 'x'}

    available = lambda self: True                                      # noqa: E731


spy = TokenSpy()
pc.PlaidClient.link_token_create(spy, 1, ['transactions'],
                                 consented=['liabilities', 'investments'])
check('products stays the minimum every institution supports',
      spy.payload.get('products') == ['transactions'], spy.payload.get('products'))
check('the rest ride along as additional_consented_products',
      spy.payload.get('additional_consented_products') == ['liabilities', 'investments'],
      spy.payload.get('additional_consented_products'))

spy = TokenSpy()
pc.PlaidClient.link_token_create(spy, 1, ['transactions', 'liabilities'],
                                 consented=['liabilities', 'investments'])
check('a product in both lists is dropped from consent -- Plaid rejects the overlap',
      spy.payload.get('additional_consented_products') == ['investments'],
      spy.payload.get('additional_consented_products'))

spy = TokenSpy()
pc.PlaidClient.link_token_create(spy, 1, ['transactions'], access_token='tok',
                                 consented=['liabilities'])
check('update mode sends neither list -- a re-auth is not a place to add products',
      'products' not in spy.payload and 'additional_consented_products' not in spy.payload,
      spy.payload)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID LIABILITIES / HOLDINGS CHECKS PASSED')
