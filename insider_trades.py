"""
Insider (SEC Form 4) cluster-buy tracker.

Real data from OpenInsider's "latest cluster buys" feed — clusters where multiple
corporate insiders (CEOs/CFOs/directors) bought their own company's stock on the
open market in a tight window. This is the strongest, best-documented signal in the
platform's toolkit, so it powers the "Pro Traders" tab.

No API key. Cached, and degrades gracefully (returns []) if the source is
unreachable so the caller can fall back.
"""

import re
import html as _html
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

OPENINSIDER_URL = "http://openinsider.com/latest-cluster-buys"


class InsiderTradeTracker:
    """Fetch + parse recent insider cluster buys."""

    def __init__(self):
        self.cache = None
        self.last_update = None
        self.cache_ttl = timedelta(hours=6)

    def get_cluster_buys(self, limit=30):
        """Return recent insider cluster buys (list of dicts), cached for cache_ttl."""
        if (self.cache is not None and self.last_update
                and (datetime.now() - self.last_update) < self.cache_ttl):
            return self.cache[:limit]
        rows = self._fetch()
        if rows:
            self.cache = rows
            self.last_update = datetime.now()
        return (self.cache or [])[:limit]

    @staticmethod
    def _strip(cell):
        # OpenInsider wraps some cells in tooltip spans; drop those, then all tags.
        cell = re.sub(r".*onmouseout=\"UnTip\(\)\">", "", cell)
        cell = re.sub(r"<[^>]+>", "", cell)
        return _html.unescape(cell).replace("\xa0", " ").strip()

    def _to_int(self, s):
        try:
            return int(re.sub(r"[^0-9]", "", s) or 0)
        except Exception:
            return 0

    def _fetch(self):
        """Fetch + parse the OpenInsider cluster-buys table. Returns [] on any failure."""
        try:
            resp = requests.get(
                OPENINSIDER_URL, timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; trader-tools/1.0)"})
            if resp.status_code != 200:
                logger.warning(f"OpenInsider HTTP {resp.status_code}")
                return []
            text = resp.text
            m = re.search(r"<table[^>]*tinytable[\s\S]*?</table>", text)
            segment = m.group(0) if m else text
            rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", segment)
            out = []
            for r in rows[1:]:
                cells = [self._strip(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", r)]
                if len(cells) < 13:
                    continue
                # Columns: X, FilingDate, TradeDate, Ticker, Company, Industry, Ins,
                #          TradeType, Price, Qty, Owned, dOwn, Value, 1d, 1w, 1m, 6m
                ticker = cells[3].upper().strip()
                if not ticker:
                    continue
                out.append({
                    "filing_date": cells[1][:10],
                    "trade_date": cells[2][:10],
                    "ticker": ticker,
                    "company": cells[4],
                    "industry": cells[5],
                    "num_insiders": self._to_int(cells[6]),
                    "trade_type": cells[7],
                    "price": cells[8],
                    "value": cells[12],
                })
            logger.info(f"OpenInsider: parsed {len(out)} insider cluster buys")
            return out
        except Exception as e:
            logger.warning(f"OpenInsider fetch failed: {e}")
            return []


# Lazily-created shared singleton (its own ~6h cache).
_insider_tracker = None


def get_insider_tracker():
    global _insider_tracker
    if _insider_tracker is None:
        _insider_tracker = InsiderTradeTracker()
    return _insider_tracker
