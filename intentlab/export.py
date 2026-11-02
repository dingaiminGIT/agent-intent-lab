"""Allowlisted, sanitized public artifacts and descriptive reports."""
import json
import os
import hashlib
import re
from collections import Counter
from pathlib import Path

SECRET = re.compile(r'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|Bearer\s+[A-Za-z0-9._~-]{16,}|-----BEGIN .*PRIVATE KEY-----)',re.I)


def clean(value,scratch=''):
    text=json.dumps(value,ensure_ascii=False)
    if SECRET.search(text):raise ValueError('Credential-like content requires manual review; export refused.')
    private_pattern=os.environ.get('INTENTLAB_DENY_PATTERN')
    if private_pattern and re.search(private_pattern,text,re.I):raise ValueError('Non-synthetic project content requires manual review; export refused.')
    if scratch:
        text=text.replace('/private'+scratch,'<SANDBOX>').replace(scratch,'<SANDBOX>')
    text=re.sub(r'/(?:Users|home|private|var/folders|tmp)/[^\s"\\`]+','<LOCAL_PATH>',text)
    return json.loads(text)


def export(source,destination):
    source=Path(source);destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((source/'manifest.json').read_text())
    scratch=(source/'scratch.private.txt').read_text()
    records=json.loads((source/'records.private.json').read_text())
    published=[]
    for record in records:
        public={k:record[k] for k in ['id','stage','fixture','condition','rep','split','kind','family','status','prompt_sha256','response','score','observed','depends_on'] if k in record}
        public['attempts']=[{k:a[k] for k in ['exit_code','timed_out','seconds','errors','tools','events','usage'] if k in a} for a in record['attempts']]
        public=clean(public,scratch);published.append(public)
        prompt_files=sorted((source/'trials'/record['id']).glob('attempt-*/prompt.txt'))
        if prompt_files:
            folder=destination/'prompts';folder.mkdir(exist_ok=True)
            public_prompt=clean(prompt_files[0].read_text(),scratch)
            public['public_prompt_sha256']=hashlib.sha256(public_prompt.encode()).hexdigest()
            (folder/(record['id']+'.txt')).write_text(public_prompt)
    (destination/'manifest.json').write_text(json.dumps(clean(manifest),ensure_ascii=False,indent=2)+'\n')
    (destination/'trials.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(published,key=lambda x:x['id'])))
    report=summary(published,manifest)
    (destination/'REPORT.md').write_text(report)
    # Scan the entire export, including generated reports and prompts.
    for p in destination.rglob('*'):
        if p.is_file():clean(p.read_text())
    return report


def summary(rows,manifest):
    valid=[r for r in rows if r['status']=='valid']
    lines=['# Synthetic intent-boundary experiment results','',
           f"Model identifier: `{manifest['runtime']['model']}`; effort: `{manifest['runtime']['effort']}`; CLI: `{manifest['runtime']['cli']}`.",
           f"Frozen source commit: `{manifest['source_sha']}`.",
           f"Scheduled episodes: {len(rows)}. Status counts: {dict(Counter(r['status'] for r in rows))}.",'',
           'These are repeated synthetic vignettes, not independent real-world incidents. Counts are descriptive; no human comparison or neural-mechanism measurement was performed. Model aliases do not identify immutable backend weights.','',
           '## Main decision trials','',
           '| Split | Condition | Ambiguous: asks / valid | Ambiguous: unclarified transition | Controls: unnecessary asks / valid | All desired outcomes / valid |',
           '|---|---|---:|---:|---:|---:|']
    for split in ['all','development','holdout']:
        for c in ['baseline','reminder','generic','explicit']:
            subset=[r for r in valid if r['stage']=='main' and r['condition']==c and (split=='all' or r['split']==split)]
            a=[r for r in subset if r['kind']=='ambiguous'];b=[r for r in subset if r['kind']!='ambiguous']
            lines.append(f"| {split} | {c} | {sum(r['score']['clarifies'] for r in a)}/{len(a)} | {sum(r['score']['unclarified_transition'] for r in a)} | {sum(r['score']['overclarifies'] for r in b)}/{len(b)} | {sum(r['score']['passes'] for r in subset)}/{len(subset)} |")
    lines.extend(['','## Family-level ambiguous results','','| Family | Condition | Asks / valid |','|---|---|---:|'])
    for family in ['aurora','willow','harbor','cedar']:
        for c in ['baseline','reminder','generic','explicit']:
            a=[r for r in valid if r['stage']=='main' and r['family']==family and r['condition']==c and r['kind']=='ambiguous']
            lines.append(f"| {family} | {c} | {sum(r['score']['clarifies'] for r in a)}/{len(a)} |")
    by_id={r['id']:r for r in rows}
    lines.extend(['','## Independent pre-action review','',
                  'The reviewer sees the original facts and only the proposed action/target, not the actor rationale. It uses the same model identifier. This adds another call; it is not an independent model or a deterministic guard.','',
                  '| Request kind | Reviewed valid pairs | Wrong to desired | Desired to wrong | Desired before | Desired after |','|---|---:|---:|---:|---:|---:|'])
    for kind in ['ambiguous','matching','override']:
        pairs=[(by_id[r['depends_on']],r) for r in valid if r['stage']=='review' and r['kind']==kind and by_id[r['depends_on']]['status']=='valid']
        before=sum(a['score']['passes'] for a,b in pairs);after=sum(b['score']['passes'] for a,b in pairs)
        gain=sum(not a['score']['passes'] and b['score']['passes'] for a,b in pairs)
        loss=sum(a['score']['passes'] and not b['score']['passes'] for a,b in pairs)
        lines.append(f'| {kind} | {len(pairs)} | {gain} | {loss} | {before} | {after} |')
    lines.extend(['','## Synthetic long-context contrast','',
                  '300 unrelated telemetry lines are inserted between the task history and latest request. Compare with baseline replicate 0. This changes text length and distraction together; it does not isolate attention mechanisms.','',
                  '| Request kind | Paired valid | Desired short | Desired padded |','|---|---:|---:|---:|'])
    for kind in ['ambiguous','matching','override']:
        pairs=[]
        for r in valid:
            if r['stage']=='long' and r['kind']==kind:
                base=by_id[f"main__{r['fixture']}__baseline__0"]
                if base['status']=='valid':pairs.append((base,r))
        lines.append(f"| {kind} | {len(pairs)} | {sum(a['score']['passes'] for a,b in pairs)} | {sum(b['score']['passes'] for a,b in pairs)} |")
    probes=[r for r in valid if r['stage']=='probe' and r['kind']=='ambiguous']
    lines.extend(['','## Prompted recognition','',
                  f"Ambiguous fixtures: correct branch extraction {sum(r['score']['identifies_branches'] for r in probes)}/{len(probes)}; flags possible mistake {sum(bool(r['score']['flags_possible_mistake']) for r in probes)}/{len(probes)}.",
                  'These explicitly prompted probes are not evidence of spontaneous intervention.','',
                  '## Actual Git endpoints','',
                  'Actions run in disposable repositories with no remotes. The CLI has unrestricted permissions for these opt-in episodes; directory scope is instructed, not an OS isolation guarantee. State is measured independently of the model narrative.','',
                  '| Condition | Request | Valid | Unclarified mutation | Unchanged endpoint | Complete requested content |','|---|---|---:|---:|---:|---:|'])
    for c in ['baseline','explicit']:
        for kind in ['ambiguous','matching','override']:
            a=[r for r in valid if r['stage']=='action' and r['condition']==c and r['kind']==kind]
            lines.append(f"| {c} | {kind} | {len(a)} | {sum(r['score']['unclarified_mutation'] for r in a)} | {sum(r['score']['unchanged'] for r in a)} | {sum(r['score']['completed_requested_change'] for r in a)} |")
    for r in rows:
        if r['stage']=='action':lines.extend(['',f"### {r['id']}",'',f"Status: {r['status']}",'',str(r.get('response'))])
    status=Counter(r['status'] for r in rows)
    usage=Counter();attempts=0
    for r in rows:
        for a in r['attempts']:
            attempts+=1
            for u in a.get('usage',[]):
                for k,v in u.items():
                    if isinstance(v,int):usage[k]+=v
    lines.extend(['','## Missing data and execution accounting','',
                  f'Actual model attempts: {attempts} (includes retained retries). Status counts: {dict(status)}.',
                  f'Provider-reported usage fields, summed as reported: `{dict(usage)}`. Cached/reasoning fields may be subsets; do not add them again to estimate billing. No pricing inference is made.','',
                  'Tool calls in decision-only episodes are protocol violations. Capacity/network failures can receive one retry with the same prompt. Mutating episodes are never automatically retried. Unknown or failed outcomes are not scored as compliance or clarification.','',
                  '## Limits','',
                  '- Frozen before the campaign; no prompt adjustment based on these results. Two named families are held out from development, but the whole set is synthetic and shares a template.',
                  '- Three repeats do not imply three independent business scenarios. No fixed sampling seed or temperature control is available in this adapter.',
                  '- A task conflict is a predefined evaluation requirement, not proof that a real user was mistaken.',
                  '- JSON decision prompts can prime behavior. Action trials are a different, complementary setting.',
                  '- Global CLI base instructions may remain despite requested configuration isolation. No claim of bare-model measurement.',
                  '- Reviewer and context comparisons are small; no causal claims about training, attention heads, or model internals.',
                  '- Public files exclude credentials, local configuration, private stderr, and reasoning traces. Public action prompts/paths normalize disposable directories.',
                  '- prompt_sha256 hashes the exact executed input; public_prompt_sha256 hashes the exported, path-normalized input. They can differ for action trials.',
                  '- No production or work-project source, requirements, branch names, or private chat history is used.',''])
    return '\n'.join(lines)
