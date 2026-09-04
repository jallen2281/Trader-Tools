"""Data retention enforcement — see DATA_RETENTION_POLICY.txt.

The policy defines retention periods; this module is what actually enforces them. It runs
as a scheduled job (k8s/retention-cronjob.yaml) and is deliberately importable without
pulling in app.py, so the cron pod does not spin up the monitoring service, analyzers, or
any of the other startup machinery just to delete some rows.

`purge_user_record` is shared with the admin purge endpoint in app.py rather than
duplicated — a second copy of the cascade would drift the moment a model is added.
"""
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Retention windows, in days. These mirror Section 3 of DATA_RETENTION_POLICY.txt — if you
# change one here, change it there too, and note it in the policy's revision history.
ACCOUNT_PURGE_AFTER_DAYS = int(os.getenv('RETENTION_ACCOUNT_DAYS', '30'))
SESSION_PURGE_AFTER_DAYS = int(os.getenv('RETENTION_SESSION_DAYS', '7'))
AI_CACHE_PURGE_AFTER_DAYS = int(os.getenv('RETENTION_AI_CACHE_DAYS', '30'))


def purge_user_record(db, user):
    """Permanently delete a user and every row they own. Irreversible.

    User's relationships carry delete-orphan cascades for only ten models (watchlist,
    alerts, portfolio, portfolio_accounts, transactions, options_positions,
    analysis_history, sessions, portfolio_snapshots, dividends). Everything else that
    references users.id has to be deleted explicitly here — including the entire finances
    and tax surface, which is not cascaded at all. Omitting one does not silently orphan
    it: the users row has a foreign key pointing at it, so Postgres rejects the delete and
    the whole purge fails.

    Ordering matters. Rows that reference OTHER user-owned rows are deleted first, or their
    own foreign keys block the parent's deletion.

    Errors are not swallowed. This function backs a published deletion promise, so a purge
    that quietly skipped a table would be worse than one that fails loudly — the caller
    rolls back and the failure surfaces. Does NOT commit; the caller owns the transaction.
    """
    from models import (PaperTrade, TradingSOP, Notification, ThreadVote, ThreadReply,
                        DiscussionThread, CopyTradingFollow, FinanceAccount, Debt,
                        IncomeSource, IncomeEvent, RecurringBill, BudgetCategory,
                        SpendTransaction, TaxDocument, AIInsight)
    uid = user.id
    user.groups = []

    ordered = (
        SpendTransaction,   # -> finance_accounts, tax_documents
        RecurringBill,      # -> debts, finance_accounts
        IncomeEvent,        # -> income_sources
        ThreadVote,         # -> discussion_threads / thread_replies
        ThreadReply,        # -> discussion_threads
        DiscussionThread,
        BudgetCategory,
        TaxDocument,
        IncomeSource,
        Debt,
        FinanceAccount,
        AIInsight,
        PaperTrade,
        TradingSOP,
        Notification,
    )
    for model in ordered:
        model.query.filter(model.user_id == uid).delete(synchronize_session=False)

    CopyTradingFollow.query.filter(
        (CopyTradingFollow.follower_id == uid) | (CopyTradingFollow.leader_id == uid)
    ).delete(synchronize_session=False)

    db.session.delete(user)
    return uid


def purge_expired_accounts(db, now=None, dry_run=False):
    """Hard-purge accounts soft-deleted longer ago than the grace period.

    The grace period is what makes soft-delete reversible: within it, signing back in
    restores the account. Past it, the record is destroyed.
    """
    from models import User
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=ACCOUNT_PURGE_AFTER_DAYS)
    rows = User.query.filter(User.deleted_at.isnot(None), User.deleted_at < cutoff).all()
    purged = []
    for user in rows:
        if dry_run:
            purged.append(user.id)
            continue
        try:
            purged.append(purge_user_record(db, user))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("retention: failed to purge user %s: %s", user.id, e, exc_info=True)
    return purged


def purge_expired_sessions(db, now=None, dry_run=False):
    """Delete session rows that expired longer ago than the grace period. Expired sessions
    already fail authentication; this stops them accumulating in storage forever."""
    from models import UserSession
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=SESSION_PURGE_AFTER_DAYS)
    q = UserSession.query.filter(UserSession.expires_at.isnot(None),
                                 UserSession.expires_at < cutoff)
    if dry_run:
        return q.count()
    n = q.delete(synchronize_session=False)
    db.session.commit()
    return n


def purge_expired_ai_cache(db, now=None, dry_run=False):
    """Delete cached AI reads past their TTL plus the grace period. These hold summarized
    financial figures, so they are covered by the retention policy like any other data."""
    from models import AIInsight
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=AI_CACHE_PURGE_AFTER_DAYS)
    q = AIInsight.query.filter(AIInsight.expires_at.isnot(None), AIInsight.expires_at < cutoff)
    if dry_run:
        return q.count()
    n = q.delete(synchronize_session=False)
    db.session.commit()
    return n


def run_retention(db, now=None, dry_run=False):
    """Run every retention control and return what was (or would be) removed."""
    now = now or datetime.utcnow()
    accounts = purge_expired_accounts(db, now=now, dry_run=dry_run)
    sessions = purge_expired_sessions(db, now=now, dry_run=dry_run)
    ai_cache = purge_expired_ai_cache(db, now=now, dry_run=dry_run)
    return {
        'ran_at': now.isoformat(),
        'dry_run': bool(dry_run),
        'accounts_purged': len(accounts),
        'accounts_purged_ids': accounts,
        'sessions_purged': sessions,
        'ai_cache_purged': ai_cache,
        'windows': {
            'account_days': ACCOUNT_PURGE_AFTER_DAYS,
            'session_days': SESSION_PURGE_AFTER_DAYS,
            'ai_cache_days': AI_CACHE_PURGE_AFTER_DAYS,
        },
    }


def main():
    """CLI entry point for the scheduled job.

    Builds a minimal Flask app around the shared models rather than importing app.py, so
    the cron pod starts nothing but a database connection. Exits non-zero on failure so a
    silently broken retention job shows up as a failed CronJob rather than looking healthy.
    """
    import json
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    url = os.getenv('DATABASE_URL') or os.getenv('SQLALCHEMY_DATABASE_URI')
    if not url:
        logger.error('DATABASE_URL is not set')
        return 1
    if url.startswith('postgres://'):        # SQLAlchemy 2.x rejects the legacy scheme
        url = url.replace('postgres://', 'postgresql://', 1)

    from flask import Flask
    from models import db

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    dry_run = os.getenv('RETENTION_DRY_RUN', '').lower() in ('1', 'true', 'yes')
    with app.app_context():
        try:
            result = run_retention(db, dry_run=dry_run)
        except Exception as e:
            logger.error('retention run failed: %s', e, exc_info=True)
            return 1
    logger.info('retention complete: %s', json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
