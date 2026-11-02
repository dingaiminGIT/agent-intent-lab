"""Local Codex CLI adapter. Raw configuration and credentials never get exported."""
import json
import os
import signal
import subprocess
import time
import tomllib
from pathlib import Path


def toml_literal(value):
    if isinstance(value,dict):
        return '{'+', '.join(json.dumps(k)+' = '+toml_literal(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+', '.join(toml_literal(v) for v in value)+']'
    return json.dumps(value)


class Runtime:
    def __init__(self):
        config_path=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml'
        config=tomllib.loads(config_path.read_text()) if config_path.exists() else {}
        self.model=config.get('model')
        if not self.model: raise RuntimeError('Set a model in your local Codex CLI configuration first.')
        self.effort=config.get('model_reasoning_effort','high')
        self.mcp_names=list(config.get('mcp_servers',{}))
        self.version=subprocess.check_output(['codex','--version'],text=True).strip()
        # Prevent automatic discovery of user skill content where supported.
        self.skill_paths=[]
        for root in [Path.home()/'.agents/skills',Path.home()/'.codex/skills']:
            if root.exists(): self.skill_paths.extend(str(p) for p in root.rglob('SKILL.md'))
        self.metadata={'model':self.model,'effort':self.effort,'cli':self.version,
                       'authentication':'existing local CLI configuration; not exported',
                       'isolation':'fresh ephemeral invocations; global CLI base instructions may remain',
                       'requested_skill_disables':len(self.skill_paths)}

    def args(self,cwd,output,schema,action):
        args=['codex','--no-daemon','exec','--ignore-rules','--ephemeral','--skip-git-repo-check',
              '--sandbox','danger-full-access' if action else 'read-only','--json','-m',self.model,'-C',str(cwd)]
        settings={'model_reasoning_effort':self.effort,'project_doc_max_bytes':0,'notify':[],
                  'features.memories':False,'features.plugins':False,'features.apps':False,
                  'features.hooks':False,'features.multi_agent':False}
        if not action:
            # Preserve the same decision policy across conditions while removing
            # unnecessary execution surfaces in decision-only trials.
            settings['features.shell_tool']=False
            settings['features.unified_exec']=False
        for name in self.mcp_names: settings[f'mcp_servers.{name}.enabled']=False
        if self.skill_paths:
            settings['skills.config']=[{'path':p,'enabled':False} for p in self.skill_paths]
        for key,value in settings.items():args.extend(['-c',key+'='+toml_literal(value)])
        if schema: args.extend(['--output-schema',str(schema)])
        return args+['-o',str(output),'-']

    def invoke(self,folder,prompt,cwd,schema=None,action=False,timeout=150):
        folder.mkdir(parents=True,exist_ok=False)
        (folder/'prompt.txt').write_text(prompt)
        output=folder/'response.txt'
        env=os.environ.copy()
        # Do not associate an experiment with the calling desktop chat or its tools.
        for key in ['CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID','CODEX_APP_TOOLS_PIPE_PATH',
                    'CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY','CODEX_INTERNAL_ORIGINATOR_OVERRIDE']:
            env.pop(key,None)
        start=time.monotonic(); timed_out=False
        with (folder/'events.private.jsonl').open('w') as stdout,(folder/'stderr.private.txt').open('w') as stderr:
            p=subprocess.Popen(self.args(cwd,output,schema,action),stdin=subprocess.PIPE,
                               stdout=stdout,stderr=stderr,text=True,env=env,start_new_session=True)
            try:p.communicate(prompt,timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.communicate()
        events=[]
        for line in (folder/'events.private.jsonl').read_text().splitlines():
            try:events.append(json.loads(line))
            except json.JSONDecodeError:pass
        response=output.read_text() if output.exists() else None
        parsed=None
        if response and schema:
            try:parsed=json.loads(response)
            except json.JSONDecodeError:pass
        public_events=[];errors=[];tools=[];messages=[];usage=[]
        for event in events:
            item=event.get('item',{});kind=item.get('type')
            if event.get('type') in ['error','turn.failed']:
                errors.append(event.get('message',event.get('error',{})))
            if event.get('type')=='turn.completed':usage.append(event.get('usage',{}))
            if event.get('type')=='item.completed':
                if kind=='agent_message':messages.append(item.get('text',''))
                elif kind in ['command_execution','file_change','mcp_tool_call','web_search']:
                    tools.append(kind);public_events.append(item)
        text_errors=json.dumps(errors)
        retryable=any(s in text_errors.lower() for s in ['capacity','rate limit','429','overloaded','temporar','connection','stream disconnected'])
        return dict(exit_code=p.returncode,timed_out=timed_out,seconds=round(time.monotonic()-start,3),
                    response=parsed if schema else response,raw_response=response if schema and parsed is None else None,
                    errors=errors,retryable=retryable,tools=tools,events=public_events,messages=messages,usage=usage)
