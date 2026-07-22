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
