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

    # ---- the calls this app actually makes -------------------------------------
    def link_token_create(self, user_id, products, redirect_uri=None, webhook=None,
                          access_token=None, consented=None):
        """A link_token is short-lived and client-safe; it is what the browser hands to
        Plaid Link. Passing access_token puts Link into update mode to repair a connection
        that needs re-authentication.

        `consented` becomes additional_consented_products: things the user agrees we may
        ask for later, without the link failing at an institution that does not offer
        them. Plaid rejects a product listed in both, so the overlap is dropped here
        rather than left for the caller to remember.

        Update mode sends neither list. Plaid requires products to be omitted when
        repairing a connection, and adding consent to an item that already exists is its
        own flow -- not something to smuggle into a re-auth.
        """
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
            extra = [p for p in (consented or []) if p not in (products or [])]
            if extra:
                payload['additional_consented_products'] = extra
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


    def liabilities_get(self, access_token, account_ids=None):
        """Issuer-reported terms: APR, minimum payment, next due date, statement balance.

        This is the only Plaid call that knows a rate. /accounts/get returns balances and
        nothing else, which is why _apply_plaid_balance deliberately left APR to the user
        -- it had no better source. Liabilities is a better source: it is the issuer's own
        number rather than an inference, and it carries a date.
        """
        payload = {'access_token': access_token}
        if account_ids:
            payload['options'] = {'account_ids': list(account_ids)}
        return self._post('/liabilities/get', payload)

    def investments_holdings_get(self, access_token, account_ids=None):
        """Positions and prices inside a brokerage or retirement account."""
        payload = {'access_token': access_token}
        if account_ids:
            payload['options'] = {'account_ids': list(account_ids)}
        return self._post('/investments/holdings/get', payload)


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
        # Plaid's detailed values are prefixed with the primary category, e.g.
        # RENT_AND_UTILITIES_GAS_AND_ELECTRICITY. Substring-matching 'RENT' therefore hits
        # the prefix on EVERY value in this group and would file the electric bill as
        # housing — compare the suffix, not the whole string.
        detailed = (pfc.get('detailed') or '').upper()
        suffix = detailed[len('RENT_AND_UTILITIES_'):] if detailed.startswith('RENT_AND_UTILITIES_') else detailed
        return 'housing' if suffix in ('RENT', 'MORTGAGE') else 'utilities'
    return PFC_TO_BUDGET.get(primary)


def is_income(txn):
    """True when Plaid classifies this as money in. Plaid's amount is positive when money
    leaves the account, so a negative amount is a credit — but the category is the more
    reliable signal, and a refund is a credit that is NOT income."""
    primary = ((txn.get('personal_finance_category') or {}).get('primary') or '').upper()
    return primary in SKIP_PFC


# ------------------------------------------------------------- liabilities and holdings
# Plaid error codes meaning "this item was linked without the product you just asked for".
# Distinct from a transient failure: retrying never fixes one, the user has to
# re-authenticate that institution through Link with the product enabled. Worth telling
# apart, because a sync that reports "failed" for a condition only the user can clear
# teaches people to ignore the word.
NEEDS_RELINK_CODES = {
    'PRODUCTS_NOT_SUPPORTED', 'PRODUCT_NOT_ENABLED', 'PRODUCT_NOT_READY',
    'NO_LIABILITY_ACCOUNTS', 'NO_INVESTMENT_ACCOUNTS', 'INVALID_PRODUCT',
}


def apr_for_card(credit):
    """The rate a card is ACTUALLY being charged, out of the list Plaid returns.

    A card does not have one APR. Plaid returns a list -- purchase_apr, cash_apr,
    balance_transfer_apr, and any number of `special` promotional rates -- each with the
    slice of the balance it applies to. Taking the first entry, or always taking
    purchase_apr, is wrong in the case that matters most: a card parked on a 0% balance
    transfer would be recorded at its 24% purchase rate and every payoff plan built on it
    would be fiction, while a card whose promo has just expired would be recorded at 0%.

    So prefer whichever rate the largest part of the balance is actually subject to --
    that is where the money is accruing. Only when nothing reports a balance does it fall
    back to purchase_apr, and then to anything carrying a number.

    Returns (percentage, apr_type), or (None, None) when the issuer gave no rate at all.
    None rather than 0.0: a card with no rate reported is unknown, not interest-free.
    """
    aprs = [a for a in (credit.get('aprs') or []) if a.get('apr_percentage') is not None]
    if not aprs:
        return None, None
    charged = [a for a in aprs if (a.get('balance_subject_to_apr') or 0) > 0]
    if charged:
        best = max(charged, key=lambda a: float(a.get('balance_subject_to_apr') or 0))
        return float(best['apr_percentage']), (best.get('apr_type') or None)
    for a in aprs:
        if (a.get('apr_type') or '') == 'purchase_apr':
            return float(a['apr_percentage']), 'purchase_apr'
    return float(aprs[0]['apr_percentage']), (aprs[0].get('apr_type') or None)


def liability_terms(entry, kind):
    """Normalize one credit / mortgage / student entry into a single shape.

    Plaid names the same idea differently per product -- a mortgage's rate is
    interest_rate.percentage, a student loan's is interest_rate_percentage, a card's is an
    entire list -- and the caller should not have to know which kind it is holding.

    Every value may be absent, and absent stays absent: None is never turned into 0,
    because a zeroed minimum payment or a zeroed rate reads as fact downstream.
    """
    def num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    out = {'account_id': entry.get('account_id'), 'kind': kind, 'apr': None,
           'apr_type': None, 'min_payment': None, 'next_due': None,
           'last_payment_amount': num(entry.get('last_payment_amount')),
           'last_payment_date': entry.get('last_payment_date') or None,
           'last_statement_balance': None, 'maturity_date': None,
           'origination_date': None, 'ytd_interest_paid': None}

    if kind == 'credit':
        out['apr'], out['apr_type'] = apr_for_card(entry)
        out['min_payment'] = num(entry.get('minimum_payment_amount'))
        out['last_statement_balance'] = num(entry.get('last_statement_balance'))
    elif kind == 'mortgage':
        rate = entry.get('interest_rate') or {}
        out['apr'] = num(rate.get('percentage'))
        out['apr_type'] = (rate.get('type') or None)
        # next_monthly_payment is the scheduled payment, which for a mortgage IS the
        # minimum. There is no separate minimum field on this product.
        out['min_payment'] = num(entry.get('next_monthly_payment'))
        out['maturity_date'] = entry.get('maturity_date') or None
        out['origination_date'] = entry.get('origination_date') or None
        out['ytd_interest_paid'] = num(entry.get('ytd_interest_paid'))
    elif kind == 'student':
        out['apr'] = num(entry.get('interest_rate_percentage'))
        out['min_payment'] = num(entry.get('minimum_payment_amount'))
        out['origination_date'] = entry.get('origination_date') or None
        out['ytd_interest_paid'] = num(entry.get('ytd_interest_paid'))
    out['next_due'] = entry.get('next_payment_due_date') or None
    return out


def liability_rows(payload):
    """Every liability in a /liabilities/get response, normalized and flattened."""
    out = []
    liabs = (payload or {}).get('liabilities') or {}
    for kind in ('credit', 'mortgage', 'student'):
        for entry in (liabs.get(kind) or []):
            if entry.get('account_id'):
                out.append(liability_terms(entry, kind))
    return out


def holdings_rows(payload):
    """Positions from /investments/holdings/get, joined to their security.

    Returns (rows, cash_by_account). Cash equivalents are split out rather than returned
    as positions: a money-market sweep is the account's cash, and recording it as a
    holding with a $1.00 price would put a fake ticker in the portfolio and double-count
    it against the account's own cash balance.

    Plaid's `cost_basis` is the TOTAL cost of the holding, not a per-share price, so the
    average cost is derived -- guarded, because a zero quantity would otherwise divide.
    """
    payload = payload or {}
    secs = {s.get('security_id'): s for s in (payload.get('securities') or [])}
    rows, cash = [], {}
    for h in (payload.get('holdings') or []):
        sec = secs.get(h.get('security_id')) or {}
        aid = h.get('account_id')
        qty = float(h.get('quantity') or 0)
        price = h.get('institution_price')
        value = h.get('institution_value')
        if sec.get('is_cash_equivalent'):
            # Value, not quantity: a sweep fund's quantity is shares, and only
            # institution_value is reliably dollars.
            amt = float(value) if value is not None else qty
            cash[aid] = round(cash.get(aid, 0.0) + amt, 2)
            continue
        symbol = (sec.get('ticker_symbol') or '').strip().upper()
        if not symbol or qty == 0:
            # No ticker means an instrument the portfolio cannot key on (a private fund,
            # an option with no symbol). Skipped rather than invented.
            continue
        basis = h.get('cost_basis')
        rows.append({
            'account_id': aid,
            'symbol': symbol,
            'name': (sec.get('name') or '').strip() or None,
            'quantity': qty,
            'price': float(price) if price is not None else None,
            'price_as_of': h.get('institution_price_as_of') or None,
            'value': float(value) if value is not None else None,
            'average_cost': round(float(basis) / qty, 4) if basis and qty else None,
            'security_type': (sec.get('type') or None),
        })
    return rows, cash
