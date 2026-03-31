---
name: execute
description: Execute approved implementation plans with self-healing verification gates. Runs phased implementations with automated testing and manual checkpoints.
allowed-tools: Bash, Read, Glob, Grep, Agent, Write, Edit, AskUserQuestion, TaskCreate, TaskUpdate, TaskGet, TaskList
---

# Execute Plan

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/load-config.sh"`

You are executing an approved implementation plan from `{artifactsDir}/<project>/implementation-plan.md`. These plans contain phases with specific changes and success criteria (automated gates and manual verification).

## Getting Started

When given a plan path:

- Read the plan completely and check for existing checkmarks (- [x]) and status markers
- Read the original spec.md and research.md from the same {artifactsDir}/ directory if they exist
- Read ALL files mentioned in the plan FULLY (never use limit/offset parameters)
- Create tasks using TaskCreate to track your progress through phases
- Confirm execution scope with the user:

  ```
  I've reviewed the implementation plan. It has [N] phases:

  Phase 1: [Name] - Status: [Not Started/In Progress/Complete]
  Phase 2: [Name] - Status: [Not Started/In Progress/Complete]
  ...

  Execution options:
  a) Single phase: Execute Phase [N] only (pauses for manual verification after this phase)
  b) Multi-phase: Execute all remaining phases (pauses only at the end for batch testing)
  c) Multi-phase: Execute phases [X] through [Y] (pauses only at the end for batch testing)
  ```

If no plan path provided, ask for one.

## Implementation Philosophy

Plans are carefully designed, but reality can be messy. Your job is to:

- Follow the plan's intent while adapting to what you find
- Implement each phase completely before moving to the next
- Think deeply about how pieces fit together in the broader codebase
- Update checkboxes and status markers in the plan as you complete work
- Communicate clearly when reality diverges from the plan

When the plan doesn't match reality:

- STOP and diagnose why the divergence occurred
- Present the mismatch clearly:

  ```
  Issue in Phase [N] - Section [X]:

  Expected: [what the plan says]
  Found: [actual situation in codebase]
  Why this matters: [impact on implementation]

  Diagnosis: [your analysis of why this happened]

  Options:
  1. [Adapt the approach because...]
  2. [Update the plan because...]
  3. [Need your guidance on...]

  How should I proceed?
  ```

Wait for guidance before proceeding when there's a significant mismatch.

### Recording Deviations

After the user provides guidance on how to handle a mismatch:

**Document the final decision** using the Edit tool to update the Implementation Deviations section:

```markdown
### Deviation [N]: [Brief descriptive title]

**Phase**: Phase [N] - [Phase Name]
**Section**: [Specific section]

**Original Plan:**

> [Quote exact text from plan]

**What We Actually Did:**

> [The approach we took based on user's decision]

**Reason:**

> [Why we deviated - what we discovered that made the original plan not work]

**Impact:**

> [Brief note on how this affects the implementation]

---
```

Replace `_No deviations recorded yet._` with this entry (or append if deviations already exist).

Also add a callout in the affected phase section:

```markdown
> ⚠️ **Deviation**: See [Deviation [N]](#deviation-n-brief-title)
```

Then continue with execution based on the user's decision.

## Phase Execution with Self-Healing Gates

For each phase, follow this pattern:

### 1. Implementation

**Read the phase thoroughly:**

- Understand what needs to be done
- Check the phase status marker
- Review all changes required
- Note all files that need modification

**Implement systematically:**

- Work through each required change in order
- Read files completely before modifying them
- Make focused, minimal changes aligned with the plan
- Update checkboxes as you complete each file/section:
  ```
  - [x] **File**: [path/to/file.ext](path/to/file.ext)
  ```

**Update the plan as you go:**

- Use the Edit tool to mark completed items: `- [x]`
- Update phase status when starting: `**Status**: [ ] Not Started | [x] In Progress | [ ] Complete`
- Keep your tasks in sync with plan progress using TaskUpdate

### 2. Automated Verification (Self-Healing Loop)

After completing implementation, run all automated gates defined in "Automated Verification (Gates)":

```
Phase [N]: [Phase Name] - Running Automated Gates

Gate 1: [Command or description]
Running: [actual command]
Status: [PASS/FAIL]
Output: [relevant output or error]

Gate 2: [Command or description]
Running: [actual command]
Status: [PASS/FAIL]
Output: [relevant output or error]

...

Summary: [X/Y gates passed]
```

**Self-Healing Protocol:**

If any automated gate fails, enter the self-healing loop:

**Iteration 1:**

```
🔧 Gate Failed: [gate name]

Error Output:
[Full error message]

Root Cause Analysis:
[Your diagnosis of why this failed - what did you miss or get wrong?]

Fix Strategy:
[Specific minimal change needed]

Applying fix...
```

Apply the fix, then re-run ONLY the failed gate.

**Iteration 2 (if still failing):**

```
🔧 Gate Failed Again: [gate name]

Previous fix attempted: [what you tried]
Why it didn't work: [analysis]

New root cause analysis:
[Deeper diagnosis]

Alternative fix strategy:
[Different approach]

Applying fix...
```

**Iteration 3 (if still failing):**

```
🔧 Gate Failed Third Time: [gate name]

Attempt history:
1. [First fix attempt and result]
2. [Second fix attempt and result]
3. [Third fix attempt and result]

This gate requires human debugging.

Relevant context:
- Files involved: [list]
- Error pattern: [description]
- What I've tried: [summary]

Possible causes I couldn't resolve:
- [Hypothesis 1]
- [Hypothesis 2]

Please investigate and advise on next steps.
```

**Stop after 3 failed attempts per gate.** Request human intervention.

**Gate Success:**

```
✅ Gate Passed: [gate name]
```

Continue to next gate or proceed to manual verification if all automated gates pass.

### 3. Manual Verification Checkpoint

**For Single-Phase Execution:**

After ALL automated gates pass, mark them complete in the plan and pause for human verification:

```
Phase [N]: [Phase Name] - Automated Verification Complete ✅

All automated gates passed:
- [x] [Gate 1 description]
- [x] [Gate 2 description]
---

Ready for Manual Verification

The plan specifies these manual checks:
- [ ] [Manual check 1 from plan]
- [ ] [Manual check 2 from plan]

Please perform manual testing now:

1. [Specific thing to verify - quote from plan]
2. [Another specific thing to verify - quote from plan]
3. [Edge case to test - quote from plan]

Reply with one of:
- "manual checks passed" → I'll mark items complete and proceed
- "issue found: [description]" → I'll help debug and fix
```

**For Multi-Phase Execution:**

Skip manual verification until all phases complete their automated gates (see Multi-Phase Execution section).

**Critical: Do NOT mark manual verification items as [x] until the user explicitly confirms.**

**If user reports an issue during manual testing:**

```
Manual Test Failure Reported

Issue: [what user described]

Let me investigate...
[Read relevant files, analyze the issue]

Root cause: [your diagnosis]
Fix: [proposed change]

Should I proceed with this fix?
```

Apply the fix, re-run automated gates, then ask user to re-test manually.

### 4. Phase Completion

Once all gates pass (automated + manual confirmed by user):

**Update the plan file:**

- Mark all manual verification items as `- [x]`
- Update phase status: `**Status**: [ ] Not Started | [ ] In Progress | [x] Complete`
- Update your tasks using TaskUpdate to mark the phase complete

**Report completion:**

```
✅ Phase [N] Complete: [Phase Name]

Automated gates: [X/X] PASSED
Manual verification: CONFIRMED

[If single-phase execution:]
Ready for Phase [N+1]. Continue? (yes/no)

[If multi-phase execution and more phases remain:]
Proceeding to Phase [N+1]...

[If final phase:]
🎉 All phases complete! Ready for self-review.
```

## Multi-Phase Execution

When user chooses multi-phase execution (options b or c):

### Execution Flow

- Execute all phases sequentially (implementation + automated gates for each)
- Run self-healing loop for automated gates (up to 3 attempts)
- Report progress after each phase completes its automated gates
- **Pause for manual verification ONLY after all phases complete**
- If any phase fails gates after 3 attempts, stop immediately and request help

### Progress Reporting

After each phase completes its automated gates:

```
✅ Phase [N] Automated Gates Complete

Implementation: Complete
Automated gates: [X/X] PASSED

Proceeding to Phase [N+1]...
```

### Final Manual Verification (Multi-Phase)

After all phases complete their automated gates, present combined manual verification:

```
All Phases Complete - Ready for Manual Verification

Phase 1: [Phase Name] ✅ (automated gates passed)
Manual verification needed:
- [ ] [Manual check 1 from Phase 1]
- [ ] [Manual check 2 from Phase 1]

Phase 2: [Phase Name] ✅ (automated gates passed)
Manual verification needed:
- [ ] [Manual check 1 from Phase 2]

Phase 3: [Phase Name] ✅ (automated gates passed)
Manual verification needed:
- [ ] [Manual check 1 from Phase 3]
- [ ] [Manual check 2 from Phase 3]

Please test all phases now. For each phase, verify:
1. [Specific instructions from plan]
2. [More instructions]

Reply with:
- "all manual checks passed" → I'll mark everything complete
- "Phase [N] has issue: [description]" → I'll help debug that specific phase
```

### Gate Failures During Multi-Phase

If any phase fails automated gates after 3 self-healing attempts:

```
❌ Phase [N] Automated Gates Failed

Cannot proceed with multi-phase execution until this is resolved.

Gate failure: [details]
Attempts made: 3/3
Manual intervention required.

Please debug and advise. Remaining phases are on hold.
```

Stop immediately. Do not proceed to subsequent phases.

## Resuming Work

If the plan has existing checkmarks or status markers:

**For phases marked "Complete":**

- Trust that work is done
- Skip to the next incomplete phase
- Only re-verify if something seems broken

**For phases marked "In Progress":**

- Read the phase carefully
- Check which items are already marked [x]
- Start from the first unchecked item
- Re-run automated gates even if some passed before (code may have changed)

**Resume report:**

```
Resuming Execution

Phase 1: Complete ✅
Phase 2: In Progress ⏸️
  - [x] Completed item 1
  - [x] Completed item 2
  - [ ] Next: Item 3 ← Starting here
Phase 3: Not Started

Proceeding with Phase 2, Item 3...
```

## Understanding Success Criteria Format

Plans define two types of verification:

### Automated Verification (Gates)

These are executable commands or programmatic checks:

```markdown
#### Automated Verification (Gates):

- [ ] Tests pass: `npx nx affected -t test`
- [ ] Lint passes: `npx nx affected -t lint`
- [ ] Build succeeds: `npx nx affected -t build`
- [ ] Types check: `npm run typecheck`
```

**Your job:** Run these commands and self-heal if they fail.

### Manual Verification

These require human judgment:

```markdown
#### Manual Verification:

- [ ] Feature appears correctly in the UI
- [ ] Performance is acceptable with 1000+ items
- [ ] Error messages are user-friendly
```

**Your job:** Ask the human to verify, wait for confirmation.

## Important Notes

- **Self-healing is for automated gates only** - Manual checks always require human verification
- **Read files completely** - Never use limit/offset parameters, you need full context
- **Update the plan file** - Use Edit tool to check off items as you complete them
- **Think before acting** - Understand the change before implementing
- **Forward momentum** - Keep the end goal in mind, don't get stuck on perfection
- **Use sub-tasks sparingly** - Mainly for targeted debugging when stuck
- **Communicate divergences** - When plan doesn't match reality, explain clearly and ask for guidance

## Output Structure Template

```
Execution Mode: [SINGLE_PHASE | MULTI_PHASE]

Phase [N]: [Phase Name]
Status: [NOT_STARTED | IN_PROGRESS | GATES_RUNNING | AWAITING_MANUAL | COMPLETE]

Implementation: [X/Y] sections complete
Automated Gates: [X/Y] PASSED
Manual Verification: [PENDING | CONFIRMED]

Next: [Specific action or waiting state]
```

## Remember

You're implementing a solution, not just checking boxes. Keep the end goal in mind:

- Build working, tested features
- Maintain code quality
- Follow project conventions
- Communicate clearly
- Move forward with confidence

The plan is your guide. Your judgment and ability to self-heal when things go wrong make you an effective execution agent.
