---
name: review-pr-first
description: First-time code review of a PR. Reads the full diff, changed files, and neighboring code. Produces a severity-ranked report with ready-to-copy GitHub comments. Saves to .vibeos/review.md. Use when performing an initial review of a PR that has not been reviewed before.
allowed-tools: Bash(gh *), Bash(git *), Read, Write
---

First-time review of a pull request. Read the code deeply — not just the diff. Produce a report that can be posted to GitHub with minimal editing.

Arguments: `{PR_NUMBER} {org/repo}` — e.g. `42 idesi/my-repo`
If no arguments are provided, auto-detect from the current branch.

## Step 0 — Resolve identity and repo

```bash
# Who is the reviewer?
REVIEWER=$(gh api user --jq .login)

# If args not provided, detect from current context:
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
PR_NUMBER=$(gh pr view --json number --jq .number)
```

If argument `{org/repo}` is provided, use it as REPO. If `{PR_NUMBER}` is provided, use it.

## Step 1 — Fetch PR context

```bash
# Core PR metadata
gh pr view $PR_NUMBER --repo $REPO \
  --json title,body,author,headRefName,baseRefName,changedFiles,labels,isDraft,url

# Full unified diff
gh pr diff $PR_NUMBER --repo $REPO

# CI / check status
gh pr checks $PR_NUMBER --repo $REPO --json name,state,bucket,description

# Existing review comments — read these first to avoid duplicating prior feedback
gh api repos/$REPO/pulls/$PR_NUMBER/comments --paginate \
  --jq '.[] | {author: .user.login, path, line: (.line // .original_line), body}'

# Existing reviews (review-level comments, not inline)
gh api repos/$REPO/pulls/$PR_NUMBER/reviews --paginate \
  --jq '.[] | {author: .user.login, state, body, submitted_at}'
```

For any **failing CI checks**, fetch the actual failure output:
```bash
# Get recent runs for this PR's branch
gh run list --branch $(gh pr view $PR_NUMBER --repo $REPO --json headRefName --jq .headRefName) \
  --limit 5 --json databaseId,status,conclusion,name

# For each failing run, get the failure logs
gh run view <RUN_ID> --repo $REPO --log-failed 2>/dev/null
```

## Step 2 — Read the code

For each changed file in the diff:
1. `Read` the **full file** — not just the changed lines — to understand the surrounding context
2. Read related test files if they exist (e.g. `*.test.ts`, `*.spec.ts` alongside the changed file)
3. Check what imports or calls the changed functions to understand downstream impact

If the diff is large (20+ files), prioritize in this order:
1. Security-sensitive paths (auth, permissions, API routes, data access)
2. Core business logic changes
3. Test coverage gaps
4. Style and naming

## Step 3 — Review against these criteria

- **Correctness** — does the logic match what the PR description claims?
- **Edge cases** — unhandled null/undefined, off-by-one, empty arrays, concurrent access
- **Security** — injection risks, auth bypasses, exposed secrets or tokens, IDOR
- **Tests** — are changes tested? Do tests actually exercise the changed logic? Are existing tests still valid?
- **Code quality** — naming clarity, duplication, unnecessary complexity, dead code
- **CI** — are all checks passing? If not, is the failure related to this PR?

**Triage rules:**
- 🔴 **Blocking** — merging this would introduce a bug, security issue, or broken test. Must be fixed.
- 🟡 **Non-blocking** — real issue, but not a merge blocker. Can be a follow-up ticket.
- 💡 **Suggestion** — style, readability, or optional improvement. Low priority.
- **Skip** anything already raised in the existing review comments fetched in Step 1.

## Step 4 — Write `.vibeos/review.md`

```markdown
# PR Review: {title}
**Repo:** {org/repo} | **PR:** #{N} | **Author:** @{author}
**Reviewed by:** @{reviewer} | **Date:** YYYY-MM-DD | **Type:** First Review
**Branch:** {headRef} → {baseRef}
**Recommendation:** ✅ Approve | 🔄 Request Changes | 💬 Comment Only

---

## TL;DR

{2-3 sentences. What does this PR do? Is it safe to merge? What's the main concern if any?}
{If isDraft: ⚠️ This is a **draft PR** — not ready for merge review, but issues noted below.}

---

## Changes Overview

| File | What changed |
|------|-------------|
| `{file}` | {one-line summary} |

**CI Status:** ✅ All passing | ❌ {N} failing: `{name}` — {error summary} | ⏳ Pending

---

## Issues Found

### 🔴 Blocking (must fix before merge)

#### `{file}:{line}` — {issue title}
**Problem:** {what's wrong and why it matters}
**Fix:** {specific suggestion}
```{language}
// suggested code if helpful
```

---

### 🟡 Non-blocking (should fix)

#### `{file}:{line}` — {issue title}
**Problem:** {what's wrong}
**Fix:** {suggestion}

---

### 💡 Suggestions (optional)

- `{file}:{line}` — {suggestion}

---

## Ready-to-Post GitHub Comments

> Copy-paste these directly onto the PR.

**Overall review comment:**
```
{3-5 sentence professional summary: what the PR does, key finding, recommendation}
```

**Inline comments:**

`{path/to/file.ts}` line {N}:
```
{inline comment — explain the problem and the fix, constructively}
```

`{path/to/file.ts}` line {N}:
```
{inline comment}
```
```

## Notes

- Be specific: "`auth.ts:42`" not "somewhere in the auth logic"
- Be constructive: explain *why* something is a problem, not just that it is
- If CI is failing for reasons clearly unrelated to this PR, note it but don't block on it
- If no blocking issues are found, default to ✅ Approve — don't invent concerns
- Only raise a 🔴 Blocking issue if you are confident it would cause harm in production
