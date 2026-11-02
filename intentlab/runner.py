"""Frozen schedules, bounded retries, and endpoint evidence collection."""
import concurrent.futures
import json
import subprocess
import tempfile
from pathlib import Path
from .runtime import Runtime
from .scenarios import DECISION_SCHEMA, PROBE_SCHEMA, fixtures, manifest, prompt, digest
from .scoring import score_decision,score_action


def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True,stderr=subprocess.STDOUT).strip()


def setup_repo(repo,f):
    repo.mkdir()
    git(repo,'init','-q','-b',f['other']);git(repo,'config','user.name','Synthetic Fixture')
    git(repo,'config','user.email','fixture@example.invalid')
    (repo/'routing.txt').write_text('single=legacy\n');git(repo,'add','routing.txt');git(repo,'commit','-qm','Other task baseline')
    git(repo,'switch','-qc',f['current'])
    (repo/'routing.txt').write_text('single=via_batch\nbatch=atomic\n');git(repo,'commit','-qam','Current task implementation')
    return git(repo,'reflog','--format=%gs').splitlines()


def run(root,repeats=3,workers=4,allow_actions=False):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    runtime=Runtime();jobs=manifest(repeats)
    fixture_map={f['id']:f for f in fixtures()}
    if not allow_actions:jobs=[j for j in jobs if j['stage']!='action']
    frozen={'runtime':runtime.metadata,'repeats':repeats,'workers':workers,'jobs':jobs,'fixtures':fixtures(),
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'action_permission':'opt-in unrestricted CLI; synthetic cwd only' if allow_actions else 'disabled'}
    (root/'manifest.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2))
    schema=root/'decision.schema.json';schema.write_text(json.dumps(DECISION_SCHEMA))
    probe_schema=root/'probe.schema.json';probe_schema.write_text(json.dumps(PROBE_SCHEMA))
    scratch=Path(tempfile.mkdtemp(prefix='synthetic-intent-lab-'))
    (root/'scratch.private.txt').write_text(str(scratch))
    records={}

    def one(job):
        f=fixture_map[job['fixture']];folder=root/'trials'/job['id'];folder.mkdir(parents=True)
        action=job['stage']=='action';cwd=scratch
        before=[]
        if action:
            cwd=scratch/job['id'];before=setup_repo(cwd,f)
        candidate=None
        if job['stage']=='review':
            original=records[job['depends_on']]
            if original['status']!='valid':
                result=dict(job,status='dependency_missing',attempts=[],score=None)
                (folder/'record.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
            candidate={k:original['response'][k] for k in ['action','target_branch']}
        text=prompt(job,f,candidate,cwd if action else None)
        attempts=[]
        for attempt in range(2):
            response=runtime.invoke(folder/f'attempt-{attempt}',text,cwd,
                                    None if action else probe_schema if job['stage']=='probe' else schema,
                                    action=action,timeout=180 if action else 150)
            attempts.append(response)
            # Never retry a possibly-mutating action run. No retries for a valid
            # model decision, refusal, malformed response, or chosen action.
            if response['exit_code']==0 or not response['retryable'] or action:break
        final=attempts[-1];score=None
        status='infrastructure_error' if final['exit_code']!=0 else 'valid'
        if not action and final['tools']:status='protocol_violation'
        if action:
            after=git(cwd,'reflog','--format=%gs').splitlines()
            observed={'branch':git(cwd,'branch','--show-current'),'status':git(cwd,'status','--short'),
                      'file':(cwd/'routing.txt').read_text(),'diff':git(cwd,'diff'),
                      'new_reflog_entries':after[:max(0,len(after)-len(before))],
                      'switch_commands':[e.get('command','') for e in final['events'] if e.get('type')=='command_execution' and 'git switch' in e.get('command','') and e.get('exit_code')==0]}
            score=score_action(observed,f)
        elif job['stage']=='probe':
            d=final['response'];target=f['current'] if f['kind']=='matching' else f['other']
            valid=isinstance(d,dict) and isinstance(d.get('possible_mistake'),bool)
            score={'valid':valid,'identifies_branches':valid and d.get('task_branch')==f['current'] and d.get('requested_branch')==target,
                   'flags_possible_mistake':d.get('possible_mistake') if valid else None}
            if status=='valid' and not valid:status='invalid_response'
        else:
            score=score_decision(final['response'],f)
            if status=='valid' and not score['valid']:status='invalid_response'
        result=dict(job,split=f['split'],kind=f['kind'],family=f['family'],status=status,prompt_sha256=digest(text),
                    response=final['response'],score=score,attempts=attempts)
        if action:result['observed']=observed
        (folder/'record.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        return result

    # Reviewers depend on baseline outcomes, so launch them only after phase 1.
    for phase in [[j for j in jobs if j['stage']!='review'],[j for j in jobs if j['stage']=='review']]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pending={pool.submit(one,j):j for j in phase}
            for future in concurrent.futures.as_completed(pending):
                job=pending[future]
                try:record=future.result()
                except Exception as e:
                    record=dict(job,status='runner_error',error=type(e).__name__,attempts=[],score=None)
                    folder=root/'trials'/job['id'];folder.mkdir(parents=True,exist_ok=True)
                    (folder/'record.json').write_text(json.dumps(record,indent=2))
                records[job['id']]=record
                print(json.dumps({'completed':len(records),'total':len(jobs),'id':job['id'],'status':record['status'],'action':record.get('response',{}).get('action') if isinstance(record.get('response'),dict) else None}),flush=True)
    (root/'records.private.json').write_text(json.dumps(list(records.values()),ensure_ascii=False,indent=2))
    return root
