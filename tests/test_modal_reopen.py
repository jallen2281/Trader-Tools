"""A modal must reopen after it is dismissed by clicking the backdrop.

The reported bug: open a holding on the portfolio page, click off the modal instead of the
X, and no holding detail would open again until the page was reloaded.

Two scripts attach a backdrop handler to the same element. The page shows modals with an
`active` class (CSS turns it into display:flex), while app.js closed them by setting an
inline display:none -- and an inline style outranks a class, so every later
classList.add('active') was overruled for the life of the page.

This runs BOTH real handlers, extracted from the shipped files, against a fake element that
models the same rule the browser applies: an inline display wins over the class.
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
    print('SKIP: node is not installed, cannot run the modal handlers')
    raise SystemExit(0)

fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


def fn_source(path, name):
    """The whole of a top-level `function name() { ... }` from a shipped file."""
    src = io.open(path, encoding='utf-8').read()
    start = src.index('function %s(' % name)
    end = src.index('\n}\n', start) + len('\n}\n')
    return src[start:end]


APP = os.path.join(os.getcwd(), 'static', 'app.js')
PORT = os.path.join(os.getcwd(), 'static', 'portfolio.js')
pieces = [fn_source(APP, '_closeModalEl'), fn_source(APP, 'initializeModals'),
          fn_source(PORT, 'showModalEl'), fn_source(PORT, 'hideModalEl'),
          fn_source(PORT, 'setupModalCloseHandlers'), fn_source(PORT, 'closeModalById'),
          fn_source(PORT, 'closeHoldingModal')]

HARNESS = r"""
// A fake element that models the browser rule the bug turned on: an inline display beats
// the stylesheet, so `.modal.active { display:flex }` cannot show an element whose inline
// display is 'none'.
function makeModal(id) {
    const classes = new Set(['modal']);
    const handlers = [];
    const el = {
        id,
        style: {display: ''},
        classList: {
            add: c => classes.add(c),
            remove: c => classes.delete(c),
            contains: c => classes.has(c),
        },
        addEventListener: (type, h) => { if (type === 'click') handlers.push(h); },
        click: () => handlers.forEach(h => h({target: el})),   // a click on the backdrop
        visible: () => classes.has('active') && el.style.display !== 'none',
    };
    el.closest = () => el;
    return el;
}

const MODALS = {holdingModal: makeModal('holdingModal'),
                addPositionModal: makeModal('addPositionModal'),
                createAlertModal: makeModal('createAlertModal')};
const keydown = [];
const document = {
    getElementById: id => MODALS[id] || null,
    querySelectorAll: sel => sel === '.modal' ? Object.values(MODALS) : [],
    addEventListener: (t, h) => { if (t === 'keydown') keydown.push(h); },
};
function stopPriceChart() { stopped++; }
function closeAddPositionModal() { hideModalEl('addPositionModal'); }
function closeCreateAlertModal() { hideModalEl('createAlertModal'); }
const window = {};
let stopped = 0;
"""

TAIL = r"""
// Both scripts load on the portfolio page, and both bind the backdrop.
setupModalCloseHandlers();
initializeModals();

const out = {};
const m = MODALS.holdingModal;
showModalEl('holdingModal');
out.opened = m.visible();
m.click();                       // click off, rather than the X
out.closed_by_backdrop = !m.visible();
out.chart_stopped = stopped > 0;
out.no_inline_none = m.style.display !== 'none';   // app.js must not wedge it shut
showModalEl('holdingModal');
out.reopens = m.visible();       // the bug: this stayed false until a page reload
m.click();
showModalEl('holdingModal');
out.reopens_again = m.visible();

// the X still works, and still allows reopening
closeHoldingModal();
out.closed_by_x = !m.visible();
showModalEl('holdingModal');
out.reopens_after_x = m.visible();

// the other two modals on the page behave the same way
const a = MODALS.addPositionModal;
showModalEl('addPositionModal'); a.click(); showModalEl('addPositionModal');
out.add_position_reopens = a.visible();
const c = MODALS.createAlertModal;
showModalEl('createAlertModal'); c.click(); showModalEl('createAlertModal');
out.create_alert_reopens = c.visible();

// a modal that is NOT class-driven keeps the old inline behaviour
const legacy = makeModal('legacy');
legacy.style.display = 'block';
_closeModalEl(legacy);
out.legacy_hidden_inline = legacy.style.display === 'none';

console.log(JSON.stringify(out));
"""

script = HARNESS + '\n'.join(pieces) + TAIL
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(script)
    path = f.name
try:
    proc = subprocess.run([shutil.which('node'), path], capture_output=True, text=True, timeout=60)
finally:
    os.unlink(path)

if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr)
    print('FAILED: the handlers did not run')
    raise SystemExit(1)

r = json.loads(proc.stdout.strip().splitlines()[-1])
print('\n--- clicking off, then opening another holding ---')
check('the modal opens', r['opened'])
check('clicking the backdrop closes it', r['closed_by_backdrop'])
check('and it opens again afterwards', r['reopens'], r)
check('twice over', r['reopens_again'], r)
check('the price chart timer is stopped on a backdrop close', r['chart_stopped'])
check('no inline display is left behind to outrank the class', r['no_inline_none'], r)

print('\n--- the X and the other modals ---')
check('the X still closes', r['closed_by_x'])
check('and still allows reopening', r['reopens_after_x'])
check('Add Position reopens after a click-off', r['add_position_reopens'])
check('Create Alert reopens after a click-off', r['create_alert_reopens'])

print('\n--- modals that are not class-driven are untouched ---')
check('one shown with an inline style is still hidden inline', r['legacy_hidden_inline'])

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL MODAL REOPEN CHECKS PASSED')
