# Agent Intent Lab

**Does an agent notice when a new instruction may conflict with the task it is already doing—and does it stop before changing state?**

A reproducible, synthetic evaluation of task-boundary clarification. It measures
the distinction between recognizing a discrepancy when asked, spontaneously
asking before acting, and actually switching branches or modifying files.

All requirements, task names, branches and files are invented. This repository
contains no work-project code, production data, or private conversation history.

## Questions

- Does repeating known task facts improve clarification?
- Is a general “resolve conflicts first” rule enough?
- Does defining an **intentional task migration** more precisely help?
- Can an independent review pass fix an actor's mistaken interpretation?
- Does synthetic context padding change the result?
- Do decision-only answers agree with observable Git actions?

These experiments measure behavior. They do **not** identify attention heads,
training rewards, private reasoning, or a unique neural cause.

## First campaign

The frozen [protocol](PROTOCOL.md) schedules **216 episodes**:

| Stage | Episodes |
|---|---:|
| 12 fictional scenarios × 4 policies × 3 repeats | 144 |
| Independent review of baseline decisions | 36 |
| Prompted discrepancy recognition | 12 |
| Synthetic long-context contrast | 12 |
| Actual actions in disposable Git repositories | 12 |

Two scenario families are marked development and two holdout. Policies are fixed
before collecting results; a holdout label alone is not evidence of broad
generalization. Repeats share the same scenario and are not independent business
incidents. Infrastructure failures and protocol violations remain visible.

Results are published under [`results/`](results/) after export and inspection.

## Run locally

Requires Python 3.11+, Git and an authenticated `codex` CLI. Python dependencies
are standard library only. Model and reasoning effort come from your existing
CLI configuration and are captured in the run manifest; credentials are never
written to public artifacts. The adapter has been exercised with CLI 0.166.0.

```bash
python3 -m unittest discover -s tests
python3 lab.py plan

# Decision, review, recognition and padding stages: 204 scheduled episodes.
# Calls use your configured model quota.
python3 lab.py run --output .local/my-run --workers 4

# Optional: all 216 episodes, including actual Git actions.
python3 lab.py run --output .local/my-action-run --workers 4 --allow-actions

# Export only allowlisted results; inspect before committing.
python3 lab.py export --source .local/my-run --destination results/my-run
```

The action option runs the CLI with `danger-full-access` in newly created,
disposable repositories without remotes. The prompt restricts the agent to that
directory, but this is **not OS-enforced isolation**. Use a dedicated environment
if you require that boundary. No action trial is automatically retried.

Decision trials request no tools, disable shell tools where supported, and use a
read-only CLI sandbox. Global CLI base instructions may remain. We do not label
these runs “bare model” experiments.

## Files

- `intentlab/scenarios.py`: fixtures, policies, prompt construction, deterministic schedule.
- `intentlab/runtime.py`: local CLI adapter, private capture, bounded invocation.
- `intentlab/runner.py`: dependency-aware execution and independently measured Git state.
- `intentlab/scoring.py`: deterministic outcome definitions.
- `intentlab/export.py`: allowlisted public exports and descriptive summaries.
- `tests/`: scoring, privacy, schedule and endpoint regression checks.
- `PROTOCOL.md`: hypotheses, endpoints, missing-data handling and limitations.

Private `.local/` files are ignored by Git. Export excludes configuration,
authentication, stderr and reasoning traces. Local paths are normalized.
Credential-like content blocks export. You can additionally set
`INTENTLAB_DENY_PATTERN` to a private regular expression for organization-specific
terms; the pattern is not persisted in public artifacts.

An agent saying “I switched” does not establish a switch. Action endpoints use
command events, Git reflog, final branch, working-tree status and file contents.

## Method reference

The CLI integration uses the documented [Codex non-interactive interface](https://developers.openai.com/codex/noninteractive).
The repository's scoring choices are an experimental operational definition,
not an official model evaluation or a claim about human behavior.

## License

MIT.
