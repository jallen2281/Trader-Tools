"""Retention enforcement tests.

Foreign key enforcement is switched ON in SQLite (it is off by default). Without it this
suite would be near-worthless: a model missing from purge_user_record's delete list would
leave orphans silently instead of failing, exactly the bug the list exists to prevent.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

TMP = tempfile.mkdtemp(prefix='ret_')
DBURL = 'sqlite:///' + os.path.join(TMP, 'r.db').replace('\\', '/')
os.environ['DATABASE_URL'] = DBURL
sys.path.insert(0, os.getcwd())

from flask import Flask                                      # noqa: E402
from sqlalchemy import event                                 # noqa: E402
from sqlalchemy.engine import Engine                         # noqa: E402


@event.listens_for(Engine, 'connect')
def _fk_on(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute('PRAGMA foreign_keys=ON')
    cur.close()


from models import (db, User, FinanceAccount, Debt, IncomeSource, IncomeEvent,   # noqa: E402
                    RecurringBill, BudgetCategory, SpendTransaction, TaxDocument,
                    AIInsight, UserSession, Watchlist, Notification, PlaidItem)
import retention as R                                        # noqa: E402
import plaid_client as pc                                    # noqa: E402
from cryptography.fernet import Fernet                       # noqa: E402

os.environ['PLAID_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['PLAID_CLIENT_ID'] = 'test-client'
os.environ['PLAID_SECRET'] = 'test-secret'

REVOKED = []


class _FakePlaid:
    """Records revocations instead of calling Plaid."""
    def available(self):
        return True

    def item_remove(self, token):
        REVOKED.append(token)
        return {'removed': True}


pc.PlaidClient = lambda *a, **kw: _FakePlaid()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DBURL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

fails = []
NOW = datetime(2026, 9, 3, 12, 0, 0)


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def seed_user_data(uid, tag):
    """Give a user one row in every table that references users.id."""
    acct = FinanceAccount(user_id=uid, name=tag + '-checking', type='checking', balance=100)
    debt = Debt(user_id=uid, name=tag + '-card', type='credit_card', apr=20, balance=500)
    src = IncomeSource(user_id=uid, name=tag + '-job')
    doc = TaxDocument(user_id=uid, doc_type='receipt', merchant=tag + '-store', amount=50,
                      filename=tag + '.pdf')
    db.session.add_all([acct, debt, src, doc])
    db.session.flush()
    db.session.add_all([
        IncomeEvent(income_source_id=src.id, user_id=uid, date=NOW.date(), gross_amount=1000),
        RecurringBill(user_id=uid, name=tag + '-rent', amount=900, linked_debt_id=debt.id,
                      from_account_id=acct.id),
        BudgetCategory(user_id=uid, category='food', monthly_limit=500),
        SpendTransaction(user_id=uid, posted_at=NOW.date(), description=tag + '-buy',
                         amount=25, account_id=acct.id, tax_document_id=doc.id),
        AIInsight(user_id=uid, kind='finance', input_hash=tag + 'h', content='x',
                  expires_at=NOW + timedelta(days=10)),
        Watchlist(user_id=uid, symbol='AAPL'),
        PlaidItem(user_id=uid, item_id=tag + '-item',
                  access_token_enc=pc.encrypt_token('access-token-' + tag),
                  institution_name=tag + ' Bank'),
        Notification(user_id=uid, title=tag, message='m'),
    ])


with app.app_context():
    db.drop_all()
    db.create_all()

    fk = db.session.execute(db.text('PRAGMA foreign_keys')).scalar()
    check('SQLite foreign key enforcement is ON (test would be vacuous otherwise)', fk == 1, fk)

    db.session.add_all([
        User(id=1, google_id='g1', email='a@x.com', name='Active'),
        User(id=2, google_id='g2', email='b@x.com', name='Old Deleted',
             deleted_at=NOW - timedelta(days=40)),
        User(id=3, google_id='g3', email='c@x.com', name='Recent Deleted',
             deleted_at=NOW - timedelta(days=5)),
    ])
    db.session.flush()
    for uid, tag in ((1, 'u1'), (2, 'u2'), (3, 'u3')):
        seed_user_data(uid, tag)

    # Sessions: one long-expired (purge), one just-expired (keep), one live (keep).
    db.session.add_all([
        UserSession(user_id=1, session_token='old', expires_at=NOW - timedelta(days=10)),
        UserSession(user_id=1, session_token='recent', expires_at=NOW - timedelta(days=2)),
        UserSession(user_id=1, session_token='live', expires_at=NOW + timedelta(days=5)),
    ])
    # AI cache: one long-expired (purge), one recently expired (keep).
    db.session.add_all([
        AIInsight(user_id=1, kind='tax', input_hash='old', content='x',
                  expires_at=NOW - timedelta(days=40)),
        AIInsight(user_id=1, kind='tax', input_hash='recent', content='x',
                  expires_at=NOW - timedelta(days=5)),
    ])
    db.session.commit()

    print('\n--- dry run changes nothing ---')
    before_users = User.query.count()
    res = R.run_retention(db, now=NOW, dry_run=True)
    check('dry run reports the one expired account', res['accounts_purged'] == 1, res)
    check('dry run reports the long-expired session', res['sessions_purged'] == 1, res)
    check('dry run reports the long-expired AI entry', res['ai_cache_purged'] == 1, res)
    check('dry run deleted no users', User.query.count() == before_users)
    check('dry run deleted no sessions', UserSession.query.count() == 3)
    check('dry run flagged as dry_run', res['dry_run'] is True)

    print('\n--- real run ---')
    res = R.run_retention(db, now=NOW, dry_run=False)
    check('purged exactly one account', res['accounts_purged'] == 1, res)
    check('purged the right account (user 2)', res['accounts_purged_ids'] == [2], res)
    check('reports its configured windows', res['windows']['account_days'] == 30, res['windows'])

    print('\n--- purged user is fully gone (all 16 referencing tables) ---')
    check('user row deleted', db.session.get(User, 2) is None)
    for model, name in ((FinanceAccount, 'FinanceAccount'), (Debt, 'Debt'),
                        (IncomeSource, 'IncomeSource'), (IncomeEvent, 'IncomeEvent'),
                        (RecurringBill, 'RecurringBill'), (BudgetCategory, 'BudgetCategory'),
                        (SpendTransaction, 'SpendTransaction'), (TaxDocument, 'TaxDocument'),
                        (AIInsight, 'AIInsight'), (Watchlist, 'Watchlist'),
                        (PlaidItem, 'PlaidItem'),
                        (Notification, 'Notification')):
        n = model.query.filter(model.user_id == 2).count()
        check('%s rows removed' % name, n == 0, '%d left' % n)

    check('purge revoked the bank connection at Plaid, not just locally',
          'access-token-u2' in REVOKED, REVOKED)
    check('and left other users tokens alone',
          not any(t.endswith('u1') or t.endswith('u3') for t in REVOKED), REVOKED)

    print('\n--- everyone else is untouched ---')
    check('active user survives', db.session.get(User, 1) is not None)
    check('within-grace deleted user survives (still restorable)', db.session.get(User, 3) is not None)
    check('user 3 tax documents intact', TaxDocument.query.filter_by(user_id=3).count() == 1)
    check('user 1 finance data intact', FinanceAccount.query.filter_by(user_id=1).count() == 1)
    check('user 1 spend transactions intact', SpendTransaction.query.filter_by(user_id=1).count() == 1)

    print('\n--- session and cache expiry ---')
    tokens = {s.session_token for s in UserSession.query.all()}
    check('long-expired session purged', 'old' not in tokens, tokens)
    check('recently-expired session kept (inside grace)', 'recent' in tokens, tokens)
    check('live session kept', 'live' in tokens, tokens)
    hashes = {a.input_hash for a in AIInsight.query.filter_by(user_id=1).all()}
    check('long-expired AI cache purged', 'old' not in hashes, hashes)
    check('recently-expired AI cache kept (inside grace)', 'recent' in hashes, hashes)

    print('\n--- grace period boundary ---')
    later = NOW + timedelta(days=26)   # user 3 deleted 5d before NOW -> 31d before `later`
    res = R.run_retention(db, now=later, dry_run=False)
    check('user 3 purged once past 30 days', db.session.get(User, 3) is None, res)
    check('user 3 tax documents gone with them', TaxDocument.query.filter_by(user_id=3).count() == 0)
    check('active user still survives', db.session.get(User, 1) is not None)

    print('\n--- idempotent ---')
    res = R.run_retention(db, now=later, dry_run=False)
    check('second run purges nothing', res['accounts_purged'] == 0 and res['sessions_purged'] == 0, res)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL RETENTION CHECKS PASSED')
