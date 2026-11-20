"""Tiny deterministic pipeline; no network, PHP, or LLM account needed."""
import json
import os
import sys
import zipfile
from pathlib import Path

ARTIFACTS = {
    'intake':'intake.md', 'plan':'plan.md', 'design':'design.md',
    'research':'research.md', 'implement':'implementation.md',
    'test':'test_report.md', 'integrate':'integration_report.md', 'deliver':'delivery.md',
}


def main():
    stage = sys.argv[1]
    run = Path(os.environ['FORGE_RUN_DIR'])
    target = Path(os.environ['FORGE_STAGE_DIR'])
    target.mkdir(parents=True, exist_ok=True)
    if stage == 'implement':
        (target/'result.json').write_text(json.dumps({'message':'Hello from OmniForge', 'items':[1,2,3]}), encoding='utf-8')
    if stage in ('test', 'integrate', 'deliver'):
        result = json.loads((run/'implement'/'result.json').read_text(encoding='utf-8'))
        if result != {'message':'Hello from OmniForge', 'items':[1,2,3]}:
            raise ValueError('Demo output did not match acceptance criteria')
    if stage == 'deliver':
        with zipfile.ZipFile(target/'demo-bundle.zip', 'w') as bundle:
            bundle.write(run/'implement'/'result.json', 'result.json')
    (target/ARTIFACTS[stage]).write_text(
        f'# Demo: {stage}\n\nDeterministic demo stage completed.\n\n'
        'This illustrates workflow mechanics; it does not generate software with an LLM.\n', encoding='utf-8')
    print(f'Demo {stage} completed')


if __name__ == '__main__':
    main()
