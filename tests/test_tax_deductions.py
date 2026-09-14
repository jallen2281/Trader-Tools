"""The return, not just the wages: Schedule A, Schedule 1-A and the farm books.

The estimate knew wages, the standard deduction and the child credit. A household that has
never owed -- mortgage interest, property tax, a farm, overtime -- was told it would, because
none of that reached the number.

The case that shaped the design is a filed 2025 return that deducted the same $11,890 of
mortgage interest on Schedule A AND on Schedule F. So the business share is a carve-out
from the personal figure: whatever is claimed for the farm comes off Schedule A, and the
one payment can only be deducted once.
"""
import os
import sys
import tempfile
from datetime import date, datetime
from types import SimpleNamespace

TMP = tempfile.mkdtemp(prefix='taxded_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 'd.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
sys.path.insert(0, os.getcwd())

import app as A  # noqa: E402

app = A.app
app.config['TESTING'] = True
db = A.db
fails = []
YEAR = date.today().year


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


print('\n--- Schedule 1-A, straight off the form ---')
S = A._schedule_1a
ns = lambda ot=0, car=0: SimpleNamespace(qualified_overtime_annual=ot, car_loan_interest_annual=car)
check('overtime capped at $25,000 joint', S(ns(ot=30000), 'mfj', 150000)['overtime'] == 25000)
check('and $12,500 otherwise', S(ns(ot=30000), 'single', 100000)['overtime'] == 12500)
check('less $100 per FULL $1,000 over $300,000 joint',
      S(ns(ot=20000), 'mfj', 310500)['overtime'] == 19000, S(ns(ot=20000), 'mfj', 310500))
check('married filing separately cannot claim overtime', S(ns(ot=5000), 'mfs', 90000)['overtime'] == 0)
check('car loan interest capped at $10,000', S(ns(car=12000), 'mfj', 150000)['car_loan_interest'] == 10000)
check('less $200 per $1,000 rounded UP -- one dollar over costs $200',
      S(ns(car=8000), 'mfj', 200001)['car_loan_interest'] == 7800,
      S(ns(car=8000), 'mfj', 200001))
check('gone entirely $50,000 over the single threshold',
      S(ns(car=8000), 'single', 150000)['car_loan_interest'] == 0)

# ---------------------------------------------------------------- a household
with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=1, google_id='g1', email='u@x.com', name='U', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    db.session.flush()
    db.session.add(A.IncomeSource(user_id=1, name='Salary', type='salary', annual_salary=150000,
                                  pay_frequency='biweekly', tax_form='W2', owner='me', active=True))
    db.session.add(A.TaxProfile(user_id=1, filing_status='mfj',
                                ytd_federal_withheld=6000, ytd_as_of=date(YEAR, 7, 31)))
    db.session.commit()


def est():
    with app.app_context():
        return A._income_tax_estimate(1)


def set_prof(**kw):
    with app.app_context():
        p = A.TaxProfile.query.filter_by(user_id=1).first()
        for k, v in kw.items():
            setattr(p, k, v)
        db.session.commit()


base = est()
print('\n--- nothing entered: the standard deduction, as before ---')
check('standard deduction', base['deduction_basis_return'] == 'standard', base['deduction_basis_return'])
check('2026 joint amount', base['deduction_used_return'] == 32200, base['deduction_used_return'])
check('taxable = wages - standard deduction', base['taxable_income_return'] == 117800.0,
      base['taxable_income_return'])
check('no business section without books', base['business'] is None, base['business'])

print('\n--- itemizing, from the pieces ---')
with app.app_context():
    db.session.add(A.RecurringBill(user_id=1, name='Property tax - winter', category='taxes',
                                   amount=6126.93, frequency='annual', active=True))
    db.session.add(A.RecurringBill(user_id=1, name='Property tax - summer', category='taxes',
                                   amount=2744.82, frequency='annual', active=True))
    # Also in 'taxes', but not property tax -- must not be swept into the deduction.
    db.session.add(A.RecurringBill(user_id=1, name='Federal estimated payment', category='taxes',
                                   amount=1000, frequency='quarterly', active=True))
    db.session.commit()
set_prof(mortgage_interest_annual=20000, charitable_annual=1000)
e = est()
it = e['itemized']
check('property tax found by name', it['property_tax'] == 8871.75, it['property_tax'])
check('an estimated-tax payment is not property tax', it['property_tax'] < 9000, it['property_tax'])
check('state income tax joins it for SALT', it['salt'] == round(8871.75 + it['state_income_tax'], 2), it)
check('charity loses the first 0.5% of AGI when itemizing',
      it['charitable_allowed'] == 1000 - 750, it['charitable_allowed'])
check('itemizing wins when it beats standard + the non-itemizer charity amount',
      e['deduction_basis_return'] == 'itemized', e['deduction_basis_return'])
check('the itemized total is what is deducted',
      e['deduction_used_return'] == it['total'] == round(20000 + it['salt'] + 250, 2),
      (e['deduction_used_return'], it['total']))
check('and the bill drops', e['total_federal_tax'] < base['total_federal_tax'],
      (base['total_federal_tax'], e['total_federal_tax']))

print('\n--- ...but none of it is a raise ---')
check('take-home unchanged', e['take_home'] == base['take_home'])
check('wage income tax unchanged', e['federal_income_tax'] == base['federal_income_tax'])

print('\n--- the mortgage estimate when no 1098 is entered ---')
with app.app_context():
    db.session.add(A.Debt(user_id=1, name='1st Mortgage', type='mortgage', balance=342000,
                          apr=6.0, min_payment=3037.88))
    db.session.add(A.Debt(user_id=1, name='HELOC', type='heloc', balance=90000, apr=8.0,
                          min_payment=600))
    db.session.commit()
set_prof(mortgage_interest_annual=0)
e = est()
mi = e['itemized']['mortgage_interest']
check('a year of amortisation on the balance', 19500 < mi < 20500, mi)
check('labelled as an estimate', 'estimated' in e['itemized']['mortgage_interest_source'])
check('the HELOC is not counted', mi < 20500, mi)

print('\n--- the 2025 mistake: one payment on Schedule A and Schedule F ---')
with app.app_context():
    farm = A.Entity(user_id=1, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    db.session.add(farm)
    db.session.flush()
    fid = farm.id
    db.session.add(A.SpendTransaction(user_id=1, entity_id=fid, posted_at=date(YEAR, 3, 1),
                                      description='Feed', category='farm_feed', amount=1060.35))
    db.session.add(A.SpendTransaction(user_id=1, entity_id=fid, posted_at=date(YEAR, 4, 1),
                                      description='Vet', category='farm_vet', amount=300.40))
    db.session.add(A.SpendTransaction(user_id=1, entity_id=fid, posted_at=date(YEAR, 4, 2),
                                      description='To Savings', category='transfer', amount=5000))
    db.session.commit()
set_prof(mortgage_interest_annual=30529, business_mortgage_interest_annual=11890)
e = est()
it, biz = e['itemized'], e['business']
check('the farm share comes OFF Schedule A', it['mortgage_interest_personal'] == 30529 - 11890,
      it['mortgage_interest_personal'])
check('and onto the farm', biz['mortgage_interest'] == 11890, biz)
check('so the interest deducted in total is the 1098, never more',
      it['mortgage_interest_personal'] + biz['mortgage_interest'] == 30529)
check('farm books: tagged spending, transfers excluded', biz['books_net_so_far'] == -1360.75, biz)
check('net = books - the carved interest', biz['net'] == round(-1360.75 - 11890, 2), biz['net'])
check('source says it is the books', biz['source'] == 'books so far this year', biz['source'])
check('the farm loss lowers AGI', e['agi'] == round(150000 + biz['net'], 2), e['agi'])

print('\n--- a stated farm figure beats the books ---')
set_prof(business_net_annual=-14042)
e = est()
check('entered figure used', e['business']['net'] == -14042 and e['business']['source'] == 'entered',
      e['business'])
check('the books are still reported alongside', e['business']['books_net_so_far'] == -1360.75)
check('a loss adds no self-employment tax', e['self_employment_tax_return'] == 0.0,
      e['self_employment_tax_return'])

print('\n--- a farm PROFIT is self-employment income ---')
set_prof(business_net_annual=20000)
e = est()
check('SE tax on 92.35% of the profit at 15.3%', e['self_employment_tax_return'] == 2825.91,
      e['self_employment_tax_return'])
check('and it is in the total', e['total_federal_tax'] ==
      round(e['federal_income_tax_return'] + 2825.91, 2))

print('\n--- 1099 income tagged to the farm is not counted twice ---')
set_prof(business_net_annual=None)
with app.app_context():
    db.session.add(A.IncomeSource(user_id=1, name='Egg sales', type='other', estimated_annual=5000,
                                  irregular=True, tax_form='1099', entity_id=fid, active=True))
    db.session.commit()
e = est()
check('inside the farm books', e['business']['entities'][0]['income'] > 0, e['business'])
check('not also freestanding 1099 income', e['se_income'] == 0.0, e['se_income'])

print('\n--- the SALT cap and its phase-down ---')
with app.app_context():
    db.session.add(A.RecurringBill(user_id=1, name='Property tax - lake house', category='taxes',
                                   amount=50000, frequency='annual', active=True))
    db.session.commit()
    p = A.TaxProfile.query.filter_by(user_id=1).first()
    capped = A._itemized_deductions(1, p, 'mfj', 150000, 0)
    down = A._itemized_deductions(1, p, 'mfj', 600000, 0)
    floor = A._itemized_deductions(1, p, 'mfj', 2000000, 0)
    mfs = A._itemized_deductions(1, p, 'mfs', 150000, 0)
check('$40,400 cap', capped['salt'] == 40400, capped['salt'])
check('cut by 30% of MAGI over $505,000', down['salt_cap'] == 40400 - 0.30 * 95000, down['salt_cap'])
check('never below $10,000', floor['salt_cap'] == 10000, floor['salt_cap'])
check('half for married filing separately', mfs['salt_cap'] == 20200, mfs['salt_cap'])

print('\n--- the non-itemizer charity deduction ---')
with app.app_context():
    for b in A.RecurringBill.query.all():
        db.session.delete(b)
    for d in A.Debt.query.all():
        db.session.delete(d)
    db.session.commit()
set_prof(mortgage_interest_annual=0, business_mortgage_interest_annual=0, charitable_annual=1500)
with app.app_context():
    for t in A.SpendTransaction.query.all():
        db.session.delete(t)
    for x in A.IncomeSource.query.filter(A.IncomeSource.entity_id.isnot(None)).all():
        db.session.delete(x)
    db.session.commit()
e = est()
check('standard deduction kept', e['deduction_basis_return'] == 'standard', e['deduction_basis_return'])
check('and the gift comes off on top of it', e['charitable_nonitemizer'] == 1500, e['charitable_nonitemizer'])
check('taxable reflects both', e['taxable_income_return'] == round(150000 - 32200 - 1500, 2),
      e['taxable_income_return'])

print('\n--- saving the profile ---')
c = app.test_client()
with c.session_transaction() as sess:
    sess['_user_id'] = '1'
    sess['_fresh'] = True
r = c.put('/api/finance/tax-profile', json={'business_net_annual': '-22520.5', 'charitable_annual': -5,
                                            'qualified_overtime_annual': 1907})
pr = r.get_json()['profile']
check('a farm LOSS is stored signed', pr['business_net_annual'] == -22520.5, pr['business_net_annual'])
check('other amounts cannot go negative', pr['charitable_annual'] == 0.0, pr['charitable_annual'])
check('overtime saved', pr['qualified_overtime_annual'] == 1907.0)
r = c.put('/api/finance/tax-profile', json={'business_net_annual': ''})
check('blank means "use the books" again, not zero',
      r.get_json()['profile']['business_net_annual'] is None, r.get_json()['profile'])
r = c.get('/tax')
body = r.get_data(as_text=True)
check('the tax page has the new fields', r.status_code == 200 and 'tpBizMort' in body
      and 'tpBizNet' in body and 'tpOT' in body)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL RETURN / DEDUCTION CHECKS PASSED')
