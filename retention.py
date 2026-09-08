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


def _revoke_plaid_items(user_id):
    """Revoke this user's bank connections at Plaid before the local rows are deleted.

    Deleting our stored token only removes our ability to use it — the item keeps existing
    on Plaid's side until /item/remove is called. The retention policy promises the
    credential is destroyed on account deletion, and that is only true if we tell Plaid.

    Best effort by design: a failure here never blocks the purge, because keeping a token
    we can no longer reach would be strictly worse than orphaning one at Plaid. Returns
    (revoked, failed, skipped_reason).
    """
    from models import PlaidItem
    items = PlaidItem.query.filter_by(user_id=user_id).all()
    if not items:
        return 0, 0, None
    try:
        import plaid_client as pc
        client = pc.PlaidClient()
        if not client.available():
            logger.warning('retention: %d Plaid item(s) for user %s deleted WITHOUT '
                           'revocation — Plaid is not configured in this environment',
                           len(items), user_id)
            return 0, 0, 'plaid_not_configured'
    except Exception as e:
        logger.warning('retention: Plaid client unavailable (%s); deleting %d item(s) '
                       'without revocation', e, len(items))
        return 0, 0, 'client_error'

    revoked = failed = 0
    for item in items:
        try:
            client.item_remove(pc.decrypt_token(item.access_token_enc))
            revoked += 1
        except Exception as e:
            failed += 1
            logger.warning('retention: could not revoke Plaid item %s for user %s: %s',
                           item.item_id, user_id, e)
    return revoked, failed, None


def _detach_household(db, user_id):
    """Remove a user from their household without destroying it for everyone else.

    A household outlives any one member. Deleting it because its creator left would strip
    the remaining partner of shared visibility they still rely on, so ownership is handed
    over instead; the household is only removed once nobody is left in it.
    """
    from models import Household, HouseholdMember
    memberships = HouseholdMember.query.filter_by(user_id=user_id).all()
    for m in memberships:
        hid = m.household_id
        db.session.delete(m)
        db.session.flush()
        remaining = HouseholdMember.query.filter(HouseholdMember.household_id == hid,
                                                 HouseholdMember.user_id != user_id).all()
        household = db.session.get(Household, hid)
        if not household:
            continue
        if not remaining:
            db.session.delete(household)
            continue
        if household.created_by == user_id:
            # Prefer an existing owner, else promote the longest-standing member.
            heir = next((r for r in remaining if r.role == 'owner' and r.user_id), None)                 or next((r for r in remaining if r.user_id), None)
            if heir:
                household.created_by = heir.user_id
                heir.role = 'owner'
                logger.info('retention: household %s ownership transferred to user %s',
                            hid, heir.user_id)


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
                        SpendTransaction, RecurringDecision, CreditScore, TaxDocument,
                        AIInsight,
                        PlaidItem, TaxProfile,
                        Household, HouseholdMember, Entity)
    uid = user.id
    _detach_household(db, uid)
    # Revoke at Plaid first: once the rows are gone we no longer hold the tokens needed
    # to do it, so this cannot be deferred to after the delete.
    _revoke_plaid_items(uid)
    user.groups = []

    ordered = (
        SpendTransaction,   # -> finance_accounts, tax_documents
        RecurringDecision,  # -> recurring_bills
        CreditScore,
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
        PlaidItem,          # bank access tokens die with the account, per the retention policy
        TaxProfile,
        Entity,             # after the records that reference entities.id
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
