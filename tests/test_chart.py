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
