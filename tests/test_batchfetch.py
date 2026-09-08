"""Batched market-data fetching.

No network: yf.download is stubbed, so what is actually under test is the shape handling
(yfinance returns three different column layouts), the cache path, the fallback, and — the
point of the change — that N symbols cost ONE rate-limited request rather than N.
"""
import os
import sys
import tempfile

os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(), 'b.db').replace(os.sep, '/')
sys.path.insert(0, os.getcwd())

import pandas as pd            # noqa: E402
import data_fetcher as DF      # noqa: E402

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def frame(closes):
    idx = pd.date_range('2026-09-01', periods=len(closes))
    return pd.DataFrame({'Open': closes, 'High': closes, 'Low': closes,
                         'Close': closes, 'Volume': [100] * len(closes)}, index=idx)


def ticker_first(symbols):
    """group_by='ticker': columns are (TICKER, field)."""
    parts = {s: frame([10.0 + i, 11.0 + i, 12.0 + i]) for i, s in enumerate(symbols)}
    return pd.concat(parts, axis=1)


def field_first(symbols):
    """The other layout seen in the wild: (field, TICKER)."""
    return ticker_first(symbols).swaplevel(0, 1, axis=1).sort_index(axis=1)


print('\n--- column-shape handling ---')
req = {'AAPL': 'AAPL', 'MSFT': 'MSFT'}
out = DF.FinancialDataFetcher._split_batch_frame(ticker_first(['AAPL', 'MSFT']), req)
check('ticker-first MultiIndex splits per symbol', sorted(out) == ['AAPL', 'MSFT'], sorted(out))
check('and keeps the Close column', 'Close' in out['AAPL'].columns, list(out['AAPL'].columns))
check('with the right values', float(out['MSFT']['Close'].iloc[0]) == 11.0,
      float(out['MSFT']['Close'].iloc[0]))

out = DF.FinancialDataFetcher._split_batch_frame(field_first(['AAPL', 'MSFT']), req)
check('field-first MultiIndex also splits', sorted(out) == ['AAPL', 'MSFT'], sorted(out))

out = DF.FinancialDataFetcher._split_batch_frame(frame([5.0, 6.0]), {'TSLA': 'TSLA'})
check('a flat single-symbol frame is handled', list(out) == ['TSLA'], list(out))

check('an empty frame yields nothing',
      DF.FinancialDataFetcher._split_batch_frame(pd.DataFrame(), req) == {})
check('None yields nothing', DF.FinancialDataFetcher._split_batch_frame(None, req) == {})

print('\n--- one request for many symbols ---')
calls = {'download': 0, 'rate_limited': 0, 'single': 0}
SYMS = ['AAPL', 'MSFT', 'NVDA', 'AMD']


def fake_download(tickers, **kw):
    calls['download'] += 1
    calls['last_tickers'] = list(tickers) if isinstance(tickers, (list, tuple)) else [tickers]
    return ticker_first(calls['last_tickers'])


DF.yf.download = fake_download
_orig_rl = DF._rate_limited_request
DF._rate_limited_request = lambda: calls.__setitem__('rate_limited', calls['rate_limited'] + 1)

f = DF.FinancialDataFetcher()
f._cache = {} if hasattr(f, '_cache') else getattr(f, '_cache', {})
res = f.fetch_multiple_symbols(SYMS, period='5d')
check('all four symbols returned', sorted(res) == sorted(SYMS), sorted(res))
check('exactly ONE download call for four symbols', calls['download'] == 1, calls['download'])
check('exactly ONE rate-limit wait (was one per symbol)', calls['rate_limited'] == 1,
      calls['rate_limited'])
check('derived Returns column added', 'Returns' in res['AAPL'].columns, list(res['AAPL'].columns))
check('and Cumulative_Returns', 'Cumulative_Returns' in res['AAPL'].columns)

print('\n--- the cache means a repeat costs nothing ---')
before = dict(calls)
res2 = f.fetch_multiple_symbols(SYMS, period='5d')
check('same symbols returned', sorted(res2) == sorted(SYMS))
check('no second download', calls['download'] == before['download'], calls['download'])
check('no second rate-limit wait', calls['rate_limited'] == before['rate_limited'])

print('\n--- a failing batch falls back per symbol rather than returning nothing ---')
def boom(*a, **k):
    calls['download'] += 1
    raise RuntimeError('yahoo said no')


DF.yf.download = boom
single_calls = []
f.fetch_stock_data = lambda sym, period='6mo', interval='1d', **k: (
    single_calls.append(sym) or frame([1.0, 2.0]))
res3 = f.fetch_multiple_symbols(['XYZ', 'ABC'], period='1mo')
check('still returns both symbols', sorted(res3) == ['ABC', 'XYZ'], sorted(res3))
check('by falling back to the per-symbol path', sorted(single_calls) == ['ABC', 'XYZ'],
      single_calls)

print('\n--- yfinance is allowed to parallelise its own requests ---')
seen = {}


def capture_download(tickers, **kw):
    seen.update(kw)
    calls['download'] += 1
    return ticker_first(list(tickers))


DF.yf.download = capture_download
f2 = DF.FinancialDataFetcher()
f2.fetch_multiple_symbols(['A', 'B', 'C'], period='5d')
check('threads is NOT disabled (serial-inside-download was the 3-minute regression)',
      seen.get('threads') is True, seen.get('threads'))
check('grouped by ticker for a clean split', seen.get('group_by') == 'ticker',
      seen.get('group_by'))

print('\n--- a dead batch cannot cost minutes: the fallback is time-bounded ---')
DF.yf.download = boom
slow = DF.FinancialDataFetcher()
slow.fallback_budget_seconds = 0          # budget already exhausted
slow_calls = []
slow.fetch_stock_data = lambda sym, period='6mo', interval='1d', **k: (
    slow_calls.append(sym) or frame([1.0, 2.0]))
res5 = slow.fetch_multiple_symbols(['P', 'Q', 'R', 'S'], period='1mo')
check('gives up instead of paying the per-symbol toll for every one',
      len(slow_calls) <= 1, slow_calls)
check('and returns partial data rather than hanging', isinstance(res5, dict), type(res5))

generous = DF.FinancialDataFetcher()
generous.fallback_budget_seconds = 999
gen_calls = []
generous.fetch_stock_data = lambda sym, period='6mo', interval='1d', **k: (
    gen_calls.append(sym) or frame([1.0, 2.0]))
res6 = generous.fetch_multiple_symbols(['P', 'Q'], period='1mo')
check('with budget available it still falls back for everything',
      sorted(gen_calls) == ['P', 'Q'], gen_calls)
check('and returns them all', sorted(res6) == ['P', 'Q'], sorted(res6))

print('\n--- a single symbol skips the batch entirely ---')
single_calls.clear()
before_dl = calls['download']
res4 = f.fetch_multiple_symbols(['ONE'], period='1mo')
check('one symbol uses the per-symbol path', single_calls == ['ONE'], single_calls)
check('and issues no batch download', calls['download'] == before_dl, calls['download'])

check('empty input is a no-op', f.fetch_multiple_symbols([], period='5d') == {})

DF._rate_limited_request = _orig_rl

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for x in fails:
        print('  - ' + x)
    sys.exit(1)
print('ALL BATCH FETCH CHECKS PASSED')
