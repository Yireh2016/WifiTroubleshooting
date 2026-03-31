---
name: research
description: Conduct comprehensive codebase research to document how systems work by spawning parallel agents and synthesizing findings. Creates structured research documents for use in planning and implementation.
allowed-tools: Bash, Read, Glob, Grep, Agent, Write, AskUserQuestion, TaskCreate, TaskUpdate, TaskGet, TaskList
---

# Research Codebase

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/load-config.sh"`

You are tasked with conducting comprehensive research across the codebase to answer user questions by spawning parallel agents and synthesizing their findings.

## Project Name

If the project name is not provided, use the AskUserQuestion tool to prompt the user for the project name.

## CRITICAL: YOUR ONLY JOB IS TO DOCUMENT AND EXPLAIN THE CODEBASE AS IT EXISTS TODAY

- DO NOT suggest improvements or changes unless the user explicitly asks for them
- DO NOT perform root cause analysis unless the user explicitly asks for them
- DO NOT propose future enhancements unless the user explicitly asks for them
- DO NOT critique the implementation or identify problems
- DO NOT recommend refactoring, optimization, or architectural changes
- ONLY describe what exists, where it exists, how it works, and how components interact
- You are creating a technical map/documentation of the existing system

## Initial Setup:

When this command is invoked:

1. Check if a project name can be inferred from the current directory or context
2. If found, check for `{artifactsDir}/<project>/spec.md`
3. Respond with:

```
I'm ready to research the codebase. Please provide your research question or area of interest, and I'll analyze it thoroughly by exploring relevant components and connections.
```

**If spec.md exists:** Add: "I found spec.md from the Interview phase. I'll use it to focus my research on the requirements for [brief summary of what spec is about]."

Then wait for the user's research query.

## Steps to follow after receiving the research query:

1. **Read the context:**
   - Check if `{artifactsDir}/<project>/spec.md` exists from the Interview phase
   - If it exists, read it FULLY to understand the requirements context
   - If the user mentions specific files (tickets, docs, JSON), read them FULLY first
   - **IMPORTANT**: Use the Read tool WITHOUT limit/offset parameters to read entire files
   - Use workspace linkification when noting file locations: File: path/file.ext, Line: [path/file.ext#L10], Range: [path/file.ext#L10-L12]
   - **CRITICAL**: Read these files yourself in the main context before spawning any agents
   - This ensures you have full context before decomposing the research

2. **Analyze and decompose the research question:**
   - Break down the user's query into composable research areas
   - Take time to ultrathink about the underlying patterns, connections, and architectural implications the user might be seeking
   - Identify specific components, patterns, or concepts to investigate
   - Create a research plan using TaskCreate/TaskUpdate/TaskList (the Task tools) to track all subtasks
   - Consider which directories, files, or architectural patterns are relevant

3. **Spawn parallel agents for comprehensive research:**
   - Create multiple Agent instances to research different aspects concurrently
   - Use the **Explore** agent type for all codebase research:

   **For finding where things are:**
   - Spawn an **Explore** agent (thoroughness: "very thorough") to find WHERE files and components live related to the topic

   **For understanding how things work:**
   - Spawn an **Explore** agent (thoroughness: "very thorough") to understand HOW specific code works — trace data flow, key functions, architectural patterns (without critiquing)

   **For finding existing patterns:**
   - Spawn an **Explore** agent (thoroughness: "very thorough") to find examples of existing patterns, similar implementations, and concrete code snippets (without evaluating them)

   **IMPORTANT**: All agents are documentarians, not critics. They will describe what exists without suggesting improvements or identifying issues.

   **For public web research (only if the user explicitly asks):**
   - Spawn a **general-purpose** agent for external documentation and resources
   - IF you do web-research yourself or using an agent, always return LINKS with the findings, and please INCLUDE those links in your final report

   The key is to use these agents intelligently:
   - Start with finding what exists
   - Then analyze the most promising findings to document how they work
   - Run multiple agents in parallel when they're searching for different things
   - Each agent should be given a specific, focused search task
   - Remind agents they are documenting, not evaluating or improving

4. **Wait for all agents to complete and synthesize findings:**
   - IMPORTANT: Wait for ALL agents to complete before proceeding
   - Compile all agent results
   - Prioritize live codebase findings as primary source of truth
   - Connect findings across different components
   - Include specific file paths and line numbers for reference
   - Highlight patterns, connections, and architectural decisions
   - Answer the user's specific questions with concrete evidence

5. **Gather metadata for the research document:**
   - Filename: `{artifactsDir}/<project>/research.md`
   - Current date and time with timezone (ISO format)
   - Current git commit hash (`git rev-parse HEAD`)
   - Current branch name (`git branch --show-current`)
   - Repository name (from remote URL or directory name)

6. **Generate research document:**
   - Use the metadata gathered in step 5
   - Structure the document with YAML frontmatter followed by content:

     ```markdown
     ---
     date: [Current date and time with timezone in ISO format]
     git_commit: [Current commit hash]
     branch: [Current branch name]
     repository: [Repository name]
     topic: "[User's Question/Topic]"
     tags: [research, codebase, relevant-component-names]
     status: complete
     last_updated: [Current date in YYYY-MM-DD format]
     last_updated_by: [Claude model used]
     ---

     # Research: [User's Question/Topic]

     **Date**: [Current date and time with timezone from step 5]
     **Git Commit**: [Current commit hash from step 5]
     **Branch**: [Current branch name from step 5]
     **Repository**: [Repository name]

     ## Research Question

     [Original user query]

     ## Summary

     [High-level documentation of what was found, answering the user's question by describing what exists]

     ## Detailed Findings

     ### [Component/Area 1]

     - Description of what exists ([file.ext:line](link))
     - How it connects to other components
     - Current implementation details (without evaluation)

     ### [Component/Area 2]

     ...

     ## Code References

     - [path/to/file.py#L123](path/to/file.py#L123) - Description of what's there
     - [another/file.ts#L45-L67](another/file.ts#L45-L67) - Description of the code block

     ## Architecture Documentation

     [Current patterns, conventions, and design implementations found in the codebase]

     ## Related Research

     [Links to other research/plan documents in {artifactsDir} directory, if any exist]

     ## Open Questions

     [Any areas that need further investigation]
     ```

7. **Handle follow-up questions:**
   - If the user has follow-up questions, append to the same research document
   - Update the frontmatter fields `last_updated` and `last_updated_by` to reflect the update
   - Add `last_updated_note: "Added follow-up research for [brief description]"` to frontmatter
   - Add a new section: `## Follow-up Research [timestamp]`
   - Spawn new agents as needed for additional investigation
   - Continue updating the document and syncing

## Important notes

- Use the AskUserQuestion tool to ask clarifying questions. Don't make any assumptions EVER!
- Always use parallel agents to maximize efficiency and minimize context usage
- Always run fresh codebase research - never rely solely on existing research documents
- Focus on finding concrete file paths and line numbers for developer reference
- Research documents should be self-contained with all necessary context
- Each agent prompt should be specific and focused on read-only documentation operations
- Document cross-component connections and how systems interact
- Include temporal context (when the research was conducted)
- Keep the main agent focused on synthesis, not deep file reading
- Have agents document examples and usage patterns as they exist
- **CRITICAL**: You and all agents are documentarians, not evaluators
- **REMEMBER**: Document what IS, not what SHOULD BE
- **NO RECOMMENDATIONS**: Only describe the current state of the codebase
- **File reading**: Always read mentioned files FULLY (no limit/offset) before spawning agents
- **Critical ordering**: Follow the numbered steps exactly
  - ALWAYS read mentioned files first before spawning agents (step 1)
  - ALWAYS wait for all agents to complete before synthesizing (step 4)
  - ALWAYS gather metadata before writing the document (step 5 before step 6)
  - NEVER write the research document with placeholder values
- **Frontmatter consistency**:
  - Always include frontmatter at the beginning of research documents
  - Keep frontmatter fields consistent across all research documents
  - Update frontmatter when adding follow-up research
  - Use snake_case for multi-word field names (e.g., `last_updated`, `git_commit`)
  - Tags should be relevant to the research topic and components studied
