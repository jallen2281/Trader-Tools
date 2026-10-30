"""A set of books counts what was spent, not what was moved -- and says so when money
arrived that it cannot classify.

Found by decomposing a real figure. "Personal finance" reported $128,300.88 of expenses
against $42,269.63 of take-home income, a $86,031.25 deficit. 44% of those "expenses" --
$56,657.30 across 63 rows -- was money moving between the owner's own accounts: savings to
checking, checking to the Amex, "From Taxes Vault". The proof was pairing: 22 of 31
transfer_in deposits matched an expense row to the cent and to the day in a different
account. Each move was charged as spending on the way out and credited as nothing on the
way in.

The app already knew better. NON_SPEND_CATEGORIES exists precisely because this
double-count once made a month read as $75,706 of outgoings against $13,000 of income, and
six separate spend totals drop those rows first. _entity_report, written later, did not --
so tests/test_transfers.py could claim transfers were "excluded from every spend total"
while the books page quietly included them.

Three things are tested here, all the same discipline:

  * Transfers leave the expense total and are reported separately, because a reader
    reconciling against a bank statement still has to see where the money went.
  * "At this rate" is measured over the days the ledger covers. Dividing four months of
    records by ten months of elapsed calendar is the same span error that made the income
    pace view report a salary paid in full as $35,846 short.
  * An arrival whose other half was never found is not a transfer. It came from outside,
    and leaving it classified as a transfer counts it toward neither income nor spending --
    the exact mirror of the bug above. It is surfaced to be named, not guessed at.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-books-transfers')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def near(a, b, tol=0.02):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


import app as A
from models import (db, Entity, IncomeSource, PlaidDeposit, PlaidItem, PlaidAccount,
                    SpendTransaction)

ME = 1
TODAY = date.today()
CUR = TODAY.year
JAN1 = date(CUR, 1, 1)
# Every fixture row has to land inside the current year however late in the year the suite
# runs, and the spans below need room on both sides of the dates they use.
FEED_START = max(JAN1, TODAY - timedelta(days=120))
RECENT = max(JAN1, TODAY - timedelta(days=10))


def spend(eid, when, desc, amt, cat='other', pa=None, **kw):
    t = SpendTransaction(user_id=ME, entity_id=eid, posted_at=when, description=desc,
                         amount=amt, category=cat, source='plaid',
                         external_id='x:%s:%s:%s' % (desc, when, amt),
                         plaid_account_id=pa, **kw)
    db.session.add(t)
    return t


def arrive(when, desc, amt, kind='transfer_in', pa=None, **kw):
    d = PlaidDeposit(user_id=ME, posted_at=when, description=desc, amount=amt, kind=kind,
                     external_id='d:%s:%s:%s' % (desc, when, amt),
                     plaid_account_id=pa, **kw)
    db.session.add(d)
    return d


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=ME, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    home = Entity(user_id=ME, name='Personal finance', kind='personal')
    shop = Entity(user_id=ME, name='Side business', kind='business', tax_form='Schedule C')
    db.session.add_all([home, shop])
    db.session.commit()
    HOME, SHOP = home.id, shop.id

    item = PlaidItem(user_id=ME, item_id='it1', access_token_enc=b'x',
                     institution_name='Test Bank')
    db.session.add(item)
    db.session.commit()
    chk = PlaidAccount(user_id=ME, item_id=item.id, account_id='acc_chk', name='Checking',
                       mask='0852', type='depository', subtype='checking')
    sav = PlaidAccount(user_id=ME, item_id=item.id, account_id='acc_sav', name='Savings',
                       mask='3808', type='depository', subtype='savings')
    db.session.add_all([chk, sav])
    db.session.commit()

    print('--- a transfer is not an expense ---')
    # The real shape: a move out of checking, landing in savings the same day. Both halves
    # are recorded; only one of them was ever counted.
    spend(HOME, RECENT, 'To Savings - 3808', 7500.00, 'transfer', pa='acc_chk')
    spend(HOME, RECENT, 'AMEX EPAYMENT', 2178.00, 'transfer', pa='acc_chk')
    # Real consumption, spread over a span long enough to annualize.
    spend(HOME, FEED_START, 'UNITEDWHOLESALE', 3103.88, 'housing', pa='acc_chk')
    spend(HOME, RECENT, 'KROGER', 240.00, 'food', pa='acc_chk')
    db.session.commit()

    rep = A._entity_report(ME, HOME, CUR)
    check('the expense total is the spending only',
          near(rep['expenses'], 3103.88 + 240.00), rep['expenses'])
    check('the movement is reported, not discarded',
          near(rep['transfers_out'], 7500.00 + 2178.00), rep['transfers_out'])
    check('and counted', rep['transfer_count'] == 2, rep['transfer_count'])
    check('every row is still visible in the row count',
          rep['transactions'] == 4, rep['transactions'])
    cats = {c['category'] for c in rep['by_category']}
    check('no transfer line appears in the category breakdown',
          'transfer' not in cats, sorted(cats))
    check('the categories that remain are the real ones',
          cats == {'housing', 'food'}, sorted(cats))
    check('the net is built on spending, not on movement',
          near(rep['net'], rep['income'] - (3103.88 + 240.00)),
          (rep['net'], rep['income'], rep['expenses']))

    print('\n--- the same rule reaches the taxed books ---')
    # A Schedule C book feeds `net` into the tax estimate. A transfer there is not a
    # deductible business expense, and counting one would understate the profit that gets
    # taxed -- the dangerous direction.
    spend(SHOP, RECENT, 'Transfer to owner draw', 5000.00, 'transfer', pa='acc_chk')
    spend(SHOP, RECENT, 'SUPPLIES', 412.50, 'other', pa='acc_chk')
    db.session.commit()
    sr = A._entity_report(ME, SHOP, CUR)
    check('a business book drops the transfer too', near(sr['expenses'], 412.50),
          sr['expenses'])
    check('so the taxable net is not reduced by a draw',
          near(sr['net'], sr['income'] - 412.50), (sr['net'], sr['income']))

    print('\n--- pairing is what proves a move was internal ---')
    # _pair_transfers finds the other half: same amount, different account, within days.
    # It is what catches "JPMORGAN CHASE BANK, NA", which no name rule would.
    out = spend(HOME, RECENT, 'JPMORGAN CHASE BANK, NA', 9000.00, 'other', pa='acc_chk')
    dep = arrive(RECENT, 'SoFi Bank TRANSFER', 9000.00, pa='acc_sav')
    db.session.commit()
    before = A._entity_report(ME, HOME, CUR)['expenses']
    pairs = A._pair_transfers(ME)
    db.session.commit()
    after = A._entity_report(ME, HOME, CUR)
    check('the pair is found', pairs >= 1, pairs)
    check('a $9,000 move stops being $9,000 of spending',
          near(after['expenses'], before - 9000.00), (before, after['expenses']))
    check('and joins the moved total instead',
          near(after['transfers_out'], 7500.00 + 2178.00 + 9000.00), after['transfers_out'])

    print('\n--- "at this rate" is measured over the records, not the calendar ---')
    ev = A._expense_view([
        type('T', (), {'amount': 1000.00, 'posted_at': date(CUR, 6, 1)})(),
        type('T', (), {'amount': 1000.00, 'posted_at': date(CUR, 8, 29)})(),
    ], CUR, today=date(CUR, 12, 31))
    days = (date(CUR, 8, 29) - date(CUR, 6, 1)).days + 1
    yr_days = (date(CUR, 12, 31) - date(CUR, 1, 1)).days + 1
    check('the span is the first record to the last', ev['days_covered'] == days,
          (ev['days_covered'], days))
    check('the rate uses that span', near(ev['annualized'], 2000.0 * yr_days / days, 1.0),
          (ev['annualized'], 2000.0 * yr_days / days))
    check('and it is marked as not reaching January', ev['partial_history'] is True, ev)
    # The bug this replaces: 2000 / 0.9973 of a year elapsed = $2,005, where the ledger's
    # own 90 days imply $8,111. Understated by a factor of four.
    check('the elapsed-year denominator would have understated it four-fold',
          ev['annualized'] > 4 * 2000.0, ev['annualized'])

    print('\n--- a window too short to carry a rate does not get one ---')
    thin = A._expense_view([
        type('T', (), {'amount': 900.00, 'posted_at': TODAY - timedelta(days=3)})(),
        type('T', (), {'amount': 100.00, 'posted_at': TODAY})(),
    ], CUR)
    check('no annualized figure is offered', thin['annualized'] is None, thin)
    check('it says why', thin['thin'] is True, thin)
    check('but the actual total is still reported', near(thin['total'], 1000.00), thin)

    print('\n--- the window closes at the last record ---')
    # Charging the rate for the stretch since the final transaction would read as a
    # slowdown that has not happened; the income side closes its window the same way.
    ev2 = A._expense_view([
        type('T', (), {'amount': 500.00, 'posted_at': date(CUR, 1, 1)})(),
        type('T', (), {'amount': 500.00, 'posted_at': date(CUR, 3, 1)})(),
    ], CUR, today=date(CUR, 12, 31))
    check('it ends on the last record, not in December',
          ev2['covered_through'] == date(CUR, 3, 1).isoformat(), ev2['covered_through'])
    check('an empty ledger reports no span at all',
          A._expense_view([], CUR)['days_covered'] == 0
          and A._expense_view([], CUR)['annualized'] is None, A._expense_view([], CUR))

    print('\n--- an arrival with no other half is surfaced, not silently zeroed ---')
    # Already paired above: the $9,000. It has an other half and must not be listed.
    arrive(RECENT, 'Deposit from Brokerage - 5930', 2852.16, pa='acc_chk')
    arrive(RECENT, 'Mobile Check Deposit', 3211.46, pa='acc_sav')
    arrive(RECENT, 'PAYCHECK', 1800.00, kind='income', pa='acc_chk')
    db.session.commit()
    ua = A._unpaired_arrivals(ME)
    descs = {a['description'] for a in ua['arrivals']}
    check('the unmatched arrivals are listed', ua['count'] == 2, (ua['count'], sorted(descs)))
    check('with their total', near(ua['total'], 2852.16 + 3211.46), ua['total'])
    check('the brokerage drawdown is there', 'Deposit from Brokerage - 5930' in descs, descs)
    check('a deposit that HAS an other half is not listed',
          'SoFi Bank TRANSFER' not in descs, descs)
    check('and income is not listed either -- it is already counted',
          'PAYCHECK' not in descs, descs)
    check('the account it landed in travels with it',
          all(a.get('account_name') for a in ua['arrivals']), ua['arrivals'])

    print('\n--- naming one resolves it ---')
    src = IncomeSource(user_id=ME, name='Commissions', pay_frequency='irregular',
                       irregular=True, active=True, entity_id=HOME)
    db.session.add(src)
    db.session.commit()
    row = PlaidDeposit.query.filter_by(description='Mobile Check Deposit').first()
    row.income_source_id = src.id
    db.session.commit()
    ua2 = A._unpaired_arrivals(ME)
    check('an arrival tied to an income source drops off the queue',
          ua2['count'] == 1, [a['description'] for a in ua2['arrivals']])
    check('and the total follows it down', near(ua2['total'], 2852.16), ua2['total'])

    print('\n--- the window and the list are bounded ---')
    old = arrive(date(CUR - 1, 5, 1), 'LAST YEAR MOVE', 999.00, pa='acc_chk')
    db.session.commit()
    inside = A._unpaired_arrivals(ME, date(CUR, 1, 1), date(CUR, 12, 31))
    check("last year's arrival is outside this year's books",
          'LAST YEAR MOVE' not in {a['description'] for a in inside['arrivals']},
          [a['description'] for a in inside['arrivals']])
    check('with no window it is found', A._unpaired_arrivals(ME)['count'] == 2,
          A._unpaired_arrivals(ME)['count'])
    capped = A._unpaired_arrivals(ME, limit=1)
    check('a capped list still counts everything waiting',
          capped['count'] == 2 and len(capped['arrivals']) == 1 and capped['truncated'] is True,
          capped)

    print('\n--- the books report carries the queue')
    with A.app.test_request_context('/api/finance/entities/report?year=%d' % CUR):
        rows = [A._entity_report(ME, e.id, CUR) for e in (home, shop)]
    check('every book carries its own span', all(r.get('expense_span') for r in rows), rows[0].keys())
    check('and its own moved total', all('transfers_out' in r for r in rows))
    for k in ('transfers_out', 'transfer_count', 'expense_span'):
        check('the report exposes %s' % k, k in rows[0], sorted(rows[0].keys()))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BOOKS TRANSFER CHECKS PASSED')
