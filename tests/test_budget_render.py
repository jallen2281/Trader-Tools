"""What the Budget card actually renders, run under node.

Every other suite checks the template SOURCE — that a handler is wired, that an id exists.
None of them can see what the JS produces, and that gap let a real regression ship: bills in
a category with no limit were demoted from full rows to small chips, so $1,761/mo of real
obligations stopped being visible on a card whose whole job is showing where money goes.
The rollup was returning them correctly the entire time, so no Python test could have caught
it.

This extracts renderBudgets from the template, runs it under node against the rollup shape
the API really returns, and asserts on the rendered text.
"""
import io
import json
import os
import re
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
start = src.index('    function renderBudgets(rows) {')
end = src.index('    function renderCashflow(c) {')
render_fn = src[start:end]


def render(rows):
    """Run renderBudgets over `rows` and return (html, visible_text)."""
    harness = (
        "const fmt=n=>'$'+Math.round(n).toLocaleString();\n"
        "const fmt2=n=>'$'+Number(n).toFixed(2);\n"
        "const esc=x=>String(x);\n"
        "const jsq=v=>String(v);\n"
        "let _html='';\n"
        "const document={getElementById:()=>({set innerHTML(v){_html=v;},"
        "get innerHTML(){return _html;}})};\n"
        + render_fn +
        "\nrenderBudgets(" + json.dumps(rows) + ");\n"
        "const text=_html.replace(/<[^>]+>/g,' ').replace(/&[a-z]+;/g,' ')"
        ".replace(/\\s+/g,' ').trim();\n"
        "console.log(JSON.stringify({html:_html, text}));\n"
    )
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(harness)
        path = f.name
    try:
        out = subprocess.run([shutil.which('node'), path], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        if out.returncode != 0:
            raise AssertionError('node failed: %s' % (out.stderr or '')[-400:])
        d = json.loads(out.stdout.strip().split('\n')[-1])
        return d['html'], d['text']
    finally:
        os.unlink(path)


def row(cat, rid=None, limit=0, committed=0.0, actual=0.0, over=False):
    return {'category': cat, 'id': rid, 'monthly_limit': limit,
            'committed_monthly': committed, 'actual_monthly': actual,
            'projected_monthly': max(committed, actual), 'over': over, 'kind': 'expense'}


print('\n--- a bill with no budget limit is still visible, with its amount ---')
# The real shape from production: a mortgage under a limit, plus debt and utilities bills
# that no limit covers.
html, text = render([
    row('housing', rid=6, limit=3110, committed=3107.0),
    row('debt', committed=1163.97),
    row('utilities', committed=597.37),
])
for cat in ('housing', 'debt', 'utilities'):
    check('%s appears' % cat, cat in text, text[:200])
check('the unbudgeted debt bills show their amount', '$1,164' in text, text)
check('and the utilities bills show theirs', '$597' in text, text)
check('the group is totalled so the size is obvious', '$1,761' in text, text)
check('each offers a way to set a limit', text.count('set a limit') == 2, text)

print('\n--- limits and no-limits are distinguishable, not identical ---')
check('the budgeted row shows spend against its limit', '$3,107 / $3,110' in text, text)
check('a no-limit row is NOT drawn as a full bar (nothing to be a % of)',
      '(100%)' not in text.split('No limit set')[-1],
      text.split('No limit set')[-1][:200])
check('only the budgeted row offers removal', text.count('remove limit') == 1, text)
check('the two groups are separated', 'budgetTracked' in html)

print('\n--- with no limits set at all, the bills are still the main content ---')
html2, text2 = render([row('debt', committed=1163.97), row('utilities', committed=597.37)])
check('both still render', 'debt' in text2 and 'utilities' in text2, text2)
check('amounts still shown', '$1,164' in text2 and '$597' in text2, text2)
check('no empty budgeted section is drawn', 'remove limit' not in text2, text2)

print('\n--- a budgeted category with nothing in it still shows its limit ---')
_, text3 = render([row('food', rid=3, limit=600)])
check('it is not hidden just because nothing was spent', 'food' in text3, text3)
check('and the limit is stated', '$600' in text3, text3)

print('\n--- over budget is called out ---')
_, text4 = render([row('food', rid=3, limit=400, actual=555.0, over=True)])
check('marked over', 'over' in text4, text4)
check('showing actual against limit', '$555 / $400' in text4, text4)

print('\n--- nothing at all ---')
_, text5 = render([])
check('says so rather than rendering an empty card', 'No budget set' in text5, text5)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BUDGET RENDER CHECKS PASSED')
