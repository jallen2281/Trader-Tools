"""Credit health: utilization arithmetic and score trends.

Two things drive a credit score that this app can actually see. Utilization — revolving
balance against revolving limit — is about 30% of a FICO score and is the fastest-moving
lever a person has: it is recalculated when the statement posts, so paying a card down
shows up in weeks rather than years. The score itself is the outcome, and worth tracking
only as a series.

The series part matters more than it looks. Scores from different bureaus and different
scoring models are NOT comparable — a VantageScore 3.0 from a free app and a FICO 8 from a
card issuer routinely differ by 20-40 points for the same person on the same day. Plotting
them on one line manufactures drops and gains that never happened, so readings are grouped
by (bureau, scale) and a trend is only ever computed within a series.

Pure functions over plain dicts, so the whole thing is testable without a database.
"""
from datetime import date

# Thresholds are the conventional advice, and the reason for each is different:
# 30% is where the scoring penalty starts to bite, 50% is where it becomes substantial,
# and 90% reads as a maxed account regardless of what the rest of the file looks like.
UTILIZATION_GOOD = 0.30
UTILIZATION_HIGH = 0.50
CARD_MAXED = 0.90

# A drop this size is a real event (a new balance reported, a limit cut, a late mark)
# rather than the few-point noise every score shows month to month.
MATERIAL_SCORE_MOVE = 15
STALE_AFTER_DAYS = 120

# FICO and VantageScore both run 300-850; the industry-specific FICO scores (auto,
# bankcard) run 250-900. Accept the widest real range rather than rejecting a genuine
# reading someone is trying to record.
SCORE_MIN, SCORE_MAX = 250, 900

BUREAUS = ('equifax', 'experian', 'transunion', 'other')
SCALES = ('fico8', 'fico9', 'fico2', 'vantage3', 'vantage4', 'other')
SCALE_LABEL = {'fico8': 'FICO 8', 'fico9': 'FICO 9', 'fico2': 'FICO 2',
               'vantage3': 'VantageScore 3.0', 'vantage4': 'VantageScore 4.0',
               'other': 'other'}

# Descending, so the first band whose floor the score clears is the answer.
BANDS = ((800, 'exceptional'), (740, 'very good'), (670, 'good'),
         (580, 'fair'), (0, 'poor'))


def band(score):
    """The lender-facing label for a score. None in, None out."""
    if score is None:
        return None
    for floor, name in BANDS:
        if score >= floor:
            return name
    return 'poor'


def utilization(cards):
    """Revolving utilization, overall and per card.

    `cards`: dicts with name, balance and credit_limit. Only cards with a limit recorded
    can contribute — a card whose limit is unknown is counted as `unknown` rather than as
    zero, because treating it as zero would report a comfortable ratio for someone whose
    real one is terrible.

    Per-card ratios are kept alongside the overall figure because they answer different
    questions: scoring models look at both, and one maxed card is a problem even when the
    total across every card is modest.
    """
    known, unknown = [], []
    for c in cards or []:
        limit = float(c.get('credit_limit') or 0)
        bal = max(float(c.get('balance') or 0), 0.0)
        if limit > 0:
            known.append({'id': c.get('id'), 'name': c.get('name'), 'balance': round(bal, 2),
                          'credit_limit': round(limit, 2),
                          'available': round(limit - bal, 2),
                          'ratio': round(bal / limit, 4),
                          'pct': round(bal / limit * 100, 1)})
        else:
            unknown.append({'id': c.get('id'), 'name': c.get('name'),
                            'balance': round(bal, 2)})
    total_bal = round(sum(c['balance'] for c in known), 2)
    total_lim = round(sum(c['credit_limit'] for c in known), 2)
    ratio = (total_bal / total_lim) if total_lim > 0 else None
    known.sort(key=lambda c: -c['ratio'])
    return {
        'cards': known,
        'cards_without_limit': unknown,
        'total_balance': total_bal,
        'total_limit': total_lim,
        'available': round(total_lim - total_bal, 2),
        'ratio': round(ratio, 4) if ratio is not None else None,
        'pct': round(ratio * 100, 1) if ratio is not None else None,
        'highest_card': known[0] if known else None,
    }


def paydown_to(util, target=UTILIZATION_GOOD):
    """Dollars that must come off the revolving balance to reach `target` overall.

    Returned as an amount rather than a percentage because that is the form the decision
    takes: a number to move, not a ratio to contemplate. Zero when already under.
    """
    lim = util.get('total_limit') or 0
    if lim <= 0:
        return 0.0
    need = util.get('total_balance', 0) - lim * target
    return round(max(need, 0.0), 2)


def _key(r):
    return '%s/%s' % (r.get('bureau') or 'other', r.get('scale') or 'other')


def series(readings):
    """Group score readings into comparable series and describe each one's trend.

    One series per (bureau, scale). Comparing across them is the single most common way to
    misread a credit score, so the grouping is not optional.
    """
    groups = {}
    for r in readings or []:
        if r.get('score') is None:
            continue
        groups.setdefault(_key(r), []).append(r)

    out = []
    for key, rows in groups.items():
        rows = sorted(rows, key=lambda r: r['as_of'])
        latest, first = rows[-1], rows[0]
        prev = rows[-2] if len(rows) > 1 else None
        out.append({
            'key': key,
            'bureau': latest.get('bureau') or 'other',
            'scale': latest.get('scale') or 'other',
            'scale_label': SCALE_LABEL.get(latest.get('scale') or 'other', 'other'),
            'latest': latest['score'],
            'latest_on': latest['as_of'].isoformat(),
            'band': band(latest['score']),
            'previous': prev['score'] if prev else None,
            'previous_on': prev['as_of'].isoformat() if prev else None,
            'change': (latest['score'] - prev['score']) if prev else None,
            'first': first['score'],
            'first_on': first['as_of'].isoformat(),
            'change_all_time': (latest['score'] - first['score']) if len(rows) > 1 else None,
            'readings': len(rows),
            'history': [{'as_of': r['as_of'].isoformat(), 'score': r['score']} for r in rows],
        })
    # Most recent reading first: the series someone actually keeps up to date is the one
    # they want to see at the top.
    out.sort(key=lambda s: (s['latest_on'], s['readings']), reverse=True)
    return out


def findings(util, series_list, today=None, has_revolving=True):
    """Things worth telling someone about their credit, worst first.

    Every rule states the number and, where there is one, the move — "pay $1,240 off the
    Visa" is actionable in a way that "your utilization is high" is not.
    """
    today = today or date.today()
    out = []
    pct = util.get('pct')

    if pct is not None and util.get('ratio', 0) >= UTILIZATION_HIGH:
        out.append({
            'kind': 'utilization', 'severity': 'warning', 'key': 'utilization_high',
            'title': 'Revolving utilization is %.0f%%' % pct,
            'detail': '%s of %s in revolving credit is in use. Utilization is roughly a '
                      'third of a credit score and updates as each statement posts, so it '
                      'is the fastest lever here: paying %s down brings it under 30%%.' % (
                          _money(util['total_balance']), _money(util['total_limit']),
                          _money(paydown_to(util))),
            'amount': paydown_to(util),
        })
    elif pct is not None and util.get('ratio', 0) >= UTILIZATION_GOOD:
        out.append({
            'kind': 'utilization', 'severity': 'note', 'key': 'utilization_elevated',
            'title': 'Revolving utilization is %.0f%%' % pct,
            'detail': 'Above the 30%% line where the scoring penalty starts. %s off the '
                      'balance clears it.' % _money(paydown_to(util)),
            'amount': paydown_to(util),
        })

    # A single maxed card is penalised on its own, so it is worth naming even when the
    # overall ratio looks fine.
    for c in util.get('cards', []):
        if c['ratio'] >= CARD_MAXED and (pct is None or util['ratio'] < UTILIZATION_HIGH):
            out.append({
                'kind': 'utilization', 'severity': 'warning', 'key': 'card_maxed:%s' % c['id'],
                'title': '%s is at %.0f%% of its limit' % (c['name'], c['pct']),
                'detail': 'Scoring models look at each card as well as the total. %s of %s '
                          'is used, leaving %s available.' % (
                              _money(c['balance']), _money(c['credit_limit']),
                              _money(c['available'])),
                'amount': c['balance'],
            })

    missing = util.get('cards_without_limit') or []
    if missing:
        out.append({
            'kind': 'data', 'severity': 'note', 'key': 'missing_limits',
            'title': '%d card%s missing a credit limit' % (
                len(missing), '' if len(missing) == 1 else 's'),
            'detail': 'Utilization cannot be computed for %s, so the figure above covers '
                      'only part of the picture. The limit is on the statement.' % (
                          ', '.join(c['name'] for c in missing[:3])),
        })

    for s in series_list or []:
        if s['change'] is not None and s['change'] <= -MATERIAL_SCORE_MOVE:
            out.append({
                'kind': 'score', 'severity': 'warning', 'key': 'score_drop:%s' % s['key'],
                'title': '%s score fell %d points' % (s['bureau'].title(), abs(s['change'])),
                'detail': '%s on %s, down from %s on %s (%s). A move that size usually '
                          'follows a higher reported balance, a new account, or a missed '
                          'payment.' % (s['latest'], s['latest_on'], s['previous'],
                                        s['previous_on'], s['scale_label']),
                'amount': abs(s['change']),
            })
        elif s['change'] is not None and s['change'] >= MATERIAL_SCORE_MOVE:
            out.append({
                'kind': 'score', 'severity': 'note', 'key': 'score_gain:%s' % s['key'],
                'title': '%s score rose %d points' % (s['bureau'].title(), s['change']),
                'detail': '%s on %s, up from %s (%s) — now %s.' % (
                    s['latest'], s['latest_on'], s['previous'], s['scale_label'],
                    s['band']),
                'amount': s['change'],
            })

    if series_list:
        newest = max(s['latest_on'] for s in series_list)
        age = (today - date(*[int(x) for x in newest.split('-')])).days
        if age > STALE_AFTER_DAYS:
            out.append({
                'kind': 'data', 'severity': 'note', 'key': 'score_stale',
                'title': 'No credit score recorded in %d months' % (age // 30),
                'detail': 'Last reading %s. Scores are free from the card issuer or the '
                          'bureau; without a recent one the trend here is guesswork.' % newest,
            })
    elif has_revolving:
        out.append({
            'kind': 'data', 'severity': 'note', 'key': 'no_scores',
            'title': 'No credit score recorded',
            'detail': 'Adding a reading or two makes the effect of paying down a card '
                      'visible, instead of having to take it on faith.',
        })

    rank = {'critical': 0, 'warning': 1, 'note': 2}
    out.sort(key=lambda f: (rank.get(f['severity'], 3), -abs(f.get('amount') or 0)))
    return out


def _money(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    return ('-$%s' if n < 0 else '$%s') % format(abs(n), ',.0f')
