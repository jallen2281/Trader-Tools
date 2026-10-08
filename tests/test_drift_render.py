"""What the bill-drift card actually renders, run under node.

The Python suite proves _bill_drift finds the right bills. It cannot see whether the card
turns a finding into a sentence a person can act on, and that is the half that matters
here: the whole point of the card is that someone reads "declared day 7, actually pays day
1" and fixes it. A row that renders as "[object Object]" would pass every Python test.

Extracts renderDrift and driftIssue from the template and runs them against the shape the
endpoint really returns.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.getcwd())

if not shutil.which('node'):
    print('SKIP: node is not installed, cannot render the template JS')
    raise SystemExit(0)

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


TPL = os.path.join(os.getcwd(), 'templates', 'finances.html')
src = io.open(TPL, encoding='utf-8').read()
start = src.index("    const DRIFT_LABEL = {")
end = src.index("    /* Writes only the fields")
render_fn = src[start:end]


def render(payload):
    """Run renderDrift over `payload`; return (html, visible text, card display)."""
    harness = (
        "const fmt=n=>'$'+Math.round(n).toLocaleString();\n"
        "const fmt2=n=>'$'+Number(n).toFixed(2);\n"
        "const esc=x=>String(x);\n"
        "const els={};\n"
        "function el(id){ if(!els[id]) els[id]={_h:'',_t:'',style:{display:''},\n"
        "  set innerHTML(v){this._h=v;}, get innerHTML(){return this._h;},\n"
        "  set textContent(v){this._t=v;}, get textContent(){return this._t;}};\n"
        "  return els[id]; }\n"
        "const document={getElementById:el};\n"
        + render_fn +
        "\nrenderDrift(" + json.dumps(payload) + ");\n"
        "const html=els['driftBody']?els['driftBody']._h:'';\n"
        "const text=html.replace(/<[^>]+>/g,' ').replace(/&[a-z]+;/g,' ')"
        ".replace(/\\s+/g,' ').trim();\n"
        "console.log(JSON.stringify({html, text,"
        " display: els['driftCard'] ? els['driftCard'].style.display : null,"
        " count: els['driftCount'] ? els['driftCount']._t : ''}));\n"
    )
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(harness)
        path = f.name
    try:
        proc = subprocess.run([shutil.which('node'), path], capture_output=True,
                              text=True, timeout=60)
    finally:
        os.unlink(path)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit('renderDrift did not run')
    return json.loads(proc.stdout.strip().splitlines()[-1])


# The real mortgage finding, as the endpoint returns it.
PAYLOAD = {
    'checked': 21,
    'drifted': [
        {'bill_id': 12, 'name': 'Mortgage', 'payee': 'United Wholesale',
         'merchant': 'United Wholesale Mortgage', 'occurrences': 5,
         'last_seen': '2026-10-01',
         'issues': [{'kind': 'due_day', 'configured': 7, 'actual': 1, 'delta': 6}],
         'suggested': {'due_day': 1, 'next_due_date': '2026-11-01'}},
        {'bill_id': 20, 'name': 'Electric', 'payee': 'DTE Energy',
         'merchant': 'DTE Energy', 'occurrences': 4, 'last_seen': '2026-10-05',
         'issues': [{'kind': 'amount', 'configured': 421.99, 'actual': 521.20,
                     'delta': 99.21, 'annual_impact': 1190.52}],
         'suggested': {'amount': 521.20}},
    ],
}

r = render(PAYLOAD)
print('--- the card appears and says how much drifted ---')
check('the card is shown', r['display'] == '', r['display'])
check('it counts the drifted against the checked', '2 of 21 bills' in r['count'], r['count'])

print('\n--- a due-day drift reads as a sentence ---')
check('the bill is named', 'Mortgage' in r['text'], r['text'][:160])
check('the declared day is shown', 'declared day 7' in r['text'], r['text'][:200])
check('alongside the real one', 'actually pays day 1' in r['text'], r['text'][:200])
check('with how far out it is', '6 days out' in r['text'], r['text'][:200])
check('and it is labelled a due-day problem', 'due day' in r['text'], r['text'][:200])

print('\n--- an amount drift shows both figures and the yearly cost ---')
check('the declared amount', '$421.99' in r['text'], r['text'])
check('the actual amount', '$521.20' in r['text'], r['text'])
check('the annual impact', '1,191' in r['text'] or '1,190' in r['text'], r['text'])
check('labelled an amount problem', 'amount' in r['text'], r['text'])

print('\n--- nothing renders as a raw object ---')
check('no [object Object]', '[object Object]' not in r['html'], r['html'][:200])
check('no undefined leaked in', 'undefined' not in r['text'], r['text'])

print('\n--- the fix button carries the suggestion ---')
check('it offers to use the actual values', 'use actual' in r['text'], r['text'])
check('the mortgage button passes its suggested day',
      '"due_day":1' in r['html'] or '&quot;due_day&quot;:1' in r['html'], r['html'][:400])
check('and the bill id', 'applyDrift(12' in r['html'], r['html'][:400])

print('\n--- a clean set of bills hides the card entirely ---')
clean = render({'checked': 21, 'drifted': []})
check('hidden when nothing drifted', clean['display'] == 'none', clean['display'])
check('and it renders nothing', clean['text'] == '', clean['text'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL DRIFT RENDER CHECKS PASSED')
