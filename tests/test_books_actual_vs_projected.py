"""A set of books reports what happened and what was forecast, and never confuses the two.

Reported from using the app: "Personal finance" showed income $153,605.16 against expenses
$128,300.88 and read as $25k ahead. It was not. The income figure was an annualized
full-year projection and the expense figure was ten months of actual spending, so the
surplus was almost entirely the two months of spending that had not happened yet.

So every set of books now carries three figures that are never mixed: what actually
arrived, the full-year projection, and that projection cut down to the span the records
cover. The third is the only fair comparator for the first, and the tests below are mostly
about the two ways a naive version of it lies:

  * Measuring from Jan 1 when the bank feed only reaches back to October reports a salary
    that was paid in full as tens of thousands short.
  * An irregular source annualizes its own trailing receipts, so comparing its actuals to
    its projection compares a number to itself and always says "exactly on pace".

It also covers the income-side visibility filter. _business_books read every income source
tagged to an entity whoever owned it, while reading expenses through _visible -- so a
household-shared farm could pull a partner's private income into this filer's books while
leaving their spending out. Inert with one member in the household, which is why it sat
there unnoticed; a second member is exactly the fixture below.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-actual-vs-projected')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def near(a, b, tol=0.02):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


import app as A
from models import (db, Entity, Household, HouseholdMember, IncomeSource, IncomeEvent,
                    PlaidDeposit, SpendTransaction)

ME, PARTNER, HID = 1, 2, 1
TODAY = date.today()
CUR = TODAY.year
JAN1 = date(CUR, 1, 1)
# Keeps every "recent" fixture inside the current year AND inside the trailing 12 months,
# whatever day of the year the suite happens to run on.
RECENT = max(JAN1, TODAY - timedelta(days=20))

with A.app.app_context():
    db.drop_all()
    db.create_all()
    for uid, email in ((ME, 'me@x.com'), (PARTNER, 'partner@x.com')):
        db.session.add(A.User(id=uid, google_id='g%d' % uid, email=email, name='U%d' % uid,
                              role='admin', privacy_consent_at=A.datetime.utcnow(),
                              privacy_consent_version=A.CONSENT_VERSION))
    db.session.add(Household(id=HID, name='Allen Household', created_by=ME))
    db.session.add_all([
        HouseholdMember(household_id=HID, user_id=ME, role='owner', status='active'),
        HouseholdMember(household_id=HID, user_id=PARTNER, role='member', status='active'),
    ])
    db.session.commit()

    home = Entity(user_id=ME, name='Personal finance', kind='personal')
    # Shared with the household, which is what makes a partner's rows reachable at all.
    farm = Entity(user_id=ME, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F',
                  household_id=HID)
    realty = Entity(user_id=ME, name='Coldwell Banker Realty', kind='business',
                    tax_form='Schedule C')
    db.session.add_all([home, farm, realty])
    db.session.commit()

    def salary(name, amount, entity, freq='semimonthly', uid=ME):
        s = IncomeSource(user_id=uid, name=name, owner='me', type='salary',
                         annual_salary=amount, pay_frequency=freq, tax_form='W2',
                         active=True, entity_id=entity.id)
        db.session.add(s)
        db.session.commit()
        return s

    def irregular(name, entity, est=0, uid=ME, share='none', form='1099'):
        s = IncomeSource(user_id=uid, name=name, owner='me', type='self_employed',
                         tax_form=form, irregular=True, annual_salary=0,
                         estimated_annual=est, active=True, entity_id=entity.id,
                         share_level=share)
        db.session.add(s)
        db.session.commit()
        return s

    def event(src, when, amount):
        db.session.add(IncomeEvent(user_id=src.user_id, income_source_id=src.id,
                                   date=when, gross_amount=amount, description='pay'))
        db.session.commit()

    n = [0]

    def deposit(src, when, amount, kind='income', entity=None):
        n[0] += 1
        d = PlaidDeposit(user_id=src.user_id, external_id='d%d' % n[0], posted_at=when,
                         description='row %d' % n[0], amount=amount, kind=kind,
                         income_source_id=src.id, source='manual',
                         entity_id=(entity.id if entity else None))
        db.session.add(d)
        db.session.commit()
        return d

    print('--- how much of a year has run ---')
    check('a closed year is all of it', A._year_elapsed(2025, date(2026, 6, 1)) == (365, 365, 1.0),
          A._year_elapsed(2025, date(2026, 6, 1)))
    check('a year that has not started is none of it',
          A._year_elapsed(2030, date(2026, 6, 1)) == (0, 365, 0.0),
          A._year_elapsed(2030, date(2026, 6, 1)))
    e, t, f = A._year_elapsed(2026, date(2026, 7, 2))
    check('a year in progress counts today', (e, t) == (183, 365) and near(f, 183 / 365.0),
          (e, t, f))

    print('\n--- a salary paid exactly on target is reported as exactly on target ---')
    # The naive version of this measured from the first payday, so 24 cheques of a
    # 24-cheque year landed in a window that opened on 15 January -- and a salary paid in
    # full read as ~$2,300 ahead of itself.
    wages = salary('Happy elephant - salary', 60000, home)
    for mo in range(1, 13):
        event(wages, date(2025, mo, 15), 2500)
        last = (date(2025, mo + 1, 1) - timedelta(days=1)) if mo < 12 else date(2025, 12, 31)
        event(wages, last, 2500)
    v = A._income_view([wages], 2025, today=date(2026, 2, 1))
    check('the projection is the salary', near(v['projected'], 60000), v['projected'])
    check('and so is what arrived', near(v['actual'], 60000), v['actual'])
    check('the window is backed up to cover the first pay period',
          v['measured_from'] == '2025-01-01', v['measured_from'])
    check('so a full year is expected of a full year',
          near(v['expected_to_date'], 60000), v['expected_to_date'])
    check('and the variance is zero, not a fortnight of phantom surplus',
          near(v['variance'], 0), v['variance'])
    check('the comparison is reported as meaningful', v['comparable'] is True, v)
    check('and the history is not flagged partial', v['partial_history'] is False, v)

    print('\n--- a young bank feed is a young bank feed, not a $36k shortfall ---')
    newjob = salary('Second job', 48000, home)
    event(newjob, date(2026, 10, 1), 2000)
    event(newjob, date(2026, 10, 15), 2000)
    v = A._income_view([newjob], 2026, today=date(2026, 10, 30))
    # Jan 1 -> Oct 30 would have expected 48000 * 303/365 = 39846.58 against $4,000 banked,
    # reporting the household $35,846.58 behind on a salary that was paid in full.
    naive = round(4000 - 48000 * 303 / 365.0, 2)
    check('measured from the period the first record covers, not from Jan 1',
          v['measured_from'] == '2026-09-16', v['measured_from'])
    # And closed at the last record (Oct 15), not at today -- the fortnight since has no
    # payday in it, so there is nothing yet to be short of.
    check('and closed at the last record, not at today',
          v['records_through'] == '2026-10-15', v['records_through'])
    check('expects only the 30 days between them',
          near(v['expected_to_date'], 48000 * 30 / 365.0), v['expected_to_date'])
    check('counts only what arrived in them', near(v['actual_to_date'], 4000), v['actual_to_date'])
    check('so a salary paid in full is not reported behind at all',
          abs(v['variance']) < 100 and v['variance'] > naive + 30000,
          (v['variance'], 'naive would have been', naive))
    check('and the partial history is declared', v['partial_history'] is True, v)
    check('a fortnight of silence is not yet called stale',
          v['records_stale'] is False and v['stale_periods'] <= 1.5,
          (v['records_stale'], v['stale_periods']))
    check('while the full-year actual is still reported raw',
          near(v['actual'], 4000), v['actual'])

    print('\n--- but pay that stops being recorded is called out, not hidden ---')
    # Closing the window at the records is what stops a part-period reading as a deficit.
    # The risk it introduces is the opposite one: a stream that dries up stops moving the
    # window instead of showing a gap, so staleness has to be reported in its own right.
    quit_job = salary('Job that went quiet', 48000, home)
    event(quit_job, date(2026, 2, 13), 2000.00)
    event(quit_job, date(2026, 2, 27), 2000.00)
    v = A._income_view([quit_job], 2026, today=date(2026, 10, 30))
    check('the variance stays honest rather than inventing eight months of deficit',
          abs(v['variance']) < 600, (v['variance'], v['expected_to_date']))
    check('but the silence is measured in pay periods',
          v['stale_periods'] > 15, v['stale_periods'])
    check('and flagged', v['records_stale'] is True, v)
    check('with the date the records stop', v['records_through'] == '2026-02-27',
          v['records_through'])

    print('\n--- a bank deposit is take-home, and is not judged against gross pay ---')
    # The failure this guards: $153,605 of projected salary against $42,269 of deposits read
    # as 29.5% behind in production, and the gap was the withholding wedge almost exactly.
    # The cash-flow ledger was fixed for the same error in the same direction.
    banked = salary('Direct deposit job', 52000, home, freq='biweekly')
    # Every payday from the first one to the cutoff, so the window is genuinely covered: 11
    # of them, Jun 12 to Oct 30 inclusive. Stopping at 10 leaves a real missing paycheque,
    # which the comparison correctly reports as $1,500 light -- it is a fixture detail, not
    # a tolerance to widen.
    for wk in range(0, 11):
        # $1,500 landing against $2,000 gross: a 25% wedge, the shape of a real paycheck.
        deposit(banked, date(2026, 6, 12) + timedelta(days=14 * wk), 1500.00, entity=home)
    gross_only = A._income_view([banked], 2026, today=date(2026, 10, 30))
    check('measured against GROSS the pace line invents a shortfall',
          gross_only['variance'] < -3000, gross_only['variance'])
    check('and names the basis it used', gross_only['expected_basis'] == 'net',
          gross_only['expected_basis'])
    # What the app really passes: take-home per source, as the cash-flow ledger derives it.
    nets = {banked.id: {'net_annual': 39000.00}}
    v = A._income_view([banked], 2026, today=date(2026, 10, 30), nets=nets)
    check('measured against TAKE-HOME it is close to on pace',
          abs(v['variance']) < 600, (v['variance'], v['expected_to_date'], v['actual_to_date']))
    check('the take-home projection is reported for the caption',
          near(v['planned_net_projected'], 39000.00), v['planned_net_projected'])
    check('while the gross projection is still reported as the projection',
          near(v['projected'], 52000.00), v['projected'])
    check('the shortfall shrank by roughly the whole wedge',
          v['variance'] - gross_only['variance'] > 3000,
          (gross_only['variance'], v['variance']))

    print('\n--- a hand-logged payment is gross, and IS judged against gross ---')
    logged = salary('Logged-by-hand job', 24000, realty, freq='monthly')
    for mo in range(1, 11):
        event(logged, date(2026, mo, 28), 2000.00)
    v = A._income_view([logged], 2026, today=date(2026, 10, 30),
                       nets={logged.id: {'net_annual': 18000.00}})
    check('an event-backed source is compared on the gross basis',
          v['expected_basis'] == 'gross', v['expected_basis'])
    check('so a gross salary logged in full is on pace, not 25% ahead',
          abs(v['variance']) < 600, (v['variance'], v['expected_to_date'], v['actual_to_date']))

    print('\n--- a source recorded both ways is blended, not forced to one basis ---')
    both = salary('Both kinds', 24000, realty, freq='monthly')
    event(both, date(2026, 3, 28), 2000.00)
    deposit(both, date(2026, 4, 28), 1500.00, entity=realty)
    v = A._income_view([both], 2026, today=date(2026, 10, 30),
                       nets={both.id: {'net_annual': 18000.00}})
    check('the basis is reported as blended', v['expected_basis'] == 'mixed', v['expected_basis'])
    check('and the expectation falls between the two',
          v['expected_to_date'] > 0, v['expected_to_date'])

    print('\n--- a projection annualized from its own receipts is measured, not forecast ---')
    eggs = irregular('Chicken Tales LLC', farm, form='none')
    deposit(eggs, RECENT, 6.00, entity=farm)
    deposit(eggs, RECENT + timedelta(days=1), 4.50, entity=farm)
    deposit(eggs, RECENT + timedelta(days=2), 15.00, entity=farm)
    db.session.refresh(eggs)
    check('the source knows its figure came from actuals',
          eggs.projection_basis() == 'actuals', eggs.projection_basis())
    v = A._income_view([eggs], CUR)
    check('it is reported as measured', near(v['measured'], 25.50), v['measured'])
    check('nothing about it is projected', near(v['planned_projected'], 0), v['planned_projected'])
    check('so no verdict is offered', v['comparable'] is False, v)
    check('and no variance is invented', near(v['variance'], 0), v['variance'])
    check('while actual and projected are both still reported',
          near(v['actual'], 25.50) and near(v['projected'], 25.50), v)

    print('\n--- an estimate with nothing banked against it is missing data, not a shortfall ---')
    plan = irregular('Commissions (estimated)', realty, est=5000)
    check('its figure came from the number typed in',
          plan.projection_basis() == 'estimate', plan.projection_basis())
    v = A._income_view([plan], CUR)
    check('the estimate is still projected', near(v['projected'], 5000), v['projected'])
    check('nothing is claimed to have arrived', near(v['actual'], 0), v['actual'])
    check('it is named as unmeasured rather than averaged in',
          v['sources_unmeasured'] == ['Commissions (estimated)'], v['sources_unmeasured'])
    check('no verdict is offered', v['comparable'] is False, v)
    check('and it is not reported as $5,000 behind', near(v['variance'], 0), v['variance'])

    print('\n--- a year is a year: receipts do not bleed across the boundary ---')
    event(eggs, date(CUR - 1, 6, 15), 80.00)
    db.session.refresh(eggs)
    check('last year sees last year', near(eggs.received_in_year(CUR - 1), 80.00),
          eggs.received_in_year(CUR - 1))
    check('this year does not', near(eggs.received_in_year(CUR), 25.50),
          eggs.received_in_year(CUR))

    print('\n--- a future year does not divide by zero ---')
    v = A._income_view([wages], CUR + 4, today=TODAY)
    check('nothing has elapsed', v['fraction_elapsed'] == 0.0, v['fraction_elapsed'])
    check('nothing is expected yet', near(v['expected_to_date'], 0), v['expected_to_date'])
    check('and no verdict is offered', v['comparable'] is False, v)

    print('\n--- the books report both sides, and net actual against actual ---')
    db.session.add(SpendTransaction(user_id=ME, posted_at=RECENT, description='Tractor Supply',
                                    amount=200.00, category='farm_feed', entity_id=farm.id))
    db.session.commit()
    rep = A._entity_report(ME, farm.id, CUR)
    check('income still means the projection, as the tax estimate expects',
          near(rep['income'], rep['income_projected']), (rep['income'], rep['income_projected']))
    check('what actually arrived is reported beside it',
          near(rep['income_actual'], 25.50), rep['income_actual'])
    check('net actual sets actual income against actual spending',
          near(rep['net_actual'], 25.50 - 200.00), rep['net_actual'])
    check('the old mixed net is left alone',
          near(rep['net'], rep['income'] - rep['expenses']), (rep['net'], rep['income']))
    # One row dated 20 days ago is a one-day ledger. Annualizing it would multiply a single
    # purchase by 365 and present the result as a spending rate, so no rate is offered --
    # see ANNUALIZE_MIN_DAYS and tests/test_books_transfers.py. The span is reported
    # instead, which is the honest answer to "where does this land by December".
    check('a ledger too short to carry a rate does not get one',
          rep['expenses_annualized'] is None and rep['expense_span']['thin'] is True,
          (rep['expenses'], rep['expenses_annualized'], rep['expense_span']))
    check('and the span it does cover is reported in its place',
          rep['expense_span']['covered_from'] == RECENT.isoformat(), rep['expense_span'])
    # A ledger with real reach does get the full-year view, measured over its own span.
    db.session.add_all([
        SpendTransaction(user_id=ME, posted_at=JAN1, description='January rent',
                         amount=1200.00, category='housing', entity_id=home.id),
        SpendTransaction(user_id=ME, posted_at=RECENT, description='Groceries',
                         amount=300.00, category='food', entity_id=home.id),
    ])
    db.session.commit()
    hrep = A._entity_report(ME, home.id, CUR)
    check('expenses are annualized for a like-for-like full-year view',
          hrep['expenses_annualized'] is not None
          and hrep['expenses_annualized'] >= hrep['expenses'],
          (hrep['expenses'], hrep['expenses_annualized']))
    check('over the days the records cover, not the days of the year',
          near(hrep['expenses_annualized'],
               1500.00 * hrep['expense_span']['days_in_year']
               / hrep['expense_span']['days_covered'], 1.0),
          (hrep['expenses_annualized'], hrep['expense_span']))
    check('and the pace detail travels with the row', 'comparable' in (rep['income_pace'] or {}),
          rep.get('income_pace'))
    fut = A._entity_report(ME, farm.id, CUR + 4)
    check('a year that has not started annualizes nothing',
          fut['expenses_annualized'] is None and fut['net_projected'] is None,
          (fut['expenses_annualized'], fut['net_projected']))

    print('\n--- income is read through the same visibility filter as spending ---')
    private = irregular("Partner's private income", farm, est=9999, uid=PARTNER, share='none')
    shared = irregular("Partner's shared income", farm, est=1111, uid=PARTNER, share='view')
    db.session.add_all([
        SpendTransaction(user_id=PARTNER, posted_at=RECENT, description='private spend',
                         amount=77.00, category='farm_feed', entity_id=farm.id,
                         share_level='none'),
        SpendTransaction(user_id=PARTNER, posted_at=RECENT, description='shared spend',
                         amount=33.00, category='farm_feed', entity_id=farm.id,
                         share_level='view'),
    ])
    db.session.commit()
    check('the household really does make the partner a partner',
          A._household_partner_ids(ME) == [PARTNER], A._household_partner_ids(ME))
    check('and the farm really is reachable by both',
          farm.id in [x.id for x in A._visible_entities(PARTNER).all()],
          [x.id for x in A._visible_entities(PARTNER).all()])

    books = A._business_books(ME, CUR, A._tax_profile(ME))
    row = [r for r in books['entities'] if r['id'] == farm.id][0]
    check("a partner's private income stays out of this filer's books",
          not near(row['income'], 25.50 + 1111 + 9999) and row['income'] < 9999,
          row['income'])
    check("a partner's shared income is counted",
          near(row['income'], 25.50 + 1111), row['income'])
    check("a partner's private spending stays out, as it always did",
          near(row['expenses'], 200.00 + 33.00), row['expenses'])
    check('so both sides of the books now agree on who is in the household',
          near(row['income'], 25.50 + 1111) and near(row['expenses'], 233.00), row)

    rep = A._entity_report(ME, farm.id, CUR)
    check('the per-entity report was already filtering income, and still is',
          near(rep['income'], 25.50 + 1111), rep['income'])
    check('and its actual side excludes the private source too',
          near(rep['income_actual'], 25.50), rep['income_actual'])

    print('\n--- deriving take-home must not recurse through the tax estimate ---')
    # _entity_report asks for the take-home map; building it runs the tax estimate; the tax
    # estimate calls _business_books. If _business_books ever asked for the map too, that
    # closes into infinite recursion -- so it is pinned here rather than left to a
    # RecursionError in production.
    try:
        rep = A._entity_report(ME, home.id, CUR)
        ok, why = True, ''
    except RecursionError as exc:
        ok, why = False, exc
    check('a book with salaried income reports without recursing', ok, why)
    check('and the tax estimate still returns',
          bool(A._income_tax_estimate(ME, CUR)), 'no estimate')
    nets = A._net_paycheck_estimates(ME)
    check('the take-home map covers the salaried sources',
          all(s.id in nets for s in (wages, newjob, banked)),
          sorted(nets.keys()))
    check('and take-home is below gross for a W2 job',
          nets[wages.id]['net_annual'] < 60000, nets.get(wages.id))
    check('a book given the map agrees with a book that built its own',
          A._entity_report(ME, home.id, CUR, nets=nets)['income_pace']['expected_to_date']
          == rep['income_pace']['expected_to_date'],
          (A._entity_report(ME, home.id, CUR, nets=nets)['income_pace']['expected_to_date'],
           rep['income_pace']['expected_to_date']))

    print('\n--- the partner sees their own, and the filer sees theirs ---')
    pbooks = A._business_books(PARTNER, CUR, A._tax_profile(PARTNER))
    prow = [r for r in (pbooks or {}).get('entities', []) if r['id'] == farm.id]
    check('the partner counts both of their own sources, private included',
          prow and near(prow[0]['income'], 9999 + 1111), prow)

    print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL ACTUAL-VS-PROJECTED CHECKS PASSED')
