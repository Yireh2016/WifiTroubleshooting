---
name: plan
description: Create detailed implementation plans through interactive research and iteration. Produces phased plans with dependency graphs, success criteria, and verification gates.
allowed-tools: Bash, Read, Glob, Grep, Agent, Write, Edit, AskUserQuestion, TaskCreate, TaskUpdate, TaskGet, TaskList
---

# Implementation Plan

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/load-config.sh"`

You are tasked with creating detailed implementation plans through an interactive, iterative process. You should be skeptical, thorough, and work collaboratively with the user to produce high-quality technical specifications.

## Initial Response

When this command is invoked:

1. **Check for existing context in {artifactsDir}/<project>/**:
   - If `spec.md` exists (from Interview), read it FULLY
   - If `research.md` exists (from Research), read it FULLY
   - Acknowledge what you found: "I found spec.md and research.md from previous phases. I'll use them as the foundation."

2. **Check if parameters were provided**:
   - If a file path or ticket reference was provided as a parameter, skip the default message
   - Immediately read any provided files FULLY
   - Begin the research process

3. **If no parameters provided**, respond with "I'll help you create a detailed implementation plan. Let me start by understanding what we're building." & then use the AskUserQuestion tool to ask the following questions

```
1. The task/ticket description (or reference to a ticket file)
2. Any relevant context, constraints, or specific requirements
3. Links to related research or previous implementations
```

Once they have answered these questions respond with

```
I'll analyze this information and work with you to create a comprehensive plan.

Tip: You can also invoke this command with existing context: `/feature-dev:plan {artifactsDir}/<project>/file.md`
```

Then wait for the user's input.

## Process Steps

### Step 1: Context Gathering & Initial Analysis

1. **Read all mentioned files immediately and FULLY**:
   - Context files, research documents, related implementation plans
   - Any JSON/data files mentioned
   - **IMPORTANT**: Use the Read tool WITHOUT limit/offset parameters to read entire files
   - **CRITICAL**: DO NOT spawn agents before reading these files yourself in the main context
   - **NEVER** read files partially - if a file is mentioned, read it completely
   - When citing files or lines in your notes, use workspace linkification: File: path/file.ext, Line: [path/file.ext#L10], Range: [path/file.ext#L10-L12]

2. **Spawn initial research agents to gather context**:
   Before asking the user any questions, use the Agent tool to research in parallel:
   - Spawn an **Explore** agent (thoroughness: "very thorough") to find all files related to the task — source files, configs, tests, type definitions
   - Spawn another **Explore** agent (thoroughness: "very thorough") to understand how the current implementation works — trace data flow, key functions, architectural patterns

   These agents will:
   - Find relevant source files, configs, and tests
   - Trace data flow and key functions
   - Return detailed explanations with file:line references

3. **Read all files identified by research agents**:
   - After research agents complete, read ALL files they identified as relevant
   - Read them FULLY into the main context
   - This ensures you have complete understanding before proceeding

4. **Analyze and verify understanding**:
   - Cross-reference the ticket requirements with actual code
   - Identify any discrepancies or misunderstandings
   - Note assumptions that need verification
   - Determine true scope based on codebase reality

5. **Present informed understanding and focused questions**:

   ```
   Based on the ticket and my research of the codebase, I understand we need to [accurate summary].

   I've found that:
   - [Current implementation detail with file:line reference]
   - [Relevant pattern or constraint discovered]
   - [Potential complexity or edge case identified]

   Questions that my research couldn't answer:
   - [Specific technical question that requires human judgment]
   - [Business logic clarification]
   - [Design preference that affects implementation]
   ```

   Only ask questions that you genuinely cannot answer through code investigation.

### Step 2: Research & Discovery

After getting initial clarifications:

1. **If the user corrects any misunderstanding**:
   - DO NOT just accept the correction
   - Spawn new research agents to verify the correct information
   - Read the specific files/directories they mention
   - Only proceed once you've verified the facts yourself

2. **Create a research task list** use TaskCreate/TaskUpdate/TaskList (the Task tools)

3. **Spawn parallel agents for comprehensive research**:
   - Create multiple Agent instances to research different aspects concurrently
   - Use the right approach for each type of research:

   **For deeper investigation:**
   - Spawn an **Explore** agent to find more specific files (e.g., "find all files that handle [specific component]")
   - Spawn another **Explore** agent to understand implementation details (e.g., "analyze how [system] works, trace data flow, identify key functions")
   - Spawn an **Explore** agent to find similar features and existing patterns we can model after (e.g., "find examples of similar [feature type] implementations in this codebase, show concrete code snippets")

   Each agent should:
   - Find the right files and code patterns
   - Identify conventions and patterns to follow
   - Look for integration points and dependencies
   - Return specific file:line references
   - Find tests and examples

4. **Wait for ALL agents to complete** before proceeding

5. **Present findings and design options**:

   ```
   Based on my research, here's what I found:

   **Current State:**
   - [Key discovery about existing code]
   - [Pattern or convention to follow]

   **Design Options:**
   1. [Option A] - [pros/cons]
   2. [Option B] - [pros/cons]

   **Open Questions:**
   - [Technical uncertainty]
   - [Design decision needed]

   Which approach aligns best with your vision?
   ```

### Step 3: Plan Structure Development

Once aligned on approach:

1. **Create initial plan outline**:

   ```
   Here's my proposed plan structure:

   ## Overview
   [1-2 sentence summary]

   ## Implementation Phases:
   1. [Phase name] - [what it accomplishes]
   2. [Phase name] - [what it accomplishes]
   3. [Phase name] - [what it accomplishes]

   Does this phasing make sense? Should I adjust the order or granularity?
   ```

2. **Get feedback on structure** before writing details

3. **Determine dependencies and parallelization**:

   After phases are agreed upon, explicitly ask:

   ```
   Now let's map out the dependencies between phases:

   Based on my analysis:
   - Phase 1 and Phase 2 can be worked on in parallel (no shared dependencies)
   - Phase 3 depends on Phase 2 (needs the API to be ready)
   - Phase 4 depends on both Phase 1 and Phase 3

   Proposed execution groups:
   - Group 1 (start immediately): Phase 1, Phase 2
   - Group 2 (after Phase 2): Phase 3
   - Group 3 (final): Phase 4

   Does this dependency mapping look correct? Any phases that could be parallelized that I missed?
   ```

   **Why this matters**: The dependency information helps with:
   - Creating issue links (blocks/is blocked by)
   - Sprint planning (parallel tasks can be assigned to different developers)
   - Ensuring tasks are created in the correct order

### Step 4: Detailed Plan Writing

After structure approval:

1. **Write the plan** to {artifactsDir}/<project>/implementation-plan.md
2. **Use this template structure**:

````markdown
# [Feature/Task Name] Implementation Plan

## Overview

[Brief description of what we're implementing and why]

## Current State Analysis

[What exists now, what's missing, key constraints discovered]

## Desired End State

[A Specification of the desired end state after this plan is complete, and how to verify it]

### Key Discoveries:

- [Important finding with file:line reference]
- [Pattern to follow]
- [Constraint to work within]

## What We're NOT Doing

[Explicitly list out-of-scope items to prevent scope creep]

## Implementation Deviations

<!-- Auto-populated during execution -->

_No deviations recorded yet._

---

## Implementation Approach

[High-level strategy and reasoning]

## Task Dependencies & Parallelization

### Dependency Graph

<!--
Use vertical flow for clarity. Show parallel phases side-by-side,
sequential phases vertically, and merges with arrows converging.
-->

```
        ┌─────────────┐
        │   Start     │
        └──────┬──────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌─────────────┐ ┌─────────────┐
│   Phase 1   │ │   Phase 2   │  ← Can run in parallel
└──────┬──────┘ └──────┬──────┘
       │               │
       │               ▼
       │        ┌─────────────┐
       │        │   Phase 3   │  ← Blocked by Phase 2
       │        └──────┬──────┘
       │               │
       └───────┬───────┘
               │
               ▼
        ┌─────────────┐
        │   Phase 4   │  ← Blocked by Phase 1 AND Phase 3
        └─────────────┘
```

### Execution Groups

Tasks within the same group can be worked on in parallel by different developers.

| Group | Phases           | Notes                                  |
| ----- | ---------------- | -------------------------------------- |
| 1     | Phase 1, Phase 2 | No dependencies, can start immediately |
| 2     | Phase 3          | Blocked by Phase 2                     |
| 3     | Phase 4          | Blocked by Phase 1 and Phase 3         |

### Phase Dependencies

| Phase   | Depends On       | Blocks  | Can Parallel With |
| ------- | ---------------- | ------- | ----------------- |
| Phase 1 | -                | Phase 4 | Phase 2           |
| Phase 2 | -                | Phase 3 | Phase 1           |
| Phase 3 | Phase 2          | Phase 4 | -                 |
| Phase 4 | Phase 1, Phase 3 | -       | -                 |

---

## Phase 1: [Descriptive Name]

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete
**Depends On**: None
**Blocks**: Phase 4

### Overview

[What this phase accomplishes]

### Changes Required:

#### 1. [Component/File Group]

- [ ] **File**: [path/to/file.ext](path/to/file.ext)
  - **Changes**: [Summary of changes]

```[language]
// Specific code to add/modify
```

### Success Criteria (Gates):

Gates: are defined as a set of verification steps that once they pass we can say a phase is completed. They can be run a pass a set of unit tests, E2E tests, integration tests and/or manual verification. When a gate fails to pass the coding agent should iterate until it get it right before going to the next phase making the whole workflow a self healing one.

#### Add Comprehensive Tests:

- Unit Tests
- Integration Tests
- E2E Tests
- Coverage: ask user about coverage and suggest a testing strategy that sufficiently covers the required changes.

#### Automated Verification:

- [ ] Migration applies cleanly
- [ ] Unit tests pass
- [ ] Type checking passes
- [ ] Linting passes
- [ ] Integration tests pass

#### Manual Verification:

- [ ] Feature works as expected when tested via UI
- [ ] Performance is acceptable under load
- [ ] Edge case handling verified manually
- [ ] No regressions in related features

**Implementation Note**: After completing this phase and all automated gates pass, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: [Descriptive Name]

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete
**Depends On**: None
**Blocks**: Phase 3

[Similar structure with both automated and manual success criteria...]

---

## Testing Strategy

### Unit Tests:

- [What to test]
- [Key edge cases]

### Integration Tests:

- [End-to-end scenarios]

### Manual Testing Steps:

1. [Specific step to verify feature]
2. [Another verification step]
3. [Edge case to test manually]

## Performance Considerations

[Any performance implications or optimizations needed]

## Migration Notes

[If applicable, how to handle existing data/systems]

## References

- Original ticket: [link or path]
- Related research: [link or path]
- Similar implementation: [path/to/file.ts#L10-L25](path/to/file.ts#L10-L25)
````

### Step 5: Sync and Review

1. **Present the draft plan location**:

   ```
   I've created the initial implementation plan at:
   [{artifactsDir}/<project>/implementation-plan.md]({artifactsDir}/<project>/implementation-plan.md)

   Please review it and let me know:
   - Are the phases properly scoped?
   - Are the success criteria specific enough?
   - Any technical details that need adjustment?
   - Missing edge cases or considerations?
   ```

2. **Iterate based on feedback** - be ready to:
   - Add missing phases
   - Adjust technical approach
   - Clarify success criteria (both automated and manual)
   - Add/remove scope items

3. **Continue refining** until the user is satisfied

## Important Guidelines

1. **Be Skeptical**:
   - Question vague requirements
   - Identify potential issues early
   - Ask "why" and "what about"
   - Don't assume - verify with code

2. **Be Interactive**:
   - Don't write the full plan in one shot
   - Get buy-in at each major step
   - Allow course corrections
   - Work collaboratively

3. **Be Thorough**:
   - Read all context files COMPLETELY before planning
   - Research actual code patterns using parallel agents
   - Include specific file paths and line numbers using workspace linkification (e.g., [path/to/file.ts#L10-L25](path/to/file.ts#L10-L25))
   - Write measurable success criteria with clear automated vs manual distinction

4. **Be Practical**:
   - Focus on incremental, testable changes
   - Consider migration and rollback
   - Think about edge cases
   - Include "what we're NOT doing"

5. **Track Progress**:
   - Use the Task tools to track planning tasks
   - Update tasks as you complete research
   - Mark planning tasks complete when done

6. **No Open Questions in Final Plan**:
   - If you encounter open questions during planning, STOP
   - Research or ask for clarification immediately
   - Do NOT write the plan with unresolved questions
   - The implementation plan must be complete and actionable
   - Every decision must be made before finalizing the plan

## Success Criteria Guidelines

**Always separate success criteria into two categories:**

1. **Automated Verification (Gates)** - can be run by execution agents:
   - Commands that can be run (see repo's CLAUDE.md for the specific commands)
   - Specific files that should exist
   - Code compilation/type checking
   - Automated test suites
   - These are called "gates" because execution will self-heal if they fail

2. **Manual Verification** (requires human testing):
   - UI/UX functionality
   - Performance under real conditions
   - Edge cases that are hard to automate
   - User acceptance criteria

**Phase Status Tracking:**

Each phase should include a status line at the top:

```markdown
**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete
```

This allows the execute command to track progress and resume work effectively.

**Format example:**

```markdown
## Phase 1: Database Schema Updates

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete
**Depends On**: None
**Blocks**: Phase 2

### Overview

Add user preferences table and migration

### Changes Required:

#### 1. Database Migration

- [ ] **File**: [migrations/001_add_user_prefs.sql](migrations/001_add_user_prefs.sql)
  - **Changes**: Create user_preferences table with columns for theme, language, notifications

### Success Criteria:

#### Automated Verification (Gates):

- [ ] Database migration runs successfully
- [ ] All unit tests pass
- [ ] No linting errors
- [ ] API endpoint returns 200: `curl localhost:8080/api/preferences`

#### Manual Verification:

- [ ] New feature appears correctly in the UI
- [ ] Performance is acceptable with 1000+ items
- [ ] Error messages are user-friendly
- [ ] Feature works correctly on mobile devices
```

## Common Patterns

### For Database Changes:

- Start with schema/migration
- Add store methods
- Update business logic
- Expose via API
- Update clients

### For New Features:

- Research existing patterns first
- Start with data model
- Build backend logic
- Add API endpoints
- Implement UI last

### For Refactoring:

- Document current behavior
- Plan incremental changes
- Maintain backwards compatibility
- Include migration strategy

## Agent Research Best Practices

When spawning research agents:

1. **Spawn multiple agents in parallel** for efficiency
2. **Each agent should be focused** on a specific area
3. **Provide detailed instructions** including:
   - Exactly what to search for
   - Which directories to focus on
   - What information to extract
   - Expected output format
4. **Request specific file:line references** in responses
5. **Wait for all agents to complete** before synthesizing
6. **Verify agent results**:
   - If an agent returns unexpected results, spawn follow-up agents
   - Cross-check findings against the actual codebase
   - Don't accept results that seem incorrect

## Example Interaction Flow

```
User: /feature-dev:plan
Assistant: I'll help you create a detailed implementation plan...

User: We need to add parent-child tracking for sub-tasks. See {artifactsDir}/PROJ-123/context.md
Assistant: Let me read that file completely first...

[Reads file fully]

Based on the file, I understand we need to track parent-child relationships. Before I start planning, I have some questions...

[Interactive process continues...]
```

## After Plan Completion

Once the plan is finalized, ask:

"Would you like me to help with anything else related to this plan?"
