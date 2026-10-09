"""Pay schedules that real payroll departments actually run.

Two things the projection could not express, both of which put every future payday on the
wrong date:

  1. SEMIMONTHLY MEANT THE 1ST AND THE 15TH. An employer paying the 10th and the 25th had
     no way to say so. Set as semimonthly the dates were simply wrong; set as biweekly --
     the obvious workaround -- they drifted a further day out every month, because 24
     paydays a year is not 26.

  2. A PAYDAY ON A WEEKEND WAS LEFT ON THE WEEKEND. Payroll pulls it to the Friday or
     pushes it to the Monday, and nothing in the schedule knew that. The household this
     came from is paid the Friday before, so two of their next five paydays were wrong.

The subtle one is that the weekend adjustment must apply to the date REPORTED and never to
the date the schedule steps from. Roll the anchor itself and the error compounds: pay the
25th on Friday the 23rd, step from the 23rd, and the schedule walks off its own days.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-paydates')

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


import app as A
from models import db, IncomeSource, _roll_off_weekend

UID = 1


def iso(dates):
    return [d.isoformat() for d in dates]


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='pay@x.com', name='Pay',
                          role='admin', privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.commit()

    print('--- rolling a date off the weekend ---')
    sat, sun, mon = date(2026, 10, 10), date(2026, 10, 25), date(2026, 11, 9)
    check('Saturday moves back to Friday',
          _roll_off_weekend(sat, 'before') == date(2026, 10, 9))
    check('Sunday moves back to Friday',
          _roll_off_weekend(sun, 'before') == date(2026, 10, 23))
    check('Saturday moves forward to Monday',
          _roll_off_weekend(sat, 'after') == date(2026, 10, 12))
    check('Sunday moves forward to Monday',
          _roll_off_weekend(sun, 'after') == date(2026, 10, 26))
    check('a weekday is left alone', _roll_off_weekend(mon, 'before') == mon)
    check("'none' leaves a Saturday on Saturday", _roll_off_weekend(sat, 'none') == sat)

    print('\n--- the 10th and the 25th, paid the Friday before ---')
    wife = IncomeSource(id=10, user_id=UID, name='Genesee', owner='spouse', type='salary',
                        annual_salary=45150.72, pay_frequency='semimonthly', tax_form='W2',
                        active=True, next_pay_date=date(2026, 10, 10),
                        pay_day_2=25, weekend_rule='before')
    db.session.add(wife)
    db.session.commit()

    got = iso(wife.upcoming_paydates(7))
    check('the pair is recognised', wife.semimonthly_days() == (10, 25),
          wife.semimonthly_days())
    check('Sat Oct 10 is paid Fri Oct 9', got[0] == '2026-10-09', got)
    check('Sun Oct 25 is paid Fri Oct 23', got[1] == '2026-10-23', got)
    check('Tue Nov 10 is untouched', got[2] == '2026-11-10', got)
    check('Wed Nov 25 is untouched', got[3] == '2026-11-25', got)
    check('Dec keeps both days', got[4:6] == ['2026-12-10', '2026-12-25'], got)
    # The compounding check: if the roll had been applied to the anchor, stepping from
    # Fri the 23rd would have produced the 8th here instead of the 10th rolled to the 8th.
    check('and January is still anchored to the 10th',
          got[6] == '2027-01-08', got)          # Sat Jan 10 -> Fri Jan 8
    check('24 paydays a year, not 26', len(wife.upcoming_paydates(24)) == 24)
    jan_to_dec = wife.upcoming_paydates(24)
    # 24 paydays is 23 half-month steps, so a bit under a full year from the first.
    check('spanning roughly a year', 340 <= (jan_to_dec[-1] - jan_to_dec[0]).days <= 360,
          (jan_to_dec[0], jan_to_dec[-1]))

    print('\n--- the old 1st-and-15th behaviour is untouched ---')
    legacy = IncomeSource(id=11, user_id=UID, name='Legacy', owner='me', type='salary',
                          annual_salary=60000, pay_frequency='semimonthly', tax_form='W2',
                          active=True, next_pay_date=date(2026, 11, 1))
    db.session.add(legacy)
    db.session.commit()
    check('no second day declared means no pair', legacy.semimonthly_days() is None)
    check('and it still steps 1st, 15th, 1st',
          iso(legacy.upcoming_paydates(3)) == ['2026-11-01', '2026-11-15', '2026-12-01'],
          iso(legacy.upcoming_paydates(3)))

    print('\n--- biweekly is unaffected by any of this ---')
    biw = IncomeSource(id=12, user_id=UID, name='Hourly', owner='me', type='hourly',
                       annual_salary=71780, pay_frequency='biweekly', tax_form='W2',
                       active=True, next_pay_date=date(2026, 10, 15))
    db.session.add(biw)
    db.session.commit()
    check('it still steps a fortnight',
          iso(biw.upcoming_paydates(3)) == ['2026-10-15', '2026-10-29', '2026-11-12'],
          iso(biw.upcoming_paydates(3)))
    biw.weekend_rule = 'before'
    db.session.commit()
    # Sat 2026-11-28 would be the third; with the rule it reports Fri the 27th but the
    # fortnightly rhythm must not shift.
    biw.next_pay_date = date(2026, 11, 14)      # a Saturday
    db.session.commit()
    got2 = iso(biw.upcoming_paydates(3))
    check('a weekend payday reports the Friday', got2[0] == '2026-11-13', got2)
    check('but the next one is still 14 days from the NOMINAL date',
          got2[1] == '2026-11-27', got2)        # Sat Nov 28 -> Fri Nov 27

    print('\n--- the API accepts and validates the new fields ---')
    def cli():
        """A fresh client per call -- the login session does not survive a request here."""
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess['_user_id'] = str(UID)
            sess['_fresh'] = True
        return c

    r = cli().put('/api/finance/incomes/10', json={'pay_day_2': 25, 'weekend_rule': 'after'})
    check('a valid update is accepted', r.status_code == 200, (r.status_code, r.get_json()))
    r = cli().put('/api/finance/incomes/10', json={'pay_day_2': 44})
    check('a day out of range is rejected', r.status_code == 400, r.status_code)
    r = cli().put('/api/finance/incomes/10', json={'weekend_rule': 'sideways'})
    check('an unknown weekend rule is rejected', r.status_code == 400, r.status_code)
    j = cli().get('/api/finance/incomes').get_json() or {}
    rows = j.get('sources') or j.get('incomes') or []
    row = next((x for x in rows if x.get('id') == 10), None)
    check('the fields come back out', row and row.get('pay_day_2') == 25, row or j)
    check('along with the weekend rule', row and row.get('weekend_rule') == 'after',
          row and row.get('weekend_rule'))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PAY DATE CHECKS PASSED')
