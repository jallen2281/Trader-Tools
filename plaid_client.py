"""Thin Plaid REST client + at-rest encryption for access tokens.

Deliberately not the plaid-python SDK. The five endpoints we need map 1:1 onto Plaid's
REST docs, so a direct client reads the same as the documentation the reader is holding,
adds no dependency to the image, and avoids the SDK's generated request objects.

A Plaid access_token is a long-lived bearer credential for someone's bank account. It is
never stored in the clear: PlaidItem holds ciphertext, and the key lives only in the
environment. Losing the DB therefore does not hand over anyone's bank connection.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

PLAID_HOSTS = {
    'sandbox': 'https://sandbox.plaid.com',
    'production': 'https://production.plaid.com',
}

# Plaid's personal_finance_category.primary -> this app's BUDGET_CATEGORIES.
# INCOME and TRANSFER_IN are intentionally absent: money coming in belongs to the income
# module, exactly as the CSV importer skips deposits by default.
PFC_TO_BUDGET = {
    'FOOD_AND_DRINK': 'food',
    'RENT_AND_UTILITIES': 'utilities',        # refined to 'housing' for rent/mortgage below
    'HOME_IMPROVEMENT': 'housing',
    'TRANSPORTATION': 'transportation',
    'TRAVEL': 'transportation',
    'LOAN_PAYMENTS': 'debt',
    'MEDICAL': 'healthcare',
    'ENTERTAINMENT': 'entertainment',
    'PERSONAL_CARE': 'personal',
    'GENERAL_MERCHANDISE': 'personal',
    'GENERAL_SERVICES': 'other',
    'GOVERNMENT_AND_NON_PROFIT': 'taxes',
    'BANK_FEES': 'other',
    'TRANSFER_OUT': 'other',
}

SKIP_PFC = {'INCOME', 'TRANSFER_IN'}


class PlaidError(RuntimeError):
    """A Plaid API error. `code` is Plaid's error_code, useful for branching on
    ITEM_LOGIN_REQUIRED (the user must re-authenticate) versus everything else."""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


# --------------------------------------------------------------------------- encryption
def _fernet():
    """Fernet built from PLAID_ENCRYPTION_KEY.

    A dedicated key rather than a value derived from SECRET_KEY: rotating the session key
    would otherwise silently orphan every stored bank connection, and the two secrets
    should not share a blast radius.
    """
    from cryptography.fernet import Fernet
    key = os.getenv('PLAID_ENCRYPTION_KEY', '')
    if not key:
        raise PlaidError(
            'PLAID_ENCRYPTION_KEY is not set. Bank access tokens are only ever stored '
            'encrypted, so connecting an institution is refused without it. Generate one '
            'with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"')
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw):
    return _fernet().encrypt(raw.encode('utf-8'))


def decrypt_token(blob):
    return _fernet().decrypt(bytes(blob)).decode('utf-8')


def encryption_ready():
    """Whether tokens can be encrypted, without raising — for status endpoints."""
    try:
        _fernet()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------------------- client
class PlaidClient:
    def __init__(self, client_id=None, secret=None, env=None, timeout=30):
        self.client_id = client_id or os.getenv('PLAID_CLIENT_ID', '')
        self.secret = secret or os.getenv('PLAID_SECRET', '')
        self.env = (env or os.getenv('PLAID_ENV', 'sandbox')).lower()
        self.timeout = timeout

    def available(self):
        return bool(self.client_id and self.secret and self.env in PLAID_HOSTS)

    @property
    def host(self):
        return PLAID_HOSTS.get(self.env, PLAID_HOSTS['sandbox'])

    def _post(self, path, payload):
        if not self.available():
            raise PlaidError('Plaid is not configured (PLAID_CLIENT_ID / PLAID_SECRET / '
                             'PLAID_ENV).')
        body = dict(payload)
        body['client_id'] = self.client_id
        body['secret'] = self.secret
        try:
            r = requests.post(self.host + path, json=body, timeout=self.timeout,
                              headers={'Content-Type': 'application/json'})
        except requests.RequestException as e:
            raise PlaidError('Could not reach Plaid: %s' % e)
        try:
            data = r.json()
        except ValueError:
            raise PlaidError('Plaid returned a non-JSON response (HTTP %s)' % r.status_code,
                             status=r.status_code)
        if r.status_code >= 400:
            # Never log `body` — it carries the secret and the access_token.
            msg = data.get('error_message') or data.get('error_code') or 'Plaid request failed'
            logger.warning('Plaid %s failed: %s (%s)', path, data.get('error_code'), r.status_code)
            raise PlaidError(msg, code=data.get('error_code'), status=r.status_code)
        return data

    # ---- the five calls this app actually makes -------------------------------------
    def link_token_create(self, user_id, products, redirect_uri=None, webhook=None,
                          access_token=None):
        """A link_token is short-lived and client-safe; it is what the browser hands to
        Plaid Link. Passing access_token puts Link into update mode to repair a connection
        that needs re-authentication."""
        payload = {
            'user': {'client_user_id': str(user_id)},
            'client_name': 'Trader Tools',
            'language': 'en',
            'country_codes': ['US'],
        }
        if access_token:
            payload['access_token'] = access_token     # update mode: products must be omitted
        else:
            payload['products'] = list(products)
        if redirect_uri:
            payload['redirect_uri'] = redirect_uri
        if webhook:
            payload['webhook'] = webhook
        return self._post('/link/token/create', payload)

    def exchange_public_token(self, public_token):
        return self._post('/item/public_token/exchange', {'public_token': public_token})

    def item_get(self, access_token):
        return self._post('/item/get', {'access_token': access_token})

    def institution_get(self, institution_id):
        return self._post('/institutions/get_by_id', {
            'institution_id': institution_id, 'country_codes': ['US'],
        })

    def accounts_get(self, access_token):
        return self._post('/accounts/get', {'access_token': access_token})

    def transactions_sync(self, access_token, cursor=None, count=500):
        payload = {'access_token': access_token, 'count': count}
        if cursor:
            payload['cursor'] = cursor
        return self._post('/transactions/sync', payload)

    def item_remove(self, access_token):
        """Invalidates the access_token at Plaid. Called on disconnect so the credential is
        dead on their side too, not merely deleted on ours."""
        return self._post('/item/remove', {'access_token': access_token})


# ------------------------------------------------------------------------ normalization
def category_for(txn):
    """Map a Plaid transaction onto a budget category, or None to skip it.

    Plaid's own personal_finance_category is better than keyword matching on the merchant
    name, so it wins when present; the caller falls back to _guess_spend_category otherwise.
    """
    pfc = (txn.get('personal_finance_category') or {})
    primary = (pfc.get('primary') or '').upper()
    if primary in SKIP_PFC:
        return None
    if primary == 'RENT_AND_UTILITIES':
        detailed = (pfc.get('detailed') or '').upper()
        return 'housing' if ('RENT' in detailed or 'MORTGAGE' in detailed) else 'utilities'
    return PFC_TO_BUDGET.get(primary)


def is_income(txn):
    """True when Plaid classifies this as money in. Plaid's amount is positive when money
    leaves the account, so a negative amount is a credit — but the category is the more
    reliable signal, and a refund is a credit that is NOT income."""
    primary = ((txn.get('personal_finance_category') or {}).get('primary') or '').upper()
    return primary in SKIP_PFC
