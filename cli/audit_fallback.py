import argparse
import json
import sys
from pathlib import Path


def scan_decisions(root: Path):
    records = []
    for path in root.rglob('decision.json'):
        try:
            with open(path, 'r') as f:
                d = json.load(f)
            records.append({
                'job_id': d.get('job_id') or path.parent.name,
                'industry': d.get('industry') or 'unknown',
                'status': d.get('status') or ('PASS' if d.get('pass') else 'FAIL'),
                'fallback_used': bool(d.get('flags', {}).get('fallback_used', False)),
                'reasons_joined': '; '.join(d.get('reasons', [])),
                'created_at': (path.parent / 'meta.json').read_text() if (path.parent / 'meta.json').exists() else '',
                'path': str(path)
            })
        except Exception:
            continue
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='storage', help='Root directory to scan')
    ap.add_argument('--json', action='store_true', help='Output JSON instead of CSV')
    args = ap.parse_args()

    records = scan_decisions(Path(args.root))

    risky = []
    for r in records:
        if r['industry'] in ['autoclave', 'sterile', 'concrete'] and r['status'] == 'PASS' and r['fallback_used']:
            risky.append(r)
        if r['status'] == 'INDETERMINATE':
            risky.append(r)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print('job_id,industry,status,fallback_used,reasons_joined,path')
        for r in records:
            print(f"{r['job_id']},{r['industry']},{r['status']},{r['fallback_used']},\"{r['reasons_joined']}\",{r['path']}")

    sys.exit(1 if risky else 0)


if __name__ == '__main__':
    main()

