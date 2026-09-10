"""What the account-link dropdown actually offers, run under node.

The failure this exists for: a Plaid investment account was given ONLY the portfolio pool,
so a brokerage tracked as an ordinary FinanceAccount — "Sofi Robo" — was absent from its own
dropdown and could not be linked at all. Nothing errored; the option simply was not there.

No Python test could see this. The pools are all returned correctly by the API; the mistake
was in which one the template chose.
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
start = src.index('    const CASH_TYPES =')
end = src.index('    async function linkPlaidAccount(')
fn = src[start:end]

# Drawn from the real account set.
LINKABLE = {
    'debts': [{'id': 20, 'name': 'Prime visa'}, {'id': 21, 'name': 'Citi Card'},
              {'id': 1, 'name': 'Amex'}],
    'accounts': [
        {'id': 1, 'name': 'Sofi Checking', 'type': 'checking'},
        {'id': 4, 'name': 'Sofi Savings', 'type': 'savings'},
        {'id': 5, 'name': 'Sofi Robo', 'type': 'brokerage'},
        {'id': 6, 'name': 'Sofi Rollover IRA', 'type': 'retirement'},
        {'id': 7, 'name': 'Sofi Crypto', 'type': 'other'},
        {'id': 2, 'name': 'Home', 'type': 'property'},
        {'id': 9, 'name': 'Airstream Trailer', 'type': 'vehicle'},
    ],
    'portfolios': [{'id': 1, 'name': 'Robinhood'}, {'id': 2, 'name': 'Sofi'},
                   {'id': 3, 'name': 'Transamerica 401k'}],
}


def options(acct, selected=''):
    harness = ("const esc=x=>String(x);\n" + fn +
               "\nconsole.log(JSON.stringify(linkOptions(%s, %s, %s)));\n"
               % (json.dumps(acct), json.dumps(LINKABLE), json.dumps(selected)))
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(harness)
        path = f.name
    try:
        out = subprocess.run([shutil.which('node'), path], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        if out.returncode != 0:
            raise AssertionError('node failed: %s' % (out.stderr or '')[-400:])
        return json.loads(out.stdout.strip().split('\n')[-1])
    finally:
        os.unlink(path)


def values(html):
    return re.findall(r'<option value="([^"]*)"', html)


def groups(html):
    return re.findall(r'<optgroup label="([^"]*)"', html)


print('\n--- an investment account can reach BOTH ways of tracking one ---')
h = options({'is_credit': False, 'is_investment': True})
v = values(h)
check('the brokerage FinanceAccount is offered', 'account:5' in v, v)
check('so is the retirement one', 'account:6' in v, v)
check('and the portfolio account too', 'portfolio:2' in v, v)
check('investment options come first', groups(h)[0] == 'Investment accounts', groups(h))
check('the portfolio group says it is compared, not overwritten',
      'compared, not overwritten' in h, h[:300])
check('cash accounts are still reachable, just not first',
      'account:1' in v and groups(h).index('Cash accounts') > 0, groups(h))

print('\n--- and they are grouped, not mixed in with checking and savings ---')
check('several groups exist', len(groups(h)) >= 3, groups(h))
inv_block = h.split('<optgroup label="Investment accounts">')[1].split('</optgroup>')[0]
check('the brokerage is inside the investment group, not the cash one',
      'account:5' in values(inv_block), inv_block)
cash_block = h.split('<optgroup label="Cash accounts">')[1].split('</optgroup>')[0]
check('and the checking account is not in the investment group',
      'account:1' in values(cash_block) and 'account:1' not in values(inv_block))

print('\n--- a depository account leads with cash ---')
h2 = options({'is_credit': False, 'is_investment': False})
check('cash first', groups(h2)[0] == 'Cash accounts', groups(h2))
check('but a brokerage is still selectable if that is what it is',
      'account:5' in values(h2), values(h2))
check('no portfolio options, which cannot hold a checking account',
      not any(x.startswith('portfolio:') for x in values(h2)), values(h2))

print('\n--- a credit card only ever offers debts ---')
h3 = options({'is_credit': True, 'is_investment': False})
v3 = values(h3)
check('debts are offered', 'debt:20' in v3, v3)
check('and nothing else', all(x.startswith('debt:') for x in v3), v3)

print('\n--- the value carries the kind, since ids collide across pools ---')
check('account 1 and debt 1 are distinguishable',
      'account:1' in values(h2) and 'debt:1' in v3,
      (values(h2)[:3], v3))
check('selection round-trips', 'value="account:5" selected' in
      options({'is_credit': False, 'is_investment': True}, 'account:5'))
check('and selecting a portfolio does not also select the account with the same id',
      'value="account:2" selected' not in
      options({'is_credit': False, 'is_investment': True}, 'portfolio:2'))

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL LINK OPTION CHECKS PASSED')
