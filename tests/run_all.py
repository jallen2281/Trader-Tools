"""Run every test suite and report a single pass/fail.

Each suite is a standalone script rather than a pytest module, and that is deliberate: they
boot the real Flask application against a throwaway SQLite database, and several of them
manipulate module-level state (stubbing yfinance, swapping the Plaid client, moving
CONSENT_VERSION). Running each in its OWN PROCESS means one suite cannot leak that state
into the next — a shared interpreter would make failures depend on ordering, which is the
worst kind of flaky.

    python tests/run_all.py            # everything
    python tests/run_all.py plaid      # only suites matching "plaid"
    python tests/run_all.py -v         # stream each suite's own output

Run from the repository root; the suites import the application from the working directory.
"""
import os
import subprocess
import sys
import time

# The decode side of this was already handled per-suite; this is the encode side. A failing
# suite's captured output contains the application's own log glyphs, which the Windows
# console codec cannot represent — and printing them crashed the runner exactly when its
# output mattered most. Replace rather than switch to UTF-8, so the console keeps its own
# encoding and only the unrepresentable characters degrade.
try:
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Ordered roughly by what they cover: platform first, then features, then integrations.
SUITES = [
    ('chart', 'helm chart wiring: secrets are mounted, not just named'),
    ('schema_sync', 'database migration on an existing schema'),
    ('consent', 'privacy policy, terms, consent gate, landing page'),
    ('ai_gate', 'paid-AI permission gating and the SECRET_KEY guard'),
    ('docsec', 'safe serving of uploaded documents'),
    ('docencrypt', 'document encryption at rest'),
    ('retention', 'retention, purge cascade and Plaid revocation'),
    ('phase4', 'spending ledger, CSV and receipt import, budgets'),
    ('txn_account', 'transactions know which account or card they drew from'),
    ('receipt_match', 'receipts reconciled against the bank feed by card digits'),
    ('taxprofile', 'household tax profile and withholding'),
    ('retirement', 'Roth/traditional split and employer match'),
    ('matchtiers', 'tiered employer match schedules'),
    ('payroll_per_source', 'withholding and retirement per income, not per household'),
    ('paycheck', 'FICA, Section 125 vs post-tax, take-home; pinned to a real stub'),
    ('cashflow_net', 'the ledger projects net pay, not gross'),
    ('recurring', 'recurring-charge detection arithmetic'),
    ('recurring_api', 'recurring charges: decisions, adoption, sharing'),
    ('debtplan', 'payoff simulation: avalanche vs snowball'),
    ('debt_api', 'bill-to-debt link, dedupe, and the payoff endpoints'),
    ('debt_fees', 'itemised debt fees and the effective rate they imply'),
    ('credit', 'credit utilization and score trends'),
    ('credit_api', 'credit limits, score readings and sharing'),
    ('overview', 'whole-picture overview and observations'),
    ('household', 'household sharing boundaries'),
    ('entities', 'separate books per entity'),
    ('farm_categories', 'Schedule F lines on a farm set of books'),
    ('plaid', 'Plaid client, sync and token handling'),
    ('plaid_accounts', 'accounts inside a connection, deposits, income reconciliation'),
    ('batchfetch', 'batched market data fetching'),
    ('ui_render', 'pages render and controls are wired'),
    ('budget_render', 'what the Budget card actually renders (runs under node)'),
    ('link_options', 'what the account-link dropdown offers (runs under node)'),
]


def main():
    args = [a for a in sys.argv[1:]]
    verbose = '-v' in args or '--verbose' in args
    filters = [a for a in args if not a.startswith('-')]

    selected = [(n, d) for n, d in SUITES
                if not filters or any(f.lower() in n.lower() for f in filters)]
    if not selected:
        print('No suite matches %r. Available: %s'
              % (filters, ', '.join(n for n, _ in SUITES)))
        return 2

    print('Running %d suite(s) from %s\n' % (len(selected), ROOT))
    results, started = [], time.time()
    for name, desc in selected:
        path = os.path.join(HERE, 'test_%s.py' % name)
        if not os.path.exists(path):
            print('  %-14s MISSING  (%s)' % (name, path))
            results.append((name, False, 0.0))
            continue
        t0 = time.time()
        # encoding/errors are explicit: the application logs contain characters the
        # Windows locale codec cannot decode, and the default would raise a
        # UnicodeDecodeError while capturing a FAILING suite's output — crashing the
        # runner exactly when its output matters most.
        proc = subprocess.run([sys.executable, path], cwd=ROOT,
                              capture_output=not verbose, text=True,
                              encoding='utf-8', errors='replace')
        took = time.time() - t0
        ok = proc.returncode == 0
        results.append((name, ok, took))
        print('  %-14s %-5s %5.1fs   %s' % (name, 'PASS' if ok else 'FAIL', took, desc))
        if not ok and not verbose:
            # Only the failing suite's output, and only the part that matters.
            out = (proc.stdout or '') + (proc.stderr or '')
            lines = [l for l in out.split('\n') if 'FAIL' in l or 'Error' in l]
            for line in (lines[-15:] if lines else out.split('\n')[-15:]):
                if line.strip():
                    print('        %s' % line)

    failed = [n for n, ok, _ in results if not ok]
    print('\n' + '=' * 62)
    print('%d passed, %d failed in %.1fs'
          % (len(results) - len(failed), len(failed), time.time() - started))
    if failed:
        print('failed: %s' % ', '.join(failed))
        print('re-run one with output:  python tests/run_all.py %s -v' % failed[0])
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
