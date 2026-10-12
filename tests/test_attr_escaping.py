"""JSON embedded in a single-quoted HTML attribute must have its apostrophes escaped.

The reported bug: the edit button on the debt "Tricia's ASU Bachelors degree" did nothing.
The row renders as

    onclick='openDebt({"name":"Tricia's ASU Bachelors degree", ...})'

and the apostrophe in "Tricia's" ends the attribute three characters in. Everything after
it becomes stray markup, the handler is malformed, and the click is silently ignored. The
same row template was used for bills, so "Tricia's Truck" was broken too.

A helper that escapes this already existed and was used by the transactions and mileage
tables. Six other call sites did not use it.

This checks the helper does its job, and — more usefully — that no call site anywhere in
the template has gone back to raw JSON.stringify inside a single-quoted attribute. That
second check is the one that stops this returning: the bug is invisible until someone
happens to own a record with an apostrophe in its name.
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

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


TPL = os.path.join(os.getcwd(), 'templates', 'finances.html')
src = io.open(TPL, encoding='utf-8').read()

print('--- no call site embeds raw JSON in a single-quoted attribute ---')
# onclick='...${JSON.stringify(x)}...'  — the exact shape that breaks.
raw = re.findall(r"onclick='[^']*\$\{JSON\.stringify\([^']*'", src)
check('no raw JSON.stringify inside onclick=\'...\'', not raw,
      [r[:90] for r in raw])

# The safe helper should be what those sites use instead.
check('the escaping helper exists',
      "const attrJson" in src and ".replace(/'/g,'&#39;')" in src)
uses = len(re.findall(r"\$\{attrJson\(", src))
check('and is used by every record-carrying handler', uses >= 7, uses)

print('\n--- the helper actually neutralises an apostrophe ---')
if not shutil.which('node'):
    print('SKIP: node is not installed, cannot exercise the helper')
else:
    m = re.search(r"( *const attrJson = .*?;)\n", src)
    assert m, 'attrJson declaration not found'
    harness = (
        "const esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
        ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;');\n"
        + m.group(1) + "\n"
        "const rec = " + json.dumps({
            'id': 9, 'name': "Tricia's ASU Bachelors degree",
            'payee': "O'Reilly & Sons <test>", 'apr': 0.0}) + ";\n"
        "const attr = attrJson(rec);\n"
        "console.log(JSON.stringify({attr}));\n"
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
        print(proc.stderr)
        raise SystemExit('the helper did not run')
    attr = json.loads(proc.stdout.strip().splitlines()[-1])['attr']

    check("no bare apostrophe survives", "'" not in attr, attr[:120])
    check('it is escaped as an entity', '&#39;' in attr, attr[:120])
    check('angle brackets are escaped too', '<' not in attr and '>' not in attr, attr[:160])
    check('double quotes are escaped', '"' not in attr, attr[:160])
    # The whole point: the attribute it builds has exactly one opening and closing quote.
    full = "onclick='openDebt(%s)'" % attr
    check('the finished attribute has exactly two quote characters',
          full.count("'") == 2, full[:160])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL ATTRIBUTE ESCAPING CHECKS PASSED')
