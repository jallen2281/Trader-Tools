"""
Tax analyzer — realized capital gains with short-term / long-term classification.

The foundation tile of the Tax Center. Computes realized gains from the
transaction ledger using lot-matching:

  - FIFO (default), LIFO, or HIFO lot selection (HIFO minimizes gains).
  - Lots are scoped per (account, symbol) so the same ticker held in two
    accounts never cross-matches (each broker tracks its own basis).
  - Holding period > 365 days => long-term; otherwise short-term.
  - Tax-advantaged accounts (401k / IRA / Roth / HSA) are excluded — trades
    there are not taxable events.

When a sell can't be fully matched to recorded buy lots (the ledger predates
the position), the unmatched quantity falls back to the current holding's
average cost and is flagged `estimated` so the UI can warn. Accuracy improves
as full lot-level history is imported (RH tax lots, Kraken CSV) — that's the
next build on top of this engine.
"""
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

LONG_TERM_DAYS = 365  # held MORE than one year => long-term
TAX_ADVANTAGED_HINTS = ('401k', '401(k)', 'ira', 'roth', 'retirement', 'hsa', 'sep')
VALID_METHODS = ('fifo', 'lifo', 'hifo')


def is_tax_advantaged(name):
    n = (name or '').lower()
    return any(h in n for h in TAX_ADVANTAGED_HINTS)


class TaxAnalyzer:
    """Realized-gain lot accounting over the Transaction ledger."""

    def __init__(self):
        # Imported lazily to mirror the rest of the codebase's model usage.
        from models import Transaction, Portfolio, PortfolioAccount
        self.Transaction = Transaction
        self.Portfolio = Portfolio
        self.PortfolioAccount = PortfolioAccount

    @staticmethod
    def _as_date(d):
        if d is None:
            return None
        return d.date() if isinstance(d, datetime) else d

    def _pick_lot_index(self, bucket, method):
        if method == 'lifo':
            return len(bucket) - 1
        if method == 'hifo':
            return max(range(len(bucket)), key=lambda i: bucket[i]['price'])
        return 0  # fifo

    def _fallback_basis(self, user_id, account_id, symbol):
        """Basis-per-share + acquired date from the current holding, when the
        ledger has no buy lot to match a sell against."""
        q = self.Portfolio.query.filter_by(user_id=user_id, symbol=symbol)
        if account_id is not None:
            q = q.filter_by(account_id=account_id)
        h = q.first()
        if h:
            return float(getattr(h, 'average_cost', 0) or 0), self._as_date(getattr(h, 'purchase_date', None))
        return 0.0, None

    def available_years(self, user_id):
        years = set()
        for t in self.Transaction.query.filter(
            self.Transaction.user_id == user_id,
            self.Transaction.transaction_type == 'sell'
        ).all():
            if t.transaction_date:
                years.add(t.transaction_date.year)
        return sorted(years, reverse=True)

    def realized_gains(self, user_id, year=None, account_id=None, method='fifo'):
        method = (method or 'fifo').lower()
        if method not in VALID_METHODS:
            method = 'fifo'

        accounts = {a.id: a.name for a in self.PortfolioAccount.query.filter_by(user_id=user_id).all()}
        advantaged = {aid for aid, nm in accounts.items() if is_tax_advantaged(nm)}

        txns = self.Transaction.query.filter(
            self.Transaction.user_id == user_id
        ).order_by(self.Transaction.transaction_date.asc()).all()

        lots = defaultdict(list)  # (account_id, symbol) -> [{qty, price, date}]
        disposals = []

        for t in txns:
            acct = t.account_id
            if acct in advantaged:
                continue
            if account_id is not None and acct != account_id:
                continue
            if (t.asset_type or 'stock') == 'option':
                continue  # options have distinct tax treatment — added later

            symbol = (t.symbol or '').upper()
            key = (acct, symbol)
            qty = float(t.quantity or 0)
            price = float(t.price or 0)
            tdate = self._as_date(t.transaction_date) or self._as_date(datetime.utcnow())

            if t.transaction_type == 'buy':
                lots[key].append({'qty': qty, 'price': price, 'date': tdate})

            elif t.transaction_type == 'sell':
                remaining = qty
                bucket = lots[key]
                while remaining > 1e-9 and bucket:
                    idx = self._pick_lot_index(bucket, method)
                    lot = bucket[idx]
                    take = min(remaining, lot['qty'])
                    hold_days = (tdate - lot['date']).days if lot['date'] else None
                    disposals.append(self._disposal(
                        symbol, acct, accounts.get(acct), take, lot['date'], tdate,
                        take * price, take * lot['price'], hold_days, estimated=False))
                    lot['qty'] -= take
                    remaining -= take
                    if lot['qty'] <= 1e-9:
                        bucket.pop(idx)
                if remaining > 1e-9:
                    est_ps, acq = self._fallback_basis(user_id, acct, symbol)
                    hold_days = (tdate - acq).days if acq else None
                    disposals.append(self._disposal(
                        symbol, acct, accounts.get(acct), remaining, acq, tdate,
                        remaining * price, remaining * est_ps, hold_days, estimated=True))

        if year:
            disposals = [d for d in disposals if d['sold_date'][:4] == str(year)]

        st = [d for d in disposals if d['term'] == 'short']
        lt = [d for d in disposals if d['term'] == 'long']

        def _sum(rows, k):
            return round(sum(r[k] for r in rows), 2)

        summary = {
            'short_term': {'gain': _sum(st, 'gain'), 'proceeds': _sum(st, 'proceeds'),
                           'basis': _sum(st, 'basis'), 'count': len(st)},
            'long_term': {'gain': _sum(lt, 'gain'), 'proceeds': _sum(lt, 'proceeds'),
                          'basis': _sum(lt, 'basis'), 'count': len(lt)},
            'total_gain': round(_sum(st, 'gain') + _sum(lt, 'gain'), 2),
            'total_proceeds': round(_sum(st, 'proceeds') + _sum(lt, 'proceeds'), 2),
            'disposal_count': len(disposals),
            'estimated_count': sum(1 for d in disposals if d['estimated']),
        }
        disposals.sort(key=lambda d: d['sold_date'], reverse=True)
        return {
            'method': method,
            'year': year,
            'account_id': account_id,
            'excluded_accounts': sorted(accounts[a] for a in advantaged),
            'summary': summary,
            'disposals': disposals,
        }

    def harvest_candidates(self, user_id):
        """Unrealized losers that could be harvested to offset gains, with
        wash-sale and IPO-lock flags + short/long classification.

        Wash sale = bought the same symbol within 30 days (a loss sale then has
        its loss disallowed). Flags are based on recorded buy dates, so a
        snapshot-dated position can over-flag until real lots are imported.
        Uses each holding's cached current_price (kept fresh by the list view).
        """
        from datetime import date, timedelta
        accounts = {a.id: a.name for a in self.PortfolioAccount.query.filter_by(user_id=user_id).all()}
        advantaged = {aid for aid, nm in accounts.items() if is_tax_advantaged(nm)}
        today = date.today()
        wash_start = today - timedelta(days=30)

        recent_buy_symbols = set()
        for t in self.Transaction.query.filter(
            self.Transaction.user_id == user_id,
            self.Transaction.transaction_type == 'buy'
        ).all():
            d = self._as_date(t.transaction_date)
            if d and d >= wash_start:
                recent_buy_symbols.add((t.symbol or '').upper())

        candidates = []
        for h in self.Portfolio.query.filter_by(user_id=user_id).all():
            if h.account_id in advantaged:
                continue
            sym = (h.symbol or '').upper()
            if sym == 'TA401K':
                continue
            cp = getattr(h, 'current_price', None)
            if not cp:
                continue
            cp = float(cp)
            cost = float(h.average_cost or 0)
            qty = float(h.quantity or 0)
            loss = (cp - cost) * qty
            if loss >= -0.5:  # losers only
                continue
            acq = self._as_date(getattr(h, 'purchase_date', None))
            hold_days = (today - acq).days if acq else None
            term = 'long' if (hold_days is not None and hold_days > LONG_TERM_DAYS) else 'short'
            lock_until = self._as_date(getattr(h, 'ipo_lock_until', None))
            locked = bool(lock_until and lock_until > today)
            wash = (sym in recent_buy_symbols) or (acq is not None and acq >= wash_start)
            candidates.append({
                'symbol': sym,
                'account_id': h.account_id,
                'account_name': accounts.get(h.account_id),
                'quantity': round(qty, 6),
                'cost_basis': round(cost, 4),
                'current_price': round(cp, 4),
                'market_value': round(cp * qty, 2),
                'unrealized_loss': round(loss, 2),
                'loss_pct': round(loss / (cost * qty) * 100, 2) if cost * qty else None,
                'term': term,
                'hold_days': hold_days,
                'wash_sale': wash,
                'locked': locked,
                'lock_until': lock_until.isoformat() if lock_until else None,
                'intent': getattr(h, 'intent', None),
                'harvestable': (not locked) and (not wash),
            })

        candidates.sort(key=lambda c: c['unrealized_loss'])  # biggest loss first
        harvest = [c for c in candidates if c['harvestable']]

        def _sum(rows):
            return round(sum(r['unrealized_loss'] for r in rows), 2)

        summary = {
            'total_unrealized_loss': _sum(candidates),
            'harvestable_loss': _sum(harvest),
            'harvestable_short': _sum([c for c in harvest if c['term'] == 'short']),
            'harvestable_long': _sum([c for c in harvest if c['term'] == 'long']),
            'candidate_count': len(candidates),
            'harvestable_count': len(harvest),
            'blocked_count': len(candidates) - len(harvest),
        }
        return {
            'summary': summary,
            'candidates': candidates,
            'excluded_accounts': sorted(accounts[a] for a in advantaged),
        }

    def lt_threshold(self, user_id):
        """Positions with unrealized GAINS that are still short-term — i.e.
        approaching the 1-year mark where the rate drops from ordinary income to
        the long-term rate. Sorted by days-to-long-term (soonest first).

        LT requires holding MORE than one year, so the first long-term day is
        acquisition + 366 days. Only gains matter here (a loss is the harvesting
        angle, not this one). Snapshot-dated positions (RH 2026-07-08 import)
        will read as newer than reality until real lots are imported.
        """
        from datetime import date, timedelta
        accounts = {a.id: a.name for a in self.PortfolioAccount.query.filter_by(user_id=user_id).all()}
        advantaged = {aid for aid, nm in accounts.items() if is_tax_advantaged(nm)}
        today = date.today()

        rows = []
        for h in self.Portfolio.query.filter_by(user_id=user_id).all():
            if h.account_id in advantaged:
                continue
            sym = (h.symbol or '').upper()
            if sym == 'TA401K':
                continue
            cp = getattr(h, 'current_price', None)
            if not cp:
                continue
            cp = float(cp)
            cost = float(h.average_cost or 0)
            qty = float(h.quantity or 0)
            gain = (cp - cost) * qty
            if gain <= 0.5:  # only gains benefit from reaching long-term
                continue
            acq = self._as_date(getattr(h, 'purchase_date', None))
            if not acq:
                continue
            hold_days = (today - acq).days
            if hold_days > LONG_TERM_DAYS:  # already long-term
                continue
            days_to_lt = (LONG_TERM_DAYS + 1) - hold_days  # days until held > 1 year
            lt_date = acq + timedelta(days=LONG_TERM_DAYS + 1)
            rows.append({
                'symbol': sym,
                'account_id': h.account_id,
                'account_name': accounts.get(h.account_id),
                'quantity': round(qty, 6),
                'cost_basis': round(cost, 4),
                'current_price': round(cp, 4),
                'unrealized_gain': round(gain, 2),
                'gain_pct': round(gain / (cost * qty) * 100, 2) if cost * qty else None,
                'hold_days': hold_days,
                'days_to_lt': days_to_lt,
                'lt_date': lt_date.isoformat(),
                'intent': getattr(h, 'intent', None),
            })

        rows.sort(key=lambda r: r['days_to_lt'])

        def _g(rows_):
            return round(sum(r['unrealized_gain'] for r in rows_), 2)

        summary = {
            'count': len(rows),
            'total_gain_short': _g(rows),
            'within_30_count': sum(1 for r in rows if r['days_to_lt'] <= 30),
            'within_90_count': sum(1 for r in rows if r['days_to_lt'] <= 90),
            'gain_within_90': _g([r for r in rows if r['days_to_lt'] <= 90]),
        }
        return {'summary': summary, 'positions': rows,
                'excluded_accounts': sorted(accounts[a] for a in advantaged)}

    def _disposal(self, symbol, acct, acct_name, qty, acquired, sold, proceeds, basis, hold_days, estimated):
        gain = proceeds - basis
        term = 'long' if (hold_days is not None and hold_days > LONG_TERM_DAYS) else 'short'
        return {
            'symbol': symbol,
            'account_id': acct,
            'account_name': acct_name,
            'quantity': round(qty, 6),
            'acquired_date': acquired.isoformat() if acquired else None,
            'sold_date': sold.isoformat(),
            'proceeds': round(proceeds, 2),
            'basis': round(basis, 2),
            'gain': round(gain, 2),
            'hold_days': hold_days,
            'term': term,
            'estimated': estimated,
        }
