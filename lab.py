#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from intentlab.scenarios import manifest

def main():
    p=argparse.ArgumentParser(description='Synthetic task-boundary evaluation')
    sub=p.add_subparsers(dest='command',required=True)
    plan=sub.add_parser('plan');plan.add_argument('--repeats',type=int,default=3)
    run=sub.add_parser('run');run.add_argument('--output',required=True);run.add_argument('--repeats',type=int,default=3);run.add_argument('--workers',type=int,default=4);run.add_argument('--allow-actions',action='store_true')
    export=sub.add_parser('export');export.add_argument('--source',required=True);export.add_argument('--destination',required=True)
    a=p.parse_args()
    if a.command=='plan':
        jobs=manifest(a.repeats);print(json.dumps({'episodes':len(jobs),'stages':{s:sum(j['stage']==s for j in jobs) for s in sorted({j['stage'] for j in jobs})}},indent=2))
    elif a.command=='run':
        from intentlab.runner import run
        run(a.output,a.repeats,a.workers,a.allow_actions)
    else:
        from intentlab.export import export
        print(export(a.source,a.destination))

if __name__=='__main__':main()
