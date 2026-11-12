"""Scheduled Plaid sync — keeps the ledger from going stale on its own.

Why this exists. /api/plaid/sync was reachable from exactly one place: a button on the
finances page. Nothing else called it, no job ran it, so the books were only as fresh as
the last time someone happened to click. On 2026-11-09 the feed was 12 days behind, and
the cost was not the missing rows -- it was that four bills read PAST DUE and only one of
them genuinely was. The mortgage and the Costco Visa had been paid on autopay and the
electric bill had been paid on 2026-11-03; the ledger simply could not say so. A warning
you learn to ignore is worse than no warning, and staleness is what teaches you to ignore
it.

The hard part is failure, not success. A sync that stops working quietly leaves exactly
the stale ledger this job exists to prevent, while looking healthy -- so the two kinds of
failure are handled differently and deliberately:

  * ITEM_LOGIN_REQUIRED is not a retryable error. The bank has revoked consent and no
    number of retries will fix it; a human has to re-authenticate through Link in update
    mode. Retrying it forever would turn the Job red permanently, which trains you to
    ignore a red Job. So it is recorded on the item, announced ONCE as a notification in
    the app where it will actually be seen, and the run still exits 0.

  * anything else -- network, 5xx, a bug here -- IS retryable, so it exits non-zero and
    lets the Job's backoffLimit and failedJobsHistoryLimit do their work.

The notification is created only when an item's status CHANGES into login_required, not on
every run. A job that re-announces the same dead connection every thirty minutes is its own
kind of silence.
"""
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Plaid's own code for "the user must re-authenticate". Not a failure to retry.
REAUTH_CODE = 'ITEM_LOGIN_REQUIRED'


def _announce_reauth(db, item):
    """Put a dead bank connection in front of the user, once.

    Returns True if a notification was created. The guard is the item's PREVIOUS status:
    an item that was already login_required has already been announced, and saying it again
    every half hour is how a real signal becomes noise.
    """
    from models import Notification
    name = item.institution_name or 'A bank connection'
    db.session.add(Notification(
        user_id=item.user_id,
        category='system',
        title='%s needs to be reconnected' % name,
        message=('%s has stopped sharing transactions and is asking you to sign in again. '
                 'Until you reconnect it, spending and balances from this institution will '
                 'stop updating and anything that depends on them -- bill due dates, '
                 'past-due flags, category totals -- will quietly go stale. Reconnect it '
                 'from the Finances page.' % name),
        priority='high'))
    return True


def run_sync(db, user_id=None):
    """Sync every connected item, for one user or all of them.

    Returns a dict of what happened. Never raises for a single institution's sake: one
    bank being down must not stop the other five from updating, which is the same reason
    /api/plaid/sync catches per item.
    """
    import plaid_client as pc
    from models import PlaidItem
    from app import _plaid_sync_item

    q = PlaidItem.query
    if user_id:
        q = q.filter_by(user_id=user_id)
    items = q.all()

    out = {'items': len(items), 'added': 0, 'updated': 0, 'removed': 0,
           'skipped_income': 0, 'synced': 0, 'reauth': [], 'failed': [], 'announced': 0,
           # Paid products. `relink` is NOT a failure: the product is enabled in config
           # but the institution was connected before it was, so only the user can clear
           # it by re-authenticating through Link.
           'liabilities': 0, 'holdings': 0, 'holdings_cash': 0, 'relink': [],
           'unreported': []}

    for item in items:
        name = item.institution_name or 'item:%s' % item.id
        was = item.status
        try:
            r = _plaid_sync_item(item)
            for k in ('added', 'updated', 'removed', 'skipped_income',
                      'liabilities', 'holdings', 'holdings_cash'):
                out[k] += r.get(k, 0) or 0
            for rl in (r.get('relink') or []):
                out['relink'].append(dict(rl, institution=name))
            for sym in (r.get('unreported') or []):
                out['unreported'].append({'institution': name, 'symbol': sym})
            for ee in (r.get('extra_errors') or []):
                out['failed'].append(dict(ee, institution=name))
            out['synced'] += 1
            # A sync that worked clears a stale error state, or the item would keep
            # claiming it needs attention after the user has already fixed it.
            if item.status != 'active':
                item.status = 'active'
                item.last_error = None
            db.session.commit()
            logger.info('plaid-sync: %s ok added=%s updated=%s removed=%s '
                        'skipped_income=%s liabilities=%s holdings=%s',
                        name, r.get('added'), r.get('updated'), r.get('removed'),
                        r.get('skipped_income'), r.get('liabilities'), r.get('holdings'))
        except pc.PlaidError as e:
            db.session.rollback()
            item.status = 'login_required' if e.code == REAUTH_CODE else 'error'
            item.last_error = str(e)[:255]
            if e.code == REAUTH_CODE:
                out['reauth'].append(name)
                if was != 'login_required':
                    out['announced'] += int(_announce_reauth(db, item))
                logger.warning('plaid-sync: %s needs re-authentication (announced=%s)',
                               name, was != 'login_required')
            else:
                out['failed'].append({'institution': name, 'code': e.code, 'error': str(e)})
                logger.error('plaid-sync: %s failed code=%s: %s', name, e.code, e)
            db.session.commit()
        except Exception as e:                      # noqa: BLE001 -- see module docstring
            db.session.rollback()
            out['failed'].append({'institution': name, 'error': '%s: %s' % (type(e).__name__, e)})
            logger.error('plaid-sync: %s failed unexpectedly', name, exc_info=True)

    return out


def main():
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s %(levelname)s %(name)s %(message)s')

    url = os.getenv('DATABASE_URL') or os.getenv('SQLALCHEMY_DATABASE_URI')
    if not url:
        logger.error('plaid-sync: no DATABASE_URL; refusing to run')
        return 1

    # Importing app.py is what gives us _plaid_sync_item, and with it the single definition
    # of how a transaction becomes a row -- the category precedence, the card-payment and
    # transfer rules, the credit routing, the transfer pairing. A second copy of any of
    # that here would drift, and the drift would be invisible until a figure was wrong.
    # TT_BACKGROUND_JOBS=0 keeps the import from also starting the alert monitor; the
    # CronJob sets it, and this is a belt-and-braces default for a hand-run.
    os.environ.setdefault('TT_BACKGROUND_JOBS', '0')

    from app import app, db

    only = os.getenv('PLAID_SYNC_USER_ID')
    with app.app_context():
        try:
            result = run_sync(db, user_id=int(only) if only else None)
        except Exception as e:
            logger.error('plaid-sync: run failed: %s', e, exc_info=True)
            return 1

    logger.info('plaid-sync complete: %s', json.dumps(result))

    if result['failed']:
        # Retryable. Let the Job go red so backoffLimit retries and the failure is visible
        # in `kubectl get jobs` for as long as failedJobsHistoryLimit keeps it.
        logger.error('plaid-sync: %d institution(s) failed and may succeed on retry',
                     len(result['failed']))
        return 1
    if result['reauth']:
        # NOT retryable, and deliberately exit 0 -- see the module docstring. The signal
        # lives on the item and in the user's notifications, not in a Job that would be red
        # forever until someone clicks a button in a browser.
        logger.warning('plaid-sync: %d institution(s) need re-authentication: %s',
                       len(result['reauth']), ', '.join(result['reauth']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
