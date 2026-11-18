"""A bank deposit can be the same money as income already entered by hand -- and say so.

Written from a real one. The farm logs egg money by hand as it comes in: "Egg sales",
$36.00, 2026-11-17. The same day the bank fed in "Online Transfer from CHK ...7641",
$36.00 -- the buyer paying for those eggs. The app already had a way to say "this cheque is
income I logged by hand": tying the deposit to an IncomeEvent. But the farm's hand entries
are deposits, not events, so the tie list was empty, and the only filing left (naming
Chicken Tales as the source) would have counted the eggs twice.

And while doing it: a kind a person chose did not survive the bank re-sending the
transaction. _record_deposit re-ran the classifier on every delivery, so the refunds and
brokerage sales named the day before would go back to transfer_in on the next `modified`
or backfill.
"""
import os
import sys
import tempfile
from datetime import date

TMP = tempfile.mkdtemp(prefix='settles_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP, 's.db').replace(os.sep, '/')
os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
os.environ['TT_BACKGROUND_JOBS'] = '0'
sys.path.insert(0, os.getcwd())

import app as A                                    # noqa: E402
from models import db, Entity, IncomeSource, PlaidDeposit   # noqa: E402

fails = []
UID = 1
DAY = date(2026, 11, 17)


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def cli():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(UID)
        sess['_fresh'] = True
    return c


with A.app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add(A.User(id=UID, google_id='g1', email='s@x.com', name='S', role='admin',
                          privacy_consent_at=A.datetime.utcnow(),
                          privacy_consent_version=A.CONSENT_VERSION))
    farm = Entity(id=1, user_id=UID, name='Chicken Tales LLC', kind='farm', tax_form='Schedule F')
    home = Entity(id=2, user_id=UID, name='Personal finance', kind='personal')
    db.session.add_all([farm, home])
    db.session.commit()
    eggs = IncomeSource(id=15, user_id=UID, name='Chicken Tales LLC', owner='joint',
                        type='self_employed', tax_form='none', irregular=True,
                        annual_salary=0, estimated_annual=0, active=True, entity_id=1)
    other = IncomeSource(id=16, user_id=UID, name='Something else', owner='me',
                         type='self_employed', tax_form='none', irregular=True,
                         annual_salary=0, estimated_annual=0, active=True, entity_id=2)
    db.session.add_all([eggs, other])
    # Bank deposits, as the feed classifies them.
    db.session.add(PlaidDeposit(id=158, user_id=UID, external_id='plaid:mom-transfer',
                                plaid_account_id='chk', posted_at=DAY, amount=36.00,
                                description='Online Transfer from CHK ...7641', kind='transfer_in',
                                source='plaid'))
    db.session.add(PlaidDeposit(id=159, user_id=UID, external_id='plaid:another',
                                plaid_account_id='chk', posted_at=DAY, amount=36.00,
                                description='Online Transfer from CHK ...7641', kind='transfer_in',
                                source='plaid'))
    db.session.add(PlaidDeposit(id=33, user_id=UID, external_id='plaid:bcbs',
                                plaid_account_id='sav', posted_at=date(2026, 8, 10), amount=36.17,
                                description='Mobile Check Deposit', kind='transfer_in',
                                source='plaid'))
    db.session.commit()

c = cli()
r = c.post('/api/finance/deposits', json={'posted_at': '2026-11-17', 'amount': 36.00,
                                          'description': 'Egg sales', 'income_source_id': 15,
                                          'entity_id': 1})
check('the egg sale is entered by hand', r.status_code == 201, (r.status_code, r.get_json()))
EGGS = r.get_json()['id']
r = c.post('/api/finance/deposits', json={'posted_at': '2026-11-17', 'amount': 5.00,
                                          'description': 'Odd job', 'income_source_id': 16})
OTHER_ENTRY = r.get_json()['id']


def farm_income():
    with A.app.app_context():
        return round(db.session.get(IncomeSource, 15).received_between(date(2026, 1, 1),
                                                                          date(2026, 12, 31)), 2)


def arrivals():
    with A.app.app_context():
        return sorted(a['id'] for a in A._unpaired_arrivals(UID, date(2026, 1, 1),
                                                           date(2026, 12, 31))['arrivals'])


print('\n--- before: counted once, but listed as unexplained money ---')
check('farm income counts the hand entry', farm_income() == 36.00, farm_income())
check('the transfer sits in the arrivals queue', 158 in arrivals(), arrivals())

print('\n--- the editor offers the hand entry to tie to ---')
r = c.get('/api/finance/incomes')
srcs = {s['id']: s for s in (r.get_json() or {}).get('incomes', [])}
logged = srcs.get(15, {}).get('logged_deposits')
check('the farm source lists its hand-entered income',
      logged is not None and [x['id'] for x in logged] == [EGGS], logged)
check('nothing has claimed it yet', logged and logged[0]['settled_by'] == [], logged)

print('\n--- TYING THE TRANSFER TO THE EGG SALE COUNTS IT ONCE ---')
r = c.put('/api/finance/deposits/158', json={'settles_deposit_id': EGGS})
check('the tie is accepted', r.status_code == 200, (r.status_code, r.get_json()))
with A.app.app_context():
    d = db.session.get(PlaidDeposit, 158)
    check('it adopts the egg sale\'s source', d.income_source_id == 15, d.income_source_id)
    check('it is called what it is -- income -- and that is locked',
          d.kind == 'income' and d.kind_locked, (d.kind, d.kind_locked))
check('farm income is STILL $36.00, not $72.00', farm_income() == 36.00, farm_income())
check('and the transfer is off the arrivals queue', 158 not in arrivals(), arrivals())
with A.app.app_context():
    rep = A._entity_report(UID, 1, 2026)
    check('the farm book reports $36.00 of income', rep['income_actual'] == 36.00,
          rep['income_actual'])
    rec = A._income_reconciliation(UID, months=3, today=date(2026, 11, 18))
    check('the income check counts the money once as well',
          rec['counted_deposits'] == 2 and rec['by_kind']['income']['count'] == 3,
          (rec['counted_deposits'], rec['by_kind']))
    rows = [x for x in A._ledger_rows(UID, date(2026, 11, 1), date(2026, 11, 30))
            if x['kind'] == 'deposit' and x['id'] == 158]
    check('the ledger labels it as settling income already logged',
          rows and rows[0]['settles_logged_income'] and rows[0]['settles_deposit_id'] == EGGS,
          rows and rows[0])
r = c.get('/api/finance/incomes')
logged = {s['id']: s for s in r.get_json()['incomes']}[15]['logged_deposits']
check('the editor now shows the egg sale as claimed', logged[0]['settled_by'] == [158], logged)

print('\n--- the tie is refused where it would mean nothing ---')
r = c.put('/api/finance/deposits/159', json={'settles_deposit_id': EGGS})
check('a second bank deposit cannot claim the same egg sale', r.status_code == 400
      and 'already settled' in (r.get_json() or {}).get('error', ''), (r.status_code, r.get_json()))
r = c.put('/api/finance/deposits/159', json={'settles_deposit_id': 158})
check('a bank deposit cannot settle another bank deposit', r.status_code == 400,
      (r.status_code, r.get_json()))
r = c.put('/api/finance/deposits/%d' % OTHER_ENTRY, json={'settles_deposit_id': EGGS})
check('a hand entry cannot settle a hand entry', r.status_code == 400,
      (r.status_code, r.get_json()))
r = c.put('/api/finance/deposits/159', json={'income_source_id': 15,
                                             'settles_deposit_id': OTHER_ENTRY})
check('nor can it settle income from a different source', r.status_code == 400
      and 'different income source' in (r.get_json() or {}).get('error', ''),
      (r.status_code, r.get_json()))
with A.app.app_context():
    d = db.session.get(PlaidDeposit, 159)
    check('and a refused tie changed nothing', d.settles_deposit_id is None and d.kind == 'transfer_in'
          and d.income_source_id is None, (d.settles_deposit_id, d.kind, d.income_source_id))

print('\n--- deleting the hand entry leaves the money counted once, not zero times ---')
r = c.delete('/api/finance/deposits/%d' % EGGS)
check('the hand entry can be deleted', r.status_code == 200, (r.status_code, r.get_json()))
with A.app.app_context():
    check('the transfer is released', db.session.get(PlaidDeposit, 158).settles_deposit_id is None)
check('and now IT is what counts: farm income is still $36.00', farm_income() == 36.00,
      farm_income())

print('\n--- A KIND A PERSON CHOSE SURVIVES THE BANK RE-SENDING THE TRANSACTION ---')
r = c.put('/api/finance/deposits/33', json={'kind': 'refund'})
check('the Blue Cross settlement is named a refund', r.status_code == 200, r.get_json())


class _Item:
    user_id = UID


resent = {'transaction_id': 'bcbs', 'account_id': 'sav', 'amount': -36.17, 'date': '2026-08-10',
          'name': 'Mobile Check Deposit', 'personal_finance_category': {'primary': 'TRANSFER_IN'}}
fresh = {'transaction_id': 'another', 'account_id': 'chk', 'amount': -36.00, 'date': '2026-11-17',
         'name': 'Online Transfer from CHK ...7641', 'personal_finance_category': {'primary': 'INCOME'}}
with A.app.app_context():
    A._record_deposit(_Item(), resent, {'sav': 'depository'})
    A._record_deposit(_Item(), fresh, {'chk': 'depository'})
    db.session.commit()
    check('a re-delivered settlement is still a refund',
          db.session.get(PlaidDeposit, 33).kind == 'refund', db.session.get(PlaidDeposit, 33).kind)
    check('while a deposit nobody named is still re-classified by the bank',
          db.session.get(PlaidDeposit, 159).kind == 'income', db.session.get(PlaidDeposit, 159).kind)
    check('and a tied transfer stays income when re-sent too',
          db.session.get(PlaidDeposit, 158).kind_locked)

print('\n%d check(s) failed' % len(fails) if fails else '\nall checks passed')
sys.exit(1 if fails else 0)
