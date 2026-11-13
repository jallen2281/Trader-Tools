"""Which control a broken Plaid connection offers, run under node.

This is the bug that caused a genuine mess rather than a theoretical one. The row tested
`status === 'login_required'` and offered "reconnect" only then; every other failure, and
every healthy connection, got "sync" and nothing else. So when SoFi needed wider consent
-- a healthy connection, just not authorised for liabilities -- the only visible route was
"+ Connect a bank", which makes a SECOND connection. That duplicated 48 transactions,
double-counted $31,785.34 of assets, and ended with the original connection dead.

The opposite error matters just as much. Once SoFi returned ITEM_NOT_FOUND, offering
"reconnect" would have been a button that cannot work: update mode repairs an Item that
still exists, and that one is gone from Plaid entirely. An action that cannot succeed is
no better than no action at all.

So the row asks the server what the user can DO -- PlaidItem.recovery, decided from
Plaid's error_code, which is now actually stored. No Python test could cover this: the API
returned the right data all along and the template chose the wrong control.
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
start = src.index('    function plaidItemsHtml(items) {')
end = src.index('    async function relinkPlaid(')
fn = src[start:end]


def row(item):
    harness = ("const esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
               + fn + "\nconsole.log(JSON.stringify(plaidItemsHtml(%s)));\n"
               % json.dumps([item]))
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(harness)
        path = f.name
    try:
        out = subprocess.run([shutil.which('node'), path], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        if out.returncode != 0:
            raise AssertionError('node failed: %s' % (out.stderr or '')[-500:])
        return json.loads(out.stdout.strip().split('\n')[-1])
    finally:
        os.unlink(path)


def buttons(html):
    return re.findall(r'onclick="(\w+)\(', html)


def labels(html):
    return [t.strip() for t in re.findall(r'<button[^>]*>([^<]*)</button>', html)]


BASE = {'id': 2, 'institution_name': 'SoFi', 'last_synced_at': '2026-11-12T21:48',
        'status': 'active', 'last_error': None, 'last_error_code': None, 'recovery': None}


def item(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


print('\n--- a HEALTHY connection can be re-authorized, which is the whole point ---')
h = row(item())
check('it shows active', 'active' in h and 'neg' not in h.split('<td>')[2], h[:200])
check('sync is offered', 'syncPlaid' in buttons(h), buttons(h))
check('AND re-authorize, so a product can be added without a new connection',
      'connectPlaid' in buttons(h), buttons(h))
check('it says what re-authorize is for',
      'new products' in h and 'Keeps this connection' in h, h[-600:])
check('it does NOT offer reconnect, because nothing is broken',
      'reconnect' not in labels(h), labels(h))

print('\n--- needs re-authentication: update mode, which keeps the history ---')
h = row(item(status='login_required', recovery='reconnect',
             last_error_code='ITEM_LOGIN_REQUIRED', last_error='the user must log in again'))
check('reconnect is offered', 'reconnect' in labels(h), labels(h))
check('it goes to update mode on THIS item',
      'connectPlaid(2)' in h, [b for b in h.split('onclick="')[1:] if 'Plaid' in b][:2])
check('it promises the history survives', 'Keeps its history' in h, h[-500:])
check('no sync button competing with the fix', 'syncPlaid' not in buttons(h), buttons(h))
check('the error text is shown', 'log in again' in h)

print('\n--- consent missing on a working connection is ALSO update mode ---')
h = row(item(status='error', recovery='reconnect',
             last_error_code='ADDITIONAL_CONSENT_REQUIRED'))
check('reconnect, not a new connection', 'reconnect' in labels(h), labels(h))
check('and it is connectPlaid with the id', 'connectPlaid(2)' in h)

print('\n--- A DEAD ITEM MUST NOT OFFER A BUTTON THAT CANNOT WORK ---')
h = row(item(status='error', recovery='relink', last_error_code='ITEM_NOT_FOUND',
             last_error='The Item you requested cannot be found.'))
check('it does NOT call connectPlaid with the item id -- update mode has nothing to repair',
      'connectPlaid(2)' not in h, h)
check('it routes to the new-connection path instead',
      'relinkPlaid' in buttons(h), buttons(h))
check('and says so in the label', 'reconnect (new)' in labels(h), labels(h))
check('the title explains why', 'no longer exists at Plaid' in h, h[-700:])

print('\n--- an outage is nobody\'s problem: no misleading button ---')
h = row(item(status='error', recovery=None, last_error_code='INSTITUTION_DOWN',
             last_error='the institution is down'))
check('no reconnect offered', 'reconnect' not in labels(h), labels(h))
check('no relink offered', 'relinkPlaid' not in buttons(h), buttons(h))
check('just sync, which is what retrying is', 'syncPlaid' in buttons(h), buttons(h))
check('and no re-authorize either, since the connection is not healthy',
      'connectPlaid' not in buttons(h), buttons(h))
check('the reason is still shown', 'institution is down' in h)

print('\n--- disconnect is always available, and always the dangerous one ---')
for kw in ({}, {'status': 'error', 'recovery': 'relink'},
           {'status': 'login_required', 'recovery': 'reconnect'}):
    h = row(item(**kw))
    check('disconnect present for %s' % (kw.get('status', 'active')),
          'disconnectPlaid' in buttons(h), buttons(h))
    check('  and marked danger', 'link-btn danger' in h)

print('\n--- the institution name is escaped, not interpolated raw ---')
h = row(item(institution_name='Bank & <script>'))
check('ampersand escaped', '&amp;' in h, h[:300])
check('no raw script tag', '<script>' not in h, h[:300])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL PLAID ROW CHECKS PASSED')
