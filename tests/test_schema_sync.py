"""Schema drift: does a deploy bring an existing database up to date with the models?

This is the test that was missing. Every other suite calls create_all() on an empty
database, which creates every column by definition — so the upgrade path that actually runs
on a deploy was never exercised, and tax_profiles shipped to production missing six columns.

Here the schema is deliberately rolled BACK (columns dropped from tables that already
exist), init_database is run as a deploying pod would, and the live schema is then compared
against the model metadata column by column.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='drift_')
DBURL = 'sqlite:///' + os.path.join(TMP, 'drift.db').replace(os.sep, '/')
os.environ['DATABASE_URL'] = DBURL
os.environ['SQLALCHEMY_DATABASE_URI'] = DBURL
sys.path.insert(0, os.getcwd())

from flask import Flask                       # noqa: E402
from sqlalchemy import text, inspect          # noqa: E402
from models import db                         # noqa: E402

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


# Columns added by recent releases to tables that already existed in production.
# tax_profiles is the one that actually broke; the others guard the same class.
TO_DROP = {
    'tax_profiles': ['pretax_retirement_mode', 'pretax_retirement_pct',
                     'roth_retirement_annual', 'roth_retirement_pct',
                     'employer_match_rate_pct', 'employer_match_limit_pct'],
    'finance_accounts': ['share_level'],
    'spend_transactions': ['share_level'],
    'recurring_bills': ['share_level'],
    'users': ['privacy_consent_at', 'privacy_consent_version'],
}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DBURL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

dropped = {}
with app.app_context():
    db.create_all()
    for table, cols in TO_DROP.items():
        for c in cols:
            try:
                db.session.execute(text('ALTER TABLE %s DROP COLUMN %s' % (table, c)))
                db.session.commit()
                dropped.setdefault(table, []).append(c)
            except Exception:
                db.session.rollback()
    print('Rolled back %d column(s) across %d table(s) to simulate an old schema.'
          % (sum(len(v) for v in dropped.values()), len(dropped)))
    for t, cols in dropped.items():
        print('   %-20s dropped %s' % (t, ', '.join(cols)))

check('the rollback actually removed columns (test would be vacuous otherwise)',
      sum(len(v) for v in dropped.values()) >= 6, dropped)

with app.app_context():
    insp = inspect(db.engine)
    for t, cols in dropped.items():
        live = {c['name'] for c in insp.get_columns(t)}
        check('%s is genuinely missing %d column(s) before the upgrade' % (t, len(cols)),
              not (set(cols) & live), sorted(set(cols) & live))

print('\n--- running init_database, as a deploying pod would ---')
from db_config import init_database            # noqa: E402

app2 = Flask(__name__)
app2.config['SQLALCHEMY_DATABASE_URI'] = DBURL
app2.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
raised = None
try:
    init_database(app2)
except Exception as e:      # noqa: BLE001
    raised = e
check('init_database did not raise', raised is None, raised)

print('\n--- every dropped column is back ---')
with app2.app_context():
    insp = inspect(db.engine)
    for t, cols in dropped.items():
        live = {c['name'] for c in insp.get_columns(t)}
        missing = [c for c in cols if c not in live]
        check('%s restored %s' % (t, ', '.join(cols)), not missing, 'still missing %s' % missing)

print('\n--- the whole schema now matches the models (no drift anywhere) ---')
with app2.app_context():
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    drift = []
    for name, table in db.metadata.tables.items():
        if name not in tables:
            drift.append('%s: TABLE MISSING' % name)
            continue
        live = {c['name'] for c in insp.get_columns(name)}
        for col in table.columns:
            if col.name not in live:
                drift.append('%s.%s' % (name, col.name))
    check('no model column is missing from the database', not drift, drift[:12])

print('\n--- and the app can actually query the repaired table ---')
with app2.app_context():
    from models import TaxProfile, User
    try:
        db.session.add(User(id=1, google_id='g', email='e@x.com', name='n'))
        db.session.flush()
        db.session.add(TaxProfile(user_id=1, filing_status='mfj',
                                  pretax_retirement_mode='percent',
                                  pretax_retirement_pct=3, roth_retirement_pct=3))
        db.session.commit()
        p = TaxProfile.query.filter_by(user_id=1).first()
        ok = p is not None and p.pretax_retirement_mode == 'percent'
        err = None
    except Exception as e:      # noqa: BLE001
        ok, err = False, e
    check('TaxProfile round-trips the previously-missing columns', ok, err)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL SCHEMA DRIFT CHECKS PASSED')
