"""What the Books table actually renders, run under node.

The Python suites prove the API returns actual, projected and a pace verdict. None of them
can see which of those numbers reaches the screen or what it gets captioned, and that is
the whole risk here: the figures are only an improvement if a measured total is never
labelled as a forecast, and if a book with a young bank feed is never captioned as behind.
Getting that wrong would reintroduce the original complaint in a new place.

So this extracts renderEntities from the template, runs it under node against the shapes
_entity_report really returns, and asserts on the rendered text.
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
start = src.index('    function renderEntities(rep) {')
end = src.index('    function openEntity(e) {')
render_fn = src[start:end]


def helper(decl):
    """Lift a helper's real definition out of the template.

    Hand-written stand-ins are worse than no test: the first draft of this file declared
    fmt as '$' + Math.round(n), which renders a loss as "$-2,266" where the page renders
    "-$2,266". Every assertion about a negative number was then checking the harness
    instead of the product. So the helpers come from the template itself and cannot drift
    from what ships.
    """
    i = src.index('    const %s = ' % decl)
    return src[i:src.index('\n', i)].strip()


def render(rep):
    harness = (
        '\n'.join(helper(d) for d in ('fmt', 'fmt2', 'esc', 'attrJson')) + '\n'
        "let _html='';\n"
        "const document={getElementById:()=>({set innerHTML(v){_html=v;},"
        "get innerHTML(){return _html;}})};\n"
        + render_fn +
        "\nrenderEntities(" + json.dumps(rep) + ");\n"
        "const text=_html.replace(/<[^>]+>/g,' ').replace(/&middot;/g,'.')"
        ".replace(/&mdash;/g,'-').replace(/&[a-z]+;/g,' ').replace(/\\s+/g,' ').trim();\n"
        "console.log(JSON.stringify({html:_html, text}));\n"
    )
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(harness)
        path = f.name
    try:
        out = subprocess.run([shutil.which('node'), path], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        if out.returncode != 0:
            raise AssertionError('node failed: %s' % (out.stderr or '')[-500:])
        d = json.loads(out.stdout.strip().split('\n')[-1])
        return d['html'], d['text']
    finally:
        os.unlink(path)


def body(text):
    """Just the table rows -- the legend below them explains what "vs pace" means, so a
    naive search for that phrase matches the explanation on every single render."""
    return text.split('The bold figure on each line')[0]


def pace(**kw):
    p = {'actual': 0.0, 'projected': 0.0, 'measured': 0.0, 'planned_projected': 0.0,
         'expected_to_date': 0.0, 'actual_to_date': 0.0, 'variance': 0.0,
         'variance_pct': None, 'comparable': False, 'measured_from': None,
         'partial_history': False, 'sources_unmeasured': [], 'days_elapsed': 303,
         'days_in_year': 365, 'fraction_elapsed': 0.8301,
         'expected_basis': 'gross', 'planned_net_projected': 0.0,
         'records_through': None, 'stale_periods': 0.0, 'records_stale': False}
    p.update(kw)
    return p


def book(name, form=None, eid=1, income=0.0, actual=0.0, expenses=0.0, annualized=None,
         deductible=0.0, miles=0, mileage=0.0, **kw):
    return {'entity': {'id': eid, 'name': name, 'kind': 'farm', 'tax_form': form},
            'year': 2026, 'income': income, 'income_projected': income,
            'income_actual': actual, 'income_pace': pace(actual=actual, projected=income, **kw),
            'expenses': expenses, 'expenses_annualized': annualized,
            'net': round(income - expenses, 2), 'net_actual': round(actual - expenses, 2),
            'net_projected': (round(income - annualized, 2) if annualized is not None else None),
            'deductible_receipts': deductible, 'mileage_miles': miles,
            'mileage_deduction': mileage, 'receipts_on_file': 0, 'transactions': 0,
            'by_category': [], 'assets': 0.0, 'debts': 0.0, 'tax_form': form}


print('--- a figure annualized from its own receipts is never captioned as a forecast ---')
# Chicken Tales: the projection IS the trailing receipts, so there is nothing to be behind.
html, text = render({'year': 2026, 'entities': [
    book('Chicken Tales LLC', form='Schedule F', income=49.50, actual=49.50,
         expenses=2315.35, annualized=2788.42, deductible=89.97,
         measured=49.50, planned_projected=0.0, comparable=False)]})
check('the book is listed', 'Chicken Tales LLC' in text, text[:200])
check('it says the figure is measured', 'measured, not forecast' in text, text)
check('and offers no pace verdict', 'vs pace' not in body(text), body(text))
check('the actual income is the figure shown', '$50' in text, text)
check('a real Schedule F loss is rendered negative',
      'neg' in html and '-$2,266' in text, text)

print('\n--- a book running on a projection gets the comparison, with its sign ---')
html, text = render({'year': 2026, 'entities': [
    book('Personal finance', eid=2, income=153605.16, actual=118400.00,
         expenses=128300.88, annualized=154559.00,
         measured=0.0, planned_projected=153605.16, comparable=True,
         expected_to_date=49200.00, actual_to_date=42269.63,
         variance=-6930.37, variance_pct=-14.1,
         expected_basis='net', planned_net_projected=112000.00)]})
check('the projection is shown as a projection', 'proj $153,605' in text, text)
check('the shortfall is shown against pace', '-$6,930' in text, text)
check('with its percentage', '(-14.1%)' in text, text)
check('and the basis is named, so take-home is not read as gross pay',
      'vs take-home pace' in text, text)
check('the take-home projection is spelled out',
      '$112,000 projected take-home' in text, text)
check('with what was banked against what was due by now',
      '$42,270 banked of $49,200 expected by now' in text, text)
check('and drawn as negative', 'neg' in html, html[:400])
check('the actual income leads the cell', '$118,400' in text, text)
check('expenses carry where they land at this rate',
      '$154,559' in text and 'at this rate' in text, text)

print('\n--- being ahead of pace reads as ahead, not as a bare number ---')
html, text = render({'year': 2026, 'entities': [
    book('Side gig', eid=3, income=20000.00, actual=18000.00, expenses=1000.00,
         annualized=1204.00, measured=0.0, planned_projected=20000.00, comparable=True,
         expected_to_date=16600.00, actual_to_date=18000.00,
         variance=1400.00, variance_pct=8.4, expected_basis='gross')]})
check('the surplus is signed', '+$1,400' in text, text)
check('and its percentage signed too', '(+8.4%)' in text, text)
check('and drawn as positive', 'pos' in html, html[:400])
check('a gross-basis row is not captioned take-home', 'take-home' not in body(text), body(text))

print('\n--- a young bank feed says so instead of looking like a collapse ---')
html, text = render({'year': 2026, 'entities': [
    book('Second job', eid=4, income=48000.00, actual=4000.00, expenses=0.0,
         annualized=0.0, measured=0.0, planned_projected=48000.00, comparable=True,
         expected_to_date=5917.81, actual_to_date=4000.00, variance=-1917.81,
         variance_pct=-32.4, partial_history=True, measured_from='2026-09-16',
         records_through='2026-10-15', stale_periods=1.0,
         expected_basis='net', planned_net_projected=36000.00)]})
check('both ends of the measured span are named',
      'measured 2026-09-16 to 2026-10-15' in text, text)
check('and explained', 'the span the records cover' in body(text), body(text))
check('a single period of lag is not called stale',
      'no income recorded' not in text, text)
check('the variance is the fortnight, not the year', '-$1,918' in text, text)
check('and $44,000 of phantom shortfall is nowhere on the page',
      '-$44,000' not in text and '$44,000' not in text, text)

print('\n--- nothing banked yet is reported as missing data, not as a shortfall ---')
html, text = render({'year': 2026, 'entities': [
    book('Commissions (estimated)', eid=5, income=5000.00, actual=0.0, expenses=0.0,
         measured=0.0, planned_projected=5000.00, comparable=False,
         sources_unmeasured=['Commissions (estimated)'])]})
check('it says there is nothing to measure yet',
      'no income records to measure yet' in text, text)
check('it offers no verdict', 'vs pace' not in body(text), body(text))
check('but still shows the projection', 'proj $5,000' in text, text)

print('\n--- the table explains which number is which ---')
html, text = render({'year': 2026, 'entities': [
    book('Chicken Tales LLC', form='Schedule F', income=49.50, actual=49.50,
         expenses=2315.35, annualized=2788.42, measured=49.50, comparable=False)]})
check('the income column is labelled actual and projected',
      'actual . projected' in text, text)
check('the expense column says it is annualized', 'actual . annualized' in text, text)
check('the legend explains what pace is measured against',
      'the same span the records cover' in text, text)
check('and why a measured figure has no verdict',
      'no forecast there to be ahead or behind of' in text, text)
check('and that a deposit is take-home rather than gross pay',
      'A bank deposit is take-home, not gross pay' in text, text)

print('\n--- an unassigned bucket still renders, and a missing pace block is survivable ---')
bare = book('Unassigned', eid=None, expenses=12.00)
bare.pop('income_pace')
bare.pop('income_actual')
bare.pop('expenses_annualized')
bare.pop('net_actual')
bare.pop('net_projected')
html, text = render({'year': 2026, 'entities': [book('Chicken Tales LLC', income=1.0)],
                     'unassigned': bare})
check('the unassigned row appears', 'Unassigned' in text, text)
check('explained as untagged', 'records not assigned to any books' in text, text)
check('and a row with no pace data does not break the render', '$12' in text, text)

print('\n--- income that stops being recorded is called out on the row ---')
# The window closes at the last record so a part-period cannot read as a deficit. The risk
# that introduces is the opposite one, and it has to surface somewhere.
html, text = render({'year': 2026, 'entities': [
    book('Job that went quiet', eid=7, income=48000.00, actual=4000.00, expenses=0.0,
         measured=0.0, planned_projected=48000.00, comparable=True,
         expected_to_date=4100.00, actual_to_date=4000.00, variance=-100.00,
         variance_pct=-2.4, expected_basis='gross', measured_from='2026-01-29',
         records_through='2026-02-27', stale_periods=16.2, records_stale=True)]})
check('the silence is stated in pay periods',
      'no income recorded for about 16 pay periods' in text, text)
check('and drawn as a problem', 'neg' in html, html[:600])
check('while the variance itself stays small and honest', '-$100' in text, text)
check('and the date the records stop is shown', '2026-02-27' in text, text)

print('\n--- one stale period is worded in the singular ---')
html, text = render({'year': 2026, 'entities': [
    book('Barely late', eid=8, income=12000.00, actual=900.00, comparable=True,
         planned_projected=12000.00, expected_to_date=950.00, actual_to_date=900.00,
         variance=-50.00, measured_from='2026-01-01', records_through='2026-09-20',
         stale_periods=1.9, records_stale=True)]})
check('it reads "1 pay period", not "1 pay periods"',
      'about 1 pay period<' in html, [x for x in html.split('<br>') if 'pay period' in x])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL BOOKS RENDER CHECKS PASSED')
