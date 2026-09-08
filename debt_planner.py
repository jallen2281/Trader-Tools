"""Debt payoff simulation: avalanche, snowball, and what the choice actually costs.

Both strategies pay every minimum and throw everything spare at ONE debt, then roll that
debt's freed-up payment into the next. They differ only in the order. Avalanche targets the
highest APR and is always cheaper or equal. Snowball targets the smallest balance and closes
accounts sooner, which is the whole point of it — the evidence is that people stick with it,
and a plan someone follows beats a cheaper one they abandon.

So this reports both and states the gap in dollars and months rather than picking for
anyone. If avalanche saves $40, snowball is a fine choice; if it saves $4,000, that is worth
knowing before deciding.

Month-by-month simulation rather than a closed-form amortisation, because the rolling
payment changes the balance path in a way the formula cannot express, and because the
interesting failures — a minimum that does not cover interest — only show up if you actually
run it.

Pure functions over plain dicts, so it is testable without a database.
"""
from datetime import date

# A guard, not a modelling choice. Without it a debt whose payment never covers its interest
# loops forever; with it the simulation ends and the debt is reported as never paying off,
# which is the honest answer and the one worth showing someone.
MAX_MONTHS = 600


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    # Clamp rather than roll over: the 31st in a 30-day month is that month's end, not the
    # 1st of the next, which would drift the whole schedule forward.
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def _prepare(debts):
    out = []
    for d in debts or []:
        bal = float(d.get('balance') or 0)
        if bal <= 0:
            continue
        out.append({
            'id': d.get('id'),
            'name': d.get('name') or 'debt',
            'balance': bal,
            'apr': max(float(d.get('apr') or 0), 0.0),
            'min_payment': max(float(d.get('min_payment') or 0), 0.0),
            'interest_paid': 0.0,
            'paid': 0.0,
        })
    return out


def _order(debts, strategy):
    if strategy == 'snowball':
        # Smallest balance first; APR breaks ties so the cheaper win comes first.
        return sorted(debts, key=lambda d: (d['balance'], -d['apr']))
    # Avalanche: highest rate first, larger balance breaking ties because it accrues more.
    return sorted(debts, key=lambda d: (-d['apr'], -d['balance']))


def simulate(debts, extra_monthly=0.0, strategy='avalanche', start=None,
             max_months=MAX_MONTHS):
    """Run the plan to its end (or the horizon) and report what it cost.

    `extra_monthly` is money above the minimums. Whatever a cleared debt used to consume is
    rolled into the next target — that rolling is what makes either strategy accelerate, and
    leaving it out would understate both by a wide margin.
    """
    start = start or date.today()
    rows = _prepare(debts)
    if not rows:
        return {'strategy': strategy, 'months': 0, 'total_interest': 0.0, 'total_paid': 0.0,
                'debt_free_on': None, 'order': [], 'never_pays_off': [],
                'monthly_outlay': round(float(extra_monthly or 0), 2), 'balances': []}

    extra = max(float(extra_monthly or 0), 0.0)
    # The total sent out each month stays flat for the life of the plan: as a debt clears,
    # its payment is redirected rather than pocketed.
    outlay = sum(d['min_payment'] for d in rows) + extra
    order = _order(rows, strategy)
    cleared, balances = [], []

    month = 0
    while any(d['balance'] > 0 for d in rows) and month < max_months:
        month += 1
        budget = outlay

        # Interest first, then minimums, then everything left over onto the target. Charging
        # interest before payment is what a lender does; doing it the other way round
        # understates the cost of every plan by a month of interest.
        for d in rows:
            if d['balance'] <= 0:
                continue
            interest = d['balance'] * d['apr'] / 100.0 / 12.0
            d['balance'] += interest
            d['interest_paid'] += interest

        for d in order:
            if d['balance'] <= 0:
                continue
            pay = min(d['min_payment'], d['balance'], budget)
            d['balance'] -= pay
            d['paid'] += pay
            budget -= pay

        for d in order:
            if budget <= 0:
                break
            if d['balance'] <= 0:
                continue
            pay = min(budget, d['balance'])
            d['balance'] -= pay
            d['paid'] += pay
            budget -= pay

        for d in order:
            # Sub-cent residue is a rounding artefact, not a debt.
            if 0 < d['balance'] < 0.01:
                d['balance'] = 0.0
            if d['balance'] <= 0 and not any(c['id'] == d['id'] for c in cleared):
                cleared.append({'id': d['id'], 'name': d['name'], 'months': month,
                                'payoff_on': _add_months(start, month).isoformat(),
                                'interest_paid': round(d['interest_paid'], 2),
                                'total_paid': round(d['paid'], 2)})
        balances.append({'month': month,
                         'total_balance': round(sum(max(d['balance'], 0) for d in rows), 2)})

    never = [{'id': d['id'], 'name': d['name'], 'balance': round(d['balance'], 2),
              'reason': 'the payment does not cover the interest at this APR'}
             for d in rows if d['balance'] > 0]

    done = month if not never else None
    return {
        'strategy': strategy,
        'months': done,
        'debt_free_on': _add_months(start, month).isoformat() if done else None,
        'total_interest': round(sum(d['interest_paid'] for d in rows), 2),
        'total_paid': round(sum(d['paid'] for d in rows), 2),
        'monthly_outlay': round(outlay, 2),
        'extra_monthly': round(extra, 2),
        # Payoff order, soonest first — the sequence someone actually follows.
        'order': cleared,
        'never_pays_off': never,
        'balances': balances,
    }


def compare(debts, extra_monthly=0.0, start=None):
    """Both strategies side by side, with the cost of choosing the friendlier one."""
    av = simulate(debts, extra_monthly, 'avalanche', start=start)
    sn = simulate(debts, extra_monthly, 'snowball', start=start)
    both_finish = av['months'] is not None and sn['months'] is not None
    return {
        'avalanche': av,
        'snowball': sn,
        'interest_saved_by_avalanche': (round(sn['total_interest'] - av['total_interest'], 2)
                                        if both_finish else None),
        'months_saved_by_avalanche': (sn['months'] - av['months']) if both_finish else None,
        # Snowball's payoff is behavioural: the first account closes sooner. Quantify that
        # too, so the trade is visible from both sides instead of only the cost.
        'first_payoff_months': {
            'avalanche': av['order'][0]['months'] if av['order'] else None,
            'snowball': sn['order'][0]['months'] if sn['order'] else None,
        },
    }


def extra_payment_impact(debts, extra_options=(50, 100, 250, 500), base_extra=0.0,
                         strategy='avalanche', start=None):
    """What another $50, $100, $250 a month would actually buy.

    Framed as a return rather than a schedule: paying a 24% card is a guaranteed 24% return,
    which is the comparison that makes the decision, and it is invisible in a payoff date.
    """
    base = simulate(debts, base_extra, strategy, start=start)
    out = []
    for add in extra_options:
        s = simulate(debts, base_extra + add, strategy, start=start)
        if s['months'] is None or base['months'] is None:
            continue
        out.append({
            'extra': add,
            'months': s['months'],
            'months_sooner': base['months'] - s['months'],
            'interest_saved': round(base['total_interest'] - s['total_interest'], 2),
            'debt_free_on': s['debt_free_on'],
        })
    return {'base': base, 'options': out}


def findings(plan_compare, debts, today=None):
    """The few things worth saying out loud about a debt picture."""
    out = []
    av = plan_compare.get('avalanche') or {}
    sn = plan_compare.get('snowball') or {}

    for d in (av.get('never_pays_off') or []):
        out.append({
            'kind': 'debt', 'severity': 'critical', 'key': 'never_pays_off:%s' % d['id'],
            'title': '%s never pays off at the current payment' % d['name'],
            'detail': 'The minimum on this balance does not cover the interest it accrues, '
                      'so the balance grows no matter how long you keep paying. It needs a '
                      'larger payment, a lower rate, or a transfer.',
            'amount': d['balance'],
        })

    saved = plan_compare.get('interest_saved_by_avalanche')
    if saved is not None and saved >= 100:
        out.append({
            'kind': 'debt', 'severity': 'note', 'key': 'strategy_gap',
            'title': 'Highest-rate-first would save %s in interest' % _money(saved),
            'detail': 'Avalanche clears in %d months against snowball\'s %d. Snowball closes '
                      'its first account in %s months rather than %s, which is worth '
                      'something if that is what keeps you at it — but this is the price.' % (
                          av.get('months') or 0, sn.get('months') or 0,
                          plan_compare.get('first_payoff_months', {}).get('snowball'),
                          plan_compare.get('first_payoff_months', {}).get('avalanche')),
            'amount': saved,
        })

    # A "your highest-rate debt is expensive" rule deliberately does NOT live here.
    # _finance_observations already raises high_apr_debt from the outlook, and two
    # observations saying the same thing about the same card is how an findings list starts
    # getting skimmed instead of read.

    rank = {'critical': 0, 'warning': 1, 'note': 2}
    out.sort(key=lambda f: (rank.get(f['severity'], 3), -abs(f.get('amount') or 0)))
    return out


def _money(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    return ('-$%s' if n < 0 else '$%s') % format(abs(n), ',.0f')
