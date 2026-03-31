---
name: address-pr-comments-dry
description: Safe/fallback variant of address-pr-comments. Fetches all unresolved review threads, applies local code fixes, but makes NO GitHub API writes — no replies posted, no threads resolved, no re-review requests sent. Writes a full action report to .vibeos/review.md with the exact reply text that would have been posted for each thread. Use this as a fallback when you want to review the agent's decisions before they hit GitHub.
allowed-tools: Bash(gh *), Bash(git *), Read, Edit, Write, Glob, Grep
---

Dry-run variant of the PR comment address workflow. Applies code fixes locally. Posts nothing to GitHub. Writes a complete action report to `.vibeos/review.md` so you can review every decision and take action manually.

Arguments: `{PR_NUMBER} {org/repo}` — e.g. `42 idesi/my-repo`
If no arguments provided, auto-detect from the current branch.

---

## Phase 0 — Resolve context

```bash
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
PR_NUMBER=$(gh pr view --json number --jq .number)
OWNER=${REPO%/*}
NAME=${REPO#*/}
```

---

## Phase 1 — Fetch all unresolved review threads

```bash
gh api graphql -f query="
query {
  repository(owner: \"$OWNER\", name: \"$NAME\") {
    pullRequest(number: $PR_NUMBER) {
      title
      headRefName
      baseRefName
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 20) {
            nodes {
              databaseId
              author { login }
              body
              path
              line
              originalLine
              createdAt
            }
          }
        }
      }
    }
  }
}" | jq '[
  .data.repository.pullRequest.reviewThreads.nodes[]
  | select(.isResolved == false)
]'
```

Also fetch review-level comments:

```bash
gh api repos/$REPO/pulls/$PR_NUMBER/reviews --paginate \
  --jq '.[] | select(.state == "CHANGES_REQUESTED" or .state == "COMMENTED") | {
    id, author: .user.login, state, body, submitted_at
  }'
```

---

## Phase 2 — Categorize each thread

For each unresolved thread, classify it by reading the full thread history:

**Actionable** — apply a local code fix
**Answer only** — no code change, just a reply (draft the reply text, do not post it)
**Decline** — no code change, disagreement with reasoning (draft the reply text, do not post it)
**Skip** — thread already resolved in conversation, or the code at that location no longer exists

---

## Phase 3 — Address each thread (local changes only)

### For Actionable threads:

1. Read the full file at the comment's path
2. Apply the fix using `Edit` — only the change the comment requests, nothing more
3. Draft the reply text you would have posted (save it for the report — **do not call any GitHub API**)

Reply draft format: concise, factual. E.g.:
- "Done — extracted the validation logic into a separate `validateInput()` function."
- "Done — added null check before accessing `.user.id`."

### For Answer-only and Decline threads:

Draft the reply text you would have posted. Apply no code changes.
**Do not call any GitHub API.**

---

## Phase 4 — Write `.vibeos/review.md`

Write the complete action report. This file is the full record of what was done locally and what would have been posted to GitHub.

```markdown
# PR Comment Address (Dry Run): {PR title}
**Repo:** {org/repo} | **PR:** #{N}
**Date:** YYYY-MM-DD
**Mode:** Dry run — code changes applied locally, nothing posted to GitHub
**Threads found:** {total} | **Fixed:** {N} | **Answer only:** {N} | **Declined:** {N} | **Skipped:** {N}

---

## Summary

{2-3 sentences. What was the overall shape of the feedback? Were most comments actionable? Any recurring theme?}

---

## Thread-by-Thread

### ✅ Fixed (code change applied locally)

#### `{file}:{line}` — @{reviewer}
**Their comment:** {original comment text, quoted}
**What was changed:** {description of the edit made}
**Reply that would be posted:**
> Done — {reply text}
**To action:** Post reply → resolve thread

---

### 💬 Answer only (no code change)

#### @{reviewer} — {brief topic}
**Their comment:** {original comment text, quoted}
**Reply that would be posted:**
> {explanation text}
**To action:** Post reply → resolve thread

---

### ❌ Declined (no code change)

#### `{file}:{line}` — @{reviewer}
**Their comment:** {original comment text, quoted}
**Reason for declining:** {why no change was made}
**Reply that would be posted:**
> {reply text}
**To action:** Post reply → resolve thread

---

### ⏭️ Skipped

#### `{file}:{line}` — @{reviewer}
**Reason:** {already handled in thread / code no longer exists / etc.}

---

## Re-review Requests (not sent)

These reviewers had open threads and would have been re-requested:
- @{reviewer1}
- @{reviewer2}

**To action:** Re-request review from each reviewer above after resolving their threads.

---

## How to Promote to Full Auto-Mode

If this report looks correct, swap `/address-pr-comments-dry` for `/address-pr-comments`
and re-run — it will post all replies, resolve all threads, and send re-review requests automatically.
```

---

## Hard Rules

- **Never call any GitHub API with a write method** (`-X POST`, `-X PUT`, `-X PATCH`, `-X DELETE`, GraphQL mutations)
- Read-only GitHub calls are fine: `gh pr view`, `gh api ... GET`, GraphQL queries
- Code edits with `Edit` are allowed — local changes only
- Every thread must appear in the report, including skipped ones
