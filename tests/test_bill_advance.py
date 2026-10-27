"""A bill's due date keeps up with the calendar, and its due day does not erode.

Two faults in the same few lines, found with all sixteen of a household's bills stale and
the worst 56 days behind.

  1. A PAST DUE DATE WAS RETURNED VERBATIM. Nothing advances next_due_date when a bill is
     simply paid on time, and _anchor() handed the stored value back whatever its date. The
     bills list therefore showed dates weeks or months gone, and sorted by them.

     Worse than cosmetic: the projection asks for a BOUNDED number of occurrences, so a
     date far enough behind spent all of them before reaching today and the bill vanished
     from the forecast entirely. A 90-day-stale monthly bill disappeared from a 30-day
     window rather than showing up late.

  2. THE DUE DAY ERODED. Each step was taken from the previous step's CLAMPED result, so a
     bill due on the 31st passing through a 30-day month came back as the 30th -- and the
     next step started from the 30th. One short month moved it a day earlier for good;
     February moved it three. Over a year a month-end bill walked into mid-month.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-bill-advance')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, RecurringBill

UID = 1
TODAY = date.today()


def cli():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    return c


def bill(**kw):
    kw.setdefault('user_id', UID)
    kw.setdefault('category', 'other')
    kw.setdefault('amount', 100.00)
    kw.setdefault('active', True)
    b = RecurringBill(**kw)
    db.session.add(b)
    db.session.commit()
    return b


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='advance@x.com', name='Advance',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    print('--- the due day does not erode through a short month ---')
    # Jan 31 monthly. February can only offer the 28th, but March has a 31st and the bill
    # is still due on it.
    jan31 = bill(name='Month end', frequency='monthly', next_due_date=date(2027, 1, 31))
    seen = jan31.upcoming_due_dates(6, today=date(2027, 1, 1))
    check('january keeps the 31st', seen[0] == date(2027, 1, 31), seen)
    check('february clamps to the 28th', seen[1] == date(2027, 2, 28), seen)
    check('MARCH RETURNS TO THE 31st', seen[2] == date(2027, 3, 31), seen)
    check('april clamps to the 30th', seen[3] == date(2027, 4, 30), seen)
    check('may returns to the 31st', seen[4] == date(2027, 5, 31), seen)
    check('a year on it is still month end', seen[-1] == date(2027, 6, 30), seen)

    # due_day undoes a clamp: the anchor is on the last day of a short month and due_day
    # falls later, so the stored date is that month's rendering of a later day.
    eroded = bill(name='Stored clamped', frequency='monthly', due_day=31,
                  next_due_date=date(2027, 2, 28))
    seen = eroded.upcoming_due_dates(3, today=date(2027, 2, 1))
    check('due_day 31 recovers a clamped anchor', seen[1] == date(2027, 3, 31), seen)

    print('\n--- but a stale due_day does NOT override the anchor ---')
    # Both regressions from preferring due_day outright. The Amex really is due on the
    # 28th and carries a stale due_day of 2: taking the first date from the anchor and the
    # rest from due_day put two payments five days apart.
    amex = bill(name='Amex', frequency='monthly', amount=1062.62, due_day=2,
                next_due_date=date(2027, 1, 28))
    seen = amex.upcoming_due_dates(3, today=date(2027, 1, 1))
    check('the anchor day is kept', seen[0] == date(2027, 1, 28), seen)
    check('AND THE NEXT ONE IS A MONTH ON, not five days',
          seen[1] == date(2027, 2, 28), seen)
    check('the spacing stays monthly', seen[2] == date(2027, 3, 28), seen)
    check('no two occurrences land in the same week',
          all((seen[i + 1] - seen[i]).days >= 27 for i in range(len(seen) - 1)), seen)

    # And it must not rewrite a correct stored date when rolling forward: a bill really on
    # the 17th with a stale due_day of 16 was being moved to the 16th.
    asu = bill(name='ASU', frequency='monthly', amount=515.00, due_day=16,
               next_due_date=TODAY - timedelta(days=9))
    rolled = asu._anchor()
    check('rolling forward keeps the stored day, not the stale due_day',
          rolled.day == (TODAY - timedelta(days=9)).day,
          (rolled, TODAY - timedelta(days=9), asu.due_day))

    print('\n--- a past due date rolls forward to the next real one ---')
    stale = bill(name='Electric', frequency='monthly',
                 next_due_date=TODAY - timedelta(days=56))
    nxt = stale._anchor()
    check('the anchor is no longer in the past', nxt >= TODAY, nxt)
    check('and it keeps the original day of the month',
          nxt.day == (TODAY - timedelta(days=56)).day, nxt)
    check('upcoming dates all start from today or later',
          all(d >= TODAY for d in stale.upcoming_due_dates(3)), stale.upcoming_due_dates(3))

    weekly = bill(name='Weekly thing', frequency='weekly',
                  next_due_date=TODAY - timedelta(days=70))
    check('a weekly bill rolls too', weekly._anchor() >= TODAY, weekly._anchor())
    check('and lands on the same weekday',
          weekly._anchor().weekday() == (TODAY - timedelta(days=70)).weekday())

    annual = bill(name='Property tax', frequency='annual',
                  next_due_date=TODAY - timedelta(days=400))
    check('an annual bill rolls a whole year', annual._anchor() >= TODAY, annual._anchor())
    check('and stays in its own month',
          annual._anchor().month == (TODAY - timedelta(days=400)).month, annual._anchor())

    print('\n--- a one-off is finished, not overdue ---')
    # Rolling this forward would resurrect a payoff that has already happened.
    done = bill(name='Discover payoff', frequency='one_time', amount=2822.17,
                next_due_date=TODAY - timedelta(days=10))
    check('its anchor stays in the past', done._anchor() < TODAY, done._anchor())
    check('and it still yields exactly one date',
          done.upcoming_due_dates(12) == [TODAY - timedelta(days=10)],
          done.upcoming_due_dates(12))

    print('\n--- the regression: a stale bill stays in the forecast ---')
    # This is the money bug. _occurrences_for gives a 30-day window only 3 monthly
    # occurrences, so a 90-day-stale bill spent all three behind today and dropped out.
    for b in RecurringBill.query.filter(RecurringBill.name != 'Rent').all():
        b.active = False
    db.session.commit()
    rent = bill(name='Rent', frequency='monthly', amount=1500.00,
                next_due_date=TODAY - timedelta(days=90))
    proj = A._finance_cashflow(UID, days=30, starting_balance=5000.00)
    hits = [e for e in proj['events'] if e['label'] == 'Rent']
    check('a 90-day-stale monthly bill still appears', len(hits) >= 1,
          [e['label'] for e in proj['events']])
    check('and it is dated in the window',
          all(TODAY.isoformat() <= e['date'] <= (TODAY + timedelta(days=30)).isoformat()
              for e in hits), [e['date'] for e in hits])
    check('the projection spends it', proj['total_out'] >= 1500.00, proj['total_out'])

    print('\n--- the stored field is brought up to date ---')
    rent.next_due_date = TODAY - timedelta(days=90)
    db.session.commit()
    was = rent.next_due_date
    moved = A._advance_stale_bills(UID)
    db.session.refresh(rent)
    check('the stale bill is reported as moved',
          any(m['name'] == 'Rent' for m in moved), moved)
    check('and the column is written', rent.next_due_date >= TODAY, rent.next_due_date)
    check('the move says where it came from',
          any(m['from'] == was.isoformat() for m in moved), moved)
    check('running it again moves nothing', A._advance_stale_bills(UID) == [],
          A._advance_stale_bills(UID))

    # An inactive or one-off bill is never touched.
    db.session.refresh(done)
    check('the finished one-off was left alone',
          done.next_due_date == TODAY - timedelta(days=10), done.next_due_date)

    print('\n--- over the API ---')
    rent.next_due_date = TODAY - timedelta(days=45)
    db.session.commit()
    r = cli().post('/api/finance/bills/advance')
    check('the endpoint succeeds', r.status_code == 200, (r.status_code, r.get_json()))
    check('and reports the count', r.get_json()['advanced'] == 1, r.get_json())
    db.session.refresh(rent)
    check('the bill is current afterwards', rent.next_due_date >= TODAY, rent.next_due_date)

    print('\n--- a future date is left exactly as it is ---')
    soon = TODAY + timedelta(days=5)
    fine = bill(name='Netflix', frequency='monthly', next_due_date=soon)
    check('an untouched bill keeps its date', fine._anchor() == soon, fine._anchor())
    check('and is not reported as moved',
          not any(m['name'] == 'Netflix' for m in A._advance_stale_bills(UID)))

    print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BILL ADVANCE CHECKS PASSED')
