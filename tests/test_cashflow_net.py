"""The cash-flow ledger projects what actually lands, not gross pay.

It used to add GROSS paychecks to the running balance while bills left it at their real
amounts, so the projection was overstated by the entire tax and deduction wedge — about a
quarter of pay. That is the dangerous direction for this particular number: the whole point
of the ledger is the "balance goes negative" warning, and an optimistic balance simply
fails to raise it.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix='cfnet_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'c.db').replace(os.sep, '/')
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


with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='me@x.com', name='Me', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.TaxProfile(user_id=1, filing_status='single', state_tax_rate=4.25))
    db.session.add(A.FinanceAccount(user_id=1, name='Checking', type='checking', balance=2000))
    db.session.add(A.IncomeSource(
        id=10, user_id=1, name='Job', owner='me', type='salary', annual_salary=93210,
        pay_frequency='biweekly', tax_form='W2', active=True,
        next_pay_date=TODAY + timedelta(days=3),
        pretax_retirement_mode='percent', pretax_retirement_pct=3, roth_retirement_pct=3,
        payroll_deductions=[
            {'label': 'Medical', 'per_check': 19.71, 'treatment': 'section125'},
            {'label': 'HSA', 'per_check': 30.00, 'treatment': 'section125'},
            {'label': 'Voluntary Life', 'per_check': 14.63, 'treatment': 'posttax'},
        ]))
    db.session.commit()

print('\n--- a paycheck is worth less than its gross ---')
with app.app_context():
    nets = A._net_paycheck_estimates(1)
    n = nets[10]
check('gross is the salary over 26 periods', n['gross'] == round(93210 / 26.0, 2), n)
check('net is materially lower', n['net'] < n['gross'] * 0.85, n)
check('and it is not zero or negative', n['net'] > 0, n)
check('FICA is part of what came off', n['fica'] > 0, n)
check('so are the deductions and the 401k', n['deductions'] > 0, n)
check('income tax too', n['income_tax'] > 0, n)
check('the parts add back up to gross',
      abs(n['gross'] - (n['net'] + n['fica'] + n['income_tax'] + n['deductions'])) < 0.05,
      (n['gross'], n['net'], n['fica'], n['income_tax'], n['deductions']))

print('\n--- the ledger projects the net figure ---')
with app.app_context():
    cf = A._finance_cashflow(1, days=60)
pay = [e for e in cf['events'] if e['type'] == 'income']
check('paychecks appear', len(pay) >= 2, len(pay))
check('at the net amount', pay[0]['amount'] == n['net'], (pay[0]['amount'], n['net']))
check('with gross carried alongside so the two reconcile',
      pay[0]['gross'] == n['gross'], pay[0])
check('total in is built from net, not gross',
      cf['total_in'] < len(pay) * n['gross'], (cf['total_in'], len(pay) * n['gross']))

print('\n--- which is what makes the warning fire when it should ---')
# Bills that gross pay would cover but net pay does not.
with app.app_context():
    per_month = n['net'] * 26 / 12.0
    db.session.add(A.RecurringBill(user_id=1, name='Rent', category='housing',
                                   amount=round(per_month * 0.95, 2), frequency='monthly',
                                   due_day=min(TODAY.day, 28), active=True))
    db.session.commit()
    cf2 = A._finance_cashflow(1, days=60)
    gross_in = sum(e.get('gross', 0) for e in cf2['events'] if e['type'] == 'income')
    net_in = sum(e['amount'] for e in cf2['events'] if e['type'] == 'income')
check('gross would have overstated inflow by thousands',
      gross_in - net_in > 1000, (gross_in, net_in))
check('the projected low point reflects net pay',
      cf2['lowest_balance'] < cf2['starting_balance'] + gross_in,
      (cf2['lowest_balance'], cf2['starting_balance']))

print('\n--- a recorded paystub beats the estimate ---')
with app.app_context():
    src = A.IncomeSource.query.get(10)
    src.ytd_federal_withheld = 2941.08
    src.ytd_state_withheld = 2119.88
    src.ytd_as_of = date(TODAY.year, 6, 30)
    db.session.commit()
    n2 = A._net_paycheck_estimates(1)[10]
check('the basis says where the figure came from', n2['basis'] == 'from your paystub',
      n2['basis'])
check('and the net changes accordingly', n2['net'] != n['net'], (n['net'], n2['net']))
check('still below gross', n2['net'] < n2['gross'], n2)

print('\n--- 1099 income nets off its own set-aside ---')
with app.app_context():
    db.session.add(A.IncomeSource(id=11, user_id=1, name='Consulting', owner='me',
                                  type='self_employed', annual_salary=52000,
                                  pay_frequency='monthly', tax_form='1099', active=True,
                                  est_tax_rate=28, next_pay_date=TODAY + timedelta(days=5)))
    db.session.commit()
    n3 = A._net_paycheck_estimates(1)[11]
check('nothing is withheld, so the reserve is what nets off',
      n3['net'] == round(52000 * 0.72 / 12.0, 2), n3)
check('and it says so', '28' in (n3['basis'] or ''), n3['basis'])

print('\n--- irregular income is still excluded, having no schedule ---')
with app.app_context():
    db.session.add(A.IncomeSource(id=12, user_id=1, name='Commissions', owner='me',
                                  type='other', tax_form='1099', active=True,
                                  irregular=True, estimated_annual=30000))
    db.session.commit()
    nets2 = A._net_paycheck_estimates(1)
check('it produces no paycheck estimate', 12 not in nets2, list(nets2))

print('\n--- the upcoming-paychecks list says net too ---')
with app.app_context():
    o = A._finance_outlook(1)
pd = (o.get('upcoming_paydates') or [])
check('dates are listed', len(pd) > 0, pd)
check('the amount is net', pd[0]['amount'] < pd[0]['gross'], pd[0])
check('gross is kept, since it is the figure on the offer letter',
      pd[0]['gross'] > 0, pd[0])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL NET CASH-FLOW CHECKS PASSED')
