"""Detect recurring charges in the spending ledger.

RecurringBill records what a person DECLARED. This finds what is actually repeating in
their transactions, which is a different and more interesting question: the forgotten trial,
the streaming service that quietly raised its price, the annual renewal nobody remembers
until it lands, and the subscription that stopped because a card expired.

Deliberately deterministic — no model call. Interval arithmetic is exact, runs on every page
load for nothing, and produces an explanation a person can check ("charged on the 3rd for
seven months, always $15.99"). A language model asked the same question would be slower,
cost money, and occasionally invent a subscription.

Pure functions over plain dicts, so the whole thing is testable without a database.
"""
import re
from collections import defaultdict
from datetime import date, timedelta

# Payment processors prepend their own marker; the merchant is what follows.
_PROCESSOR_PREFIX = re.compile(
    r'^(SQ|TST|SP|PP|PAYPAL|SUMUP|IC|EB|WL|CKE)\s*\*+\s*', re.I)
# Trailing "#442", store/terminal numbers, long digit runs, and reference codes.
_STORE_NUMBER = re.compile(r'#\s*\d+')
_MIXED_ALNUM = re.compile(r'^(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+$')
_PHONE = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
_US_STATE_TAIL = re.compile(
    r'\s+(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|'
    r'NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)$')
_PUNCT = re.compile(r'[^A-Z0-9 ]+')
_WS = re.compile(r'\s+')

# Cadence -> (nominal days, tolerance). Monthly is wide because month lengths differ and
# billing slides across weekends.
CADENCES = [
    ('weekly', 7, 2),
    ('biweekly', 14, 3),
    ('monthly', 30, 5),
    ('quarterly', 91, 10),
    ('semiannual', 182, 16),
    ('annual', 365, 21),
]

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.15      # a charge may drift this much and still be "the same" charge
PRICE_INCREASE_THRESHOLD = 0.10


def merchant_key(text):
    """Collapse a bank description to a stable merchant identity.

    Bank descriptors carry store numbers, terminal ids, phone numbers and city/state that
    change between charges from the SAME merchant. Without stripping them, every month looks
    like a different vendor and nothing is ever detected as recurring.
    """
    if not text:
        return ''
    s = str(text).upper().strip()
    s = _PROCESSOR_PREFIX.sub('', s)
    s = _PHONE.sub(' ', s)
    s = _STORE_NUMBER.sub(' ', s)
    s = _PUNCT.sub(' ', s)
    s = _WS.sub(' ', s).strip()
    s = _US_STATE_TAIL.sub('', s)
    # Drop reference codes and store numbers. A token mixing letters and digits is a
    # terminal or reference id; a bare number is a store number UNLESS it leads the name,
    # where it is part of the brand ("7 ELEVEN", "76 GAS").
    tokens = []
    for i, tok in enumerate(s.split()):
        if _MIXED_ALNUM.match(tok):
            continue
        if tok.isdigit() and i > 0:
            continue
        tokens.append(tok)
    # Two words is enough to identify a merchant and avoids splitting on trailing noise.
    return ' '.join(tokens[:2])


def _classify(interval_days):
    for name, nominal, tol in CADENCES:
        if abs(interval_days - nominal) <= tol:
            return name, nominal
    return None, None


def _median(values):
    v = sorted(values)
    n = len(v)
    if not n:
        return 0.0
    return float(v[n // 2]) if n % 2 else (float(v[n // 2 - 1]) + float(v[n // 2])) / 2.0


def detect(transactions, today=None):
    """Find recurring charges.

    `transactions`: dicts with posted_at (date), amount (positive = money out), and one of
    merchant / description. Refunds and credits are ignored — a negative amount is not a
    subscription.
    """
    today = today or date.today()
    groups = defaultdict(list)
    for t in transactions:
        amount = float(t.get('amount') or 0)
        when = t.get('posted_at')
        if amount <= 0 or not when:
            continue
        key = merchant_key(t.get('merchant') or t.get('description'))
        if not key:
            continue
        groups[key].append({'date': when, 'amount': amount,
                            'label': (t.get('merchant') or t.get('description') or key),
                            'category': t.get('category') or 'other'})

    found = []
    for key, rows in groups.items():
        if len(rows) < MIN_OCCURRENCES:
            continue
        rows.sort(key=lambda r: r['date'])

        # Amount stability first: a merchant charged three times at wildly different amounts
        # is a shop someone visits, not a subscription.
        amounts = [r['amount'] for r in rows]
        typical = _median(amounts)
        if typical <= 0:
            continue
        consistent = [a for a in amounts if abs(a - typical) <= typical * AMOUNT_TOLERANCE]
        if len(consistent) < MIN_OCCURRENCES:
            continue

        gaps = [(rows[i]['date'] - rows[i - 1]['date']).days for i in range(1, len(rows))]
        gaps = [g for g in gaps if g > 0]
        if len(gaps) < MIN_OCCURRENCES - 1:
            continue
        median_gap = _median(gaps)
        cadence, nominal = _classify(median_gap)
        if not cadence:
            continue
        # Most intervals must actually match the cadence; one holiday-shifted charge is
        # fine, but a merchant visited at random intervals that averages out to ~30 days is
        # not a subscription.
        tol = dict((c[0], c[2]) for c in CADENCES)[cadence]
        on_schedule = [g for g in gaps if abs(g - nominal) <= tol * 2]
        if len(on_schedule) < max(2, int(len(gaps) * 0.6)):
            continue

        last = rows[-1]['date']
        next_expected = last + timedelta(days=int(round(median_gap)))
        # Stopped if more than half a cycle past due, which avoids calling something dead
        # the day after it was expected.
        stopped = (today - last).days > median_gap * 1.5
        latest = rows[-1]['amount']
        prior = _median([r['amount'] for r in rows[:-1]]) if len(rows) > 1 else latest

        found.append({
            'merchant_key': key,
            'label': rows[-1]['label'],
            'category': rows[-1]['category'],
            'cadence': cadence,
            'interval_days': int(round(median_gap)),
            'typical_amount': round(typical, 2),
            'latest_amount': round(latest, 2),
            'previous_amount': round(prior, 2),
            'monthly_equivalent': round(typical * 30.0 / median_gap, 2),
            'annual_equivalent': round(typical * 365.0 / median_gap, 2),
            'occurrences': len(rows),
            'first_seen': rows[0]['date'].isoformat(),
            'last_seen': last.isoformat(),
            'next_expected': next_expected.isoformat(),
            'status': 'stopped' if stopped else 'active',
            'price_increased': latest > prior * (1 + PRICE_INCREASE_THRESHOLD),
            'price_change': round(latest - prior, 2),
            'days_until_next': (next_expected - today).days,
        })

    found.sort(key=lambda r: -r['annual_equivalent'])
    return found


def bill_matches(charge, bills):
    """Whether a declared RecurringBill plausibly covers this detected charge.

    Matched on merchant identity rather than amount: a bill whose amount drifted is still
    the same bill, whereas two unrelated services costing the same are not.
    """
    ck = charge['merchant_key']
    for b in bills:
        for candidate in (b.get('payee'), b.get('name')):
            bk = merchant_key(candidate)
            if not bk:
                continue
            if bk == ck or bk.split()[0] == ck.split()[0]:
                return b
    return None


def annotate_matches(charges, bills):
    """Record which declared bill covers each charge.

    Separate from findings() because it MUTATES. findings() used to do this as a side
    effect, so calling it twice with different bills quietly rewrote the earlier answer — a
    reporting function should not edit what it was given.
    """
    for ch in charges:
        matched = bill_matches(ch, bills)
        ch['matched_bill_id'] = matched.get('id') if matched else None
    return charges


def findings(charges, bills, decisions=None, horizon_days=30):
    """Turn detected charges into things worth telling someone.

    Anything the user dismissed or linked to a bill is excluded — a detector that keeps
    re-raising a resolved item teaches people to ignore it.
    """
    decisions = decisions or {}
    out = []
    for ch in charges:
        d = decisions.get(ch['merchant_key'])
        if d == 'dismissed':
            continue
        matched = bill_matches(ch, bills)
        if ch['status'] == 'active' and not matched and d != 'linked':
            out.append({
                'kind': 'undeclared', 'merchant_key': ch['merchant_key'],
                'title': '%s looks like a subscription you have not recorded' % ch['label'],
                'detail': '%s %s since %s, about %s a year. It is not among your bills, so '
                          'it is missing from budgets and cash-flow projections.' % (
                              _money(ch['typical_amount']), ch['cadence'], ch['first_seen'],
                              _money(ch['annual_equivalent'])),
                'amount': ch['annual_equivalent'],
            })
        if ch['price_increased'] and ch['status'] == 'active':
            out.append({
                'kind': 'price_increase', 'merchant_key': ch['merchant_key'],
                'title': '%s went up' % ch['label'],
                'detail': 'Last charge %s against a usual %s — %s more, or %s a year at this '
                          'cadence.' % (_money(ch['latest_amount']), _money(ch['previous_amount']),
                                        _money(ch['price_change']),
                                        _money(ch['price_change'] * 365.0 / ch['interval_days'])),
                'amount': round(ch['price_change'] * 365.0 / ch['interval_days'], 2),
            })
        if ch['status'] == 'stopped':
            out.append({
                'kind': 'stopped', 'merchant_key': ch['merchant_key'],
                'title': '%s has stopped charging' % ch['label'],
                'detail': 'Expected around %s but nothing since %s. Either it was cancelled, '
                          'or a payment failed and the service may lapse.' % (
                              ch['next_expected'], ch['last_seen']),
                'amount': 0,
            })
        if (ch['status'] == 'active' and ch['interval_days'] >= 80
                and 0 <= ch['days_until_next'] <= horizon_days):
            out.append({
                'kind': 'renewal_due', 'merchant_key': ch['merchant_key'],
                'title': '%s renews in %d days' % (ch['label'], ch['days_until_next']),
                'detail': 'A %s charge of about %s falls due on %s. Infrequent charges are '
                          'the ones that surprise a budget.' % (
                              ch['cadence'], _money(ch['typical_amount']), ch['next_expected']),
                'amount': ch['typical_amount'],
            })
    order = {'undeclared': 0, 'price_increase': 1, 'renewal_due': 2, 'stopped': 3}
    out.sort(key=lambda f: (order.get(f['kind'], 9), -abs(f.get('amount') or 0)))
    return out


def _money(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    return ('-$%s' if n < 0 else '$%s') % format(abs(n), ',.2f')
