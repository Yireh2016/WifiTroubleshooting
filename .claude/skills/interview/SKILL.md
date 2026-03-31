---
description: Conduct thorough requirement analysis interviews to create bulletproof specifications before coding. Integrates with JIRA for PM collaboration and tracks open questions.
allowed-tools: Bash(*)
---

# Interview - Requirement Hardening

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/load-config.sh"`

> **Prerequisites**: Atlassian CLI (`acli`) recommended for JIRA integration. If not installed, the skill will provide copy-paste text for manual JIRA updates.

> **Customization**: Add domain-specific interview examples to `.claude/skills/interview/examples.md` in your repo root. If not present, `examples.md` at repo root is used. See end of file for format.

You are conducting a thorough requirement analysis interview to create a bulletproof specification. Your goal is to uncover gaps, ambiguities, and missing details before any code is written.

## Prerequisites Check

Before starting, check if Atlassian CLI is available:

```bash
which acli
```

- **If available**: Use `acli` commands for JIRA integration as documented below
- **If NOT available**: Provide formatted copy-paste text for manual JIRA updates (see fallback instructions in each section)

## Setup

1. **Check for existing spec.md first**:
   - Look for `{artifactsDir}/*/spec.md` files in the current directory
   - If found, ask: "I found an existing spec at `{artifactsDir}/<project>/spec.md`. Would you like to:"
     - a) Resume the interview (import PM responses from JIRA)
     - b) Start a new interview
     - c) Just review the existing spec

2. **If resuming an existing interview**:
   - Read the existing `spec.md` FULLY
   - Check for "Open Questions for PM" section
   - If ticket ID exists and `acli` is available, fetch latest comments from JIRA:
     ```bash
     acli jira workitem view <ticket-id> --fields "*all" --json | jq '.fields.comment.comments'
     ```
   - If ticket ID exists but `acli` is NOT available:
     - Check if JIRA MCP tools are available and use those
     - Otherwise, Tell user: "Please check JIRA ticket <ticket-id> for any PM responses to the open questions and share them with me."
     - Wait for user to provide PM responses
   - Look for PM responses that answer the open questions
   - Update `spec.md` with PM's answers:
     - Move answered questions from "Open Questions for PM" to main Q&A
     - Add PM's response with timestamp
   - Resume interview: "I've imported the PM's responses. Let me review what we have now..."
   - Continue interviewing if gaps remain, or conclude if complete

3. **If starting new interview**, ask: "Do you want to fetch requirements from JIRA, or provide your own initial spec?"

### Option A: Fetch from JIRA

1. Get the ticket identifier (e.g., RMK-12345)
2. Fetch ticket details:
   - **If `acli` is available**: Use Atlassian CLI:
     ```bash
     acli jira workitem view <ISSUE_KEY> --fields "*all" --json
     ```
   - **If `acli` is NOT available**:
     - Check if JIRA MCP tools are available and use those
     - Otherwise, ask user: "Please provide the JIRA ticket details (title, description, acceptance criteria) and I'll create the spec."
3. Create the spec file: `{artifactsDir}/<ticket-id>/spec.md`
4. Initialize spec.md with:
   - Ticket ID and title
   - Original description from JIRA
   - Acceptance criteria (if present)
   - Section for Q&A

### Option B: Developer-Provided Spec

1. Ask: "What's the task identifier? (e.g., RMK-12345 or a descriptive name)"
2. Ask: "Please provide the initial requirements or paste what you have"
3. Create the spec file: `{artifactsDir}/<task-identifier>/spec.md`
4. Initialize spec.md with:
   - Task identifier and title
   - Requirements provided by developer
   - Section for Q&A

Regardless of option, proceed to interview phase.

## Interview Process

Ask questions in a natural, conversational manner. Focus on uncovering what's _not_ explicitly stated in the requirements.

**The questions below are common gaps we've historically missed - use them as a starting point, but don't limit yourself to only these areas.** Dig into whatever seems unclear, ambiguous, or missing based on the specific task at hand.

### Common Gap Areas (Customizable)

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/render-examples.sh"`

## Interview Guidelines

- **Use the AskUserQuestion tool** for structured questions with multiple options, especially when:
  - Choosing between implementation approaches (e.g., "Which library should we use for X?")
  - Clarifying requirements that have clear alternatives (e.g., "Should this feature be available to all users or just admins?")
  - Getting decisions on architectural choices
  - The tool allows users to select from predefined options or provide custom input via "Other"
- **Ask one question at a time** or group tightly related questions
- **Reference what you found** in the codebase when asking questions (e.g., "I see we handle similar cases in X by doing Y. Should we follow that pattern?")
- **Track open questions** - if user says "I need to check with PM", add to "Open Questions for PM" section
- **Don't post PM questions yet** - collect them all and batch post at the end
- **Be thorough but not pedantic** - focus on gaps that could cause rework
- **Use examples** from the codebase to make questions concrete
- **Don't ask questions the ticket already answers clearly**

## When You're Done

After each round of Q&A:

1. Update `spec.md` with the answers
2. Assess completeness: Do you have clear answers for all critical areas?
3. If gaps remain: Continue with next question
4. If no critical gaps remain:
   - Summarize what you've learned
   - State: "I believe we've covered all critical areas. The spec looks complete."
   - Ask: "Do you agree, or are there areas you'd like to explore further?"

Continue until either:

- You believe the spec is complete AND user confirms, OR
- User explicitly says to stop

## Handling Open PM Questions

If there are any questions in the "Open Questions for PM" section when interview concludes:

1. Show all open questions to the user
2. Ask: "Would you like me to post these questions to JIRA?"
3. If yes and ticket ID exists:
   - Format all questions as a numbered list with context
   - **If `acli` is available**: Post using:
     ```bash
     acli jira workitem comment create --key "<ticket-id>" --body "Questions from requirement review:\n\n<formatted-questions>"
     ```
   - **If `acli` is NOT available**: Provide the formatted text for manual copy-paste:

     ```
     Here's the comment to post to JIRA ticket <ticket-id>:

     ---
     Questions from requirement review:

     <formatted-questions>
     ---

     Please copy the text above and paste it as a comment on the JIRA ticket.
     ```

   - Note in spec.md that questions were posted/provided on [date/time]

4. If yes but no ticket ID (developer-provided spec):
   - Note in spec.md that these questions need to be sent to PM
   - Suggest creating a JIRA ticket or sending via your team's communication channel

## Sync Key Decisions to JIRA

After the interview is complete, ask:

"Would you like me to post a summary of key decisions back to the JIRA ticket?"

If yes:

1. Generate a summary containing ONLY the significant decisions/clarifications from the interview:
   - Keep it concise - 5-10 bullet points max
2. Show the draft to the developer:

   ```
   Here's the summary:

   ---
   Requirement Clarifications (from AI interview on [date])

   - [Key decision 1]
   - [Key decision 2]
   - [Relevant clarification 3]
   ---
   ```

3. Ask: "Does this look good, or would you like me to adjust anything?"
4. After approval:
   - **If `acli` is available**: Post using:
     ```bash
     acli jira workitem comment create --key "<ticket-id>" --body "<formatted-summary>"
     ```
   - **If `acli` is NOT available**: Provide formatted text for manual copy-paste:

     ```
     Please copy the text below and paste it as a comment on JIRA ticket <ticket-id>:

     ---
     [formatted-summary]
     ---
     ```

5. Note in spec.md that summary was posted/provided on [date/time]

## Final Output

The `{artifactsDir}/<ticket-id>/spec.md` should contain:

- Complete ticket information
- All questions asked and answers received
- Open questions (if any) clearly marked
- Any assumptions made
- References to related code/patterns found in codebase

---

**Remember**: Better requirements now = less rework later. Be thorough.

---

## Customization Guide

To tailor interview questions to your domain, create an override file. The skill loads examples using this precedence:

1. **Project-level** (highest priority): `.claude/skills/interview/examples.md` in your project root
2. **Repo root fallback**: `examples.md` at the repository root
3. **Plugin defaults**: Built-in examples bundled with the plugin

To customize, create `.claude/skills/interview/examples.md` in your project root (commit to repo for team-wide use):

```markdown
For each area below, contextualize your questions based on what you discover in the codebase:

1. **Your Domain-Specific Area**
   - Question specific to your product/tech stack
   - Another relevant question
   - Edge cases you've encountered

2. **Another Important Area**
   - Questions tailored to your team's gaps
   - Tool-specific concerns (monitoring, feature flags, etc.)

**Again: These are examples. Ask about anything that seems unclear or could cause problems later.**
```

No plugin forking required. Override files take priority over the built-in defaults.
