"""Helm chart wiring.

Not a rendering test — helm already validates syntax, and the cluster validates schema.
This checks the thing neither of those can see: that a secret the chart NAMES is actually
mounted somewhere.

That gap is not hypothetical. trader-tools-doc-key was created on the cluster, held the
right key under the right name, and was never referenced by the deployment — so the app
refused every document upload with "DOC_ENCRYPTION_KEY is not configured" while the secret
sat there looking correct. Nothing failed; uploads were simply declined, and the reason was
two files apart.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.getcwd())

try:
    import yaml
except ImportError:                                   # pragma: no cover
    print('SKIP: PyYAML not installed')
    raise SystemExit(0)

CHART = os.path.join(os.getcwd(), 'helm', 'trader-tools')
TEMPLATES = os.path.join(CHART, 'templates')
fails = []


def check(label, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(label)


values = yaml.safe_load(io.open(os.path.join(CHART, 'values.yaml'), encoding='utf-8'))

template_text = {}
for name in sorted(os.listdir(TEMPLATES)):
    if name.endswith(('.yaml', '.yml', '.tpl')):
        template_text[name] = io.open(os.path.join(TEMPLATES, name), encoding='utf-8').read()
all_templates = '\n'.join(template_text.values())


def secret_paths(node, prefix=''):
    """Every values key naming a Secret or ConfigMap, as its dotted .Values path."""
    for key, val in (node or {}).items():
        path = '%s%s' % (prefix, key)
        if isinstance(val, dict):
            for p in secret_paths(val, path + '.'):
                yield p
        elif isinstance(val, str) and re.search(r'(Secret|ConfigMap)$', key):
            yield path, val


print('\n--- every secret the chart names is actually mounted ---')
named = list(secret_paths(values))
check('the chart names some secrets at all', len(named) >= 4, named)
for path, value in named:
    # A name is useless unless a template dereferences it; grep for the .Values path.
    check('%s (%s) is referenced by a template' % (path, value),
          ('.Values.%s' % path) in all_templates,
          'nothing under templates/ mentions .Values.%s' % path)

print('\n--- the keys that protect data at rest reach the web pods ---')
dep = template_text.get('deployment.yaml', '')
# envFrom is what actually puts these in the process environment. A secretRef elsewhere in
# the file (a volume, another workload) would not.
env_block = dep.split('envFrom:', 1)[1].split('volumeMounts:', 1)[0] if 'envFrom:' in dep else ''
for label, path in (('document encryption key', 'docKeySecret'),
                    ('Plaid credentials', 'plaidKeysSecret'),
                    ('AI provider keys', 'aiKeysSecret')):
    check('%s are in the deployment envFrom' % label,
          ('.Values.%s' % path) in env_block,
          env_block[:200] or 'no envFrom block found')

print('\n--- optional vs required is a deliberate choice, not an accident ---')
# Each externally-managed secret is optional so an absent one degrades a feature instead of
# refusing to start the pod. The app refuses the specific action and says why.
for path in ('docKeySecret', 'plaidKeysSecret', 'aiKeysSecret'):
    idx = env_block.find('.Values.%s' % path)
    tail = env_block[idx:idx + 200] if idx >= 0 else ''
    check('%s is mounted optional' % path, 'optional: true' in tail, tail[:120])

print('\n--- everything the Dockerfile copies in still exists ---')
# The build is the last place you want to discover a deleted file. Moving backup.sh into
# the chart broke `COPY backup.sh ./` and the image failed to build for three commits
# before anyone looked at the Actions tab — while ArgoCD happily kept deploying chart
# changes, so the cluster looked healthy and the application code silently stopped shipping.
dockerfile = os.path.join(os.getcwd(), 'Dockerfile')
if os.path.exists(dockerfile):
    for line in io.open(dockerfile, encoding='utf-8'):
        line = line.strip()
        if not line.upper().startswith(('COPY ', 'ADD ')):
            continue
        parts = [p for p in line.split()[1:] if not p.startswith('--')]
        if len(parts) < 2 or any(p.startswith('/') for p in parts[:-1]):
            continue          # multi-stage COPY --from, or an absolute source
        for src in parts[:-1]:
            if any(ch in src for ch in '*?['):
                import glob as _glob
                check('Dockerfile copies %s, which matches something' % src,
                      bool(_glob.glob(src)), src)
            else:
                check('Dockerfile copies %s, which exists' % src,
                      os.path.exists(os.path.join(os.getcwd(), src)), src)

print('\n--- every script a workload is told to run is actually in the image ---')
# The same class of bug as the doc-key secret above, one layer out: a CronJob whose command
# names a script that the Dockerfile never copies renders fine, deploys fine, and fails
# only when the schedule fires -- at 03:30, into a Job history nobody is watching.
cmd_scripts = set()
for name, text in template_text.items():
    for script in re.findall(r'command:\s*\[\s*"python"\s*,\s*"([^"]+\.py)"\s*\]', text):
        cmd_scripts.add((name, script))
check('some workload runs a python script', bool(cmd_scripts), sorted(cmd_scripts))
for name, script in sorted(cmd_scripts):
    check('%s runs %s, which exists at the repo root' % (name, script),
          os.path.exists(os.path.join(os.getcwd(), script)), script)
    # And is reachable by the Dockerfile's copy rules, which is a separate question from
    # existing: a script in a subdirectory would exist and still not be in the image.
    check('%s is shipped by the Dockerfile' % script, os.sep not in script and '/' not in script,
          'nested paths are not covered by `COPY *.py ./`')

print('\n--- the scheduled sync is wired for the failure cases, not just the happy one ---')
sync = template_text.get('plaid-sync-cronjob.yaml', '')
check('the plaid-sync CronJob exists', bool(sync))
if sync:
    check('it is gated on its own values block', '.Values.plaidSync.enabled' in sync)
    # Plaid bills per request and the cursor is stateful, so two overlapping runs would
    # walk the same pages twice and pay for it.
    check('overlapping runs are forbidden, not replaced',
          'concurrencyPolicy: Forbid' in sync)
    # A quietly failing sync leaves the stale ledger this job exists to prevent.
    check('failed runs are kept long enough to notice',
          re.search(r'failedJobsHistoryLimit:\s*([5-9]|\d{2,})', sync) is not None)
    check('a wedged run cannot retry forever', 'activeDeadlineSeconds' in sync)
    # Unlike retention, which can do its real work without Plaid, a sync with no
    # credentials has nothing to do at all -- so this secretRef must NOT be optional.
    idx = sync.find('.Values.plaidKeysSecret')
    tail = sync[idx:idx + 160] if idx >= 0 else ''
    check('Plaid credentials are required, not optional', idx >= 0 and 'optional' not in tail,
          tail[:120])
    # Importing app.py starts the alert monitor, so a cron pod would duplicate every
    # notification the web pods fire for as long as it lives.
    check('the job does not become a second alert source',
          'TT_BACKGROUND_JOBS' in sync and '"0"' in sync, sync[:0] or 'flag missing')
    check('and the app honours that flag',
          "TT_BACKGROUND_JOBS" in io.open(os.path.join(os.getcwd(), 'app.py'),
                                          encoding='utf-8').read())

print('\n--- files referenced by templates exist ---')
for name, text in template_text.items():
    for rel in sorted(set(re.findall(r'\.Files\.Get\s+"([^"]+)"', text))):
        check('%s reads %s, which exists' % (name, rel),
              os.path.exists(os.path.join(CHART, rel)),
              os.path.join(CHART, rel))

print('\n--- the backup script is the sh one the alpine image can run ---')
script = os.path.join(CHART, 'files', 'backup.sh')
if os.path.exists(script):
    body = io.open(script, encoding='utf-8').read()
    check('shebang is /bin/sh, not bash', body.startswith('#!/bin/sh'), body.split('\n')[0])
    # `set -euo pipefail` aborts immediately under ash, which is what /bin/sh is in the
    # alpine image — that is exactly how the repo-root copy of this script drifted into
    # something that could never have run in the container. A guarded
    # `set -o pipefail 2>/dev/null || true` is the portable form and is fine.
    pipefail = [l.strip() for l in body.split('\n') if 'pipefail' in l]
    check('no unguarded bash-only pipefail',
          all(('|| true' in l or '2>/dev/null' in l) for l in pipefail), pipefail)
    check('pipefail is attempted at all, so a failing pg_dump fails the job',
          bool(pipefail), 'no pipefail line')
    check('it still encrypts when a key is present', 'openssl enc -aes-256-cbc' in body)

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d):' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('ALL CHART CHECKS PASSED')
