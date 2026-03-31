---
name: address-pr-comments
description: Addresses all unresolved review threads on a PR you authored. Fetches every unresolved thread (bot and human reviewers), applies code fixes, posts a reply to each thread, resolves it, then re-requests review from all reviewers who had open comments. Saves a full action summary to .vibeos/review.md. Use for the pr_review_address_comments workflow — when changes have been requested on your PR.
allowed-tools: Bash(gh *), Bash(git *), Read, Edit, Write, Glob, Grep
---

Address all unresolved review threads on a PR you authored. Fix the code, reply to every thread, resolve it, re-request review. No human checkpoints — runs to completion.

Arguments: `{PR_NUMBER} {org/repo}` — e.g. `42 idesi/my-repo`
If no arguments provided, auto-detect from the current branch.

---

## Phase 0 — Resolve context

```bash
# Detect repo and PR if not provided
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
PR_NUMBER=$(gh pr view --json number --jq .number)
OWNER=${REPO%/*}
NAME=${REPO#*/}

# Verify current branch matches the PR's head branch
PR_BRANCH=$(gh pr view $PR_NUMBER --repo $REPO --json headRefName --jq .headRefName)
CURRENT_BRANCH=$(git branch --show-current)
# If branches don't match, note it in the output but proceed anyway —
# VibeOS dispatches agents into the correct worktree.
```

---

## Phase 1 — Fetch all unresolved review threads

Use GraphQL to get every unresolved thread in one call — this is the authoritative source:

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

Also fetch review-level comments (top-level review body, not attached to a line):

```bash
gh api repos/$REPO/pulls/$PR_NUMBER/reviews --paginate \
  --jq '.[] | select(.state == "CHANGES_REQUESTED" or .state == "COMMENTED") | {
    id, author: .user.login, state, body, submitted_at
  }'
```

Each unresolved thread has:
- `.id` — thread node ID (GraphQL — for resolving)
- `.comments.nodes[0].databaseId` — comment ID (REST — for replying)
- `.comments.nodes[0].author.login` — who wrote the original comment
- `.comments.nodes[0].path` / `.line` / `.body` — location and content
- `.comments.nodes[*]` — full thread, including any replies already made

---

## Phase 2 — Categorize each thread

For each unresolved thread, classify it before acting. Read the full thread (all `.comments.nodes`) to understand what was concluded:

**Actionable** — make a code change:
- Reviewer requests a specific fix, refactor, or improvement
- Bug or issue identified that needs addressing
- No reply from PR author yet, or author agreed to fix it

**Answer only** — reply but no code change:
- Reviewer asked a question that just needs an explanation
- Comment is a nit/observation the reviewer didn't expect action on
- PR author already explained the reasoning in a reply and reviewer didn't push back

**Decline** — reply explaining why, no code change:
- Change is out of scope for this PR (too large, different concern)
- PR author disagrees and can justify it
- Would break something else

**Skip** — already handled:
- Thread has a reply from the PR author and the reviewer responded positively
- The code at that path/line no longer exists in the current diff

Build a working list before acting. Do not skip threads silently — every unresolved thread must be replied to.

---

## Phase 3 — Address each thread

Work through threads in this order: **Actionable → Answer only → Decline**

### For each Actionable thread:

**3a. Read the file**
```
Read the full file at .comments.nodes[0].path
Also read any related test files if the fix may affect them
```

**3b. Apply the fix**
Use `Edit` to make the targeted change. Follow these rules:
- Make only the change the comment requests — no extra refactoring
- If the comment is ambiguous, interpret it in the most conservative way that still addresses the concern
- If fixing would require changes to multiple files, fix all of them

**3c. Post a reply**
```bash
gh api /repos/$REPO/pulls/$PR_NUMBER/comments \
  -X POST \
  -f body="Done — {one sentence describing what was changed and why}" \
  -F in_reply_to=<databaseId of first comment in thread>
```

Reply style: concise and factual. Describe what changed, not what the reviewer said. E.g.:
- "Done — extracted the validation logic into a separate `validateInput()` function."
- "Done — added null check before accessing `.user.id`."

**3d. Resolve the thread**
```bash
gh api graphql -f query="
mutation {
  resolveReviewThread(input: {threadId: \"<thread .id>\"}) {
    thread { isResolved }
  }
}"
```

Confirm `isResolved: true` before moving to the next thread.

### For each Answer-only thread:

Post a reply explaining the decision, then resolve:
```bash
gh api /repos/$REPO/pulls/$PR_NUMBER/comments \
  -X POST \
  -f body="{explanation}" \
  -F in_reply_to=<databaseId>

# then resolve same as above
```

### For each Decline thread:

Post a reply acknowledging the concern and explaining why no change was made, then resolve:
```
"Thanks for flagging this. I've decided to keep the current approach because {reason}.
Happy to address this in a follow-up if you'd like."
```

### For review-level comments (not attached to a line):

If a reviewer left a top-level review body with actionable content, address those the same way. Post a reply to the review using:
```bash
gh api /repos/$REPO/issues/$PR_NUMBER/comments \
  -X POST \
  -f body="{reply to the review-level comment}"
```

---

## Phase 4 — Re-request review

After all threads are resolved, re-request review from every human reviewer who had at least one unresolved thread.

Collect unique reviewer logins from Phase 1 (excluding bots — any login containing `[bot]` or known bot names like `copilot-pull-request-reviewer`, `dependabot`).

```bash
# Re-request from each human reviewer
gh api /repos/$REPO/pulls/$PR_NUMBER/requested_reviewers \
  -X POST \
  --input - <<EOF
{"reviewers": ["<reviewer1>", "<reviewer2>"]}
EOF
```

Also re-request Copilot if it had unresolved threads:
```bash
gh api /repos/$REPO/pulls/$PR_NUMBER/requested_reviewers \
  -X POST \
  -f 'reviewers[]=copilot-pull-request-reviewer[bot]'
```

---

## Phase 5 — Write `.vibeos/review.md`

After all threads are processed and review re-requests are sent, write the full summary:

```markdown
# PR Comment Address: {PR title}
**Repo:** {org/repo} | **PR:** #{N}
**Date:** YYYY-MM-DD
**Threads processed:** {total} | **Fixed:** {N} | **Answered:** {N} | **Declined:** {N}

---

## Summary

{2-3 sentences. How many threads were there? Were they addressed successfully? Any notable decisions?}

---

## Thread Log

### ✅ Fixed

#### `{file}:{line}` — @{reviewer}
**Comment:** {original comment text}
**Action:** {what was changed}
**Reply posted:** "{reply text}"

### 💬 Answered (no code change)

#### @{reviewer} — {brief topic}
**Comment:** {original comment text}
**Reply posted:** "{explanation}"

### ❌ Declined

#### `{file}:{line}` — @{reviewer}
**Comment:** {original comment text}
**Reason:** {why no change was made}
**Reply posted:** "{reply text}"

---

## Re-review Requested From

- @{reviewer1}
- @{reviewer2}
{or: "No re-review requests sent (no reviewers had unresolved threads)"}
```

---

## Common Mistakes

- **Using thread `.id` for replies** — replies use the comment's `.databaseId` (REST), not the thread `.id` (GraphQL)
- **Using `.databaseId` to resolve** — resolution uses the thread node `.id` (GraphQL)
- **Resolving before replying** — always reply first so the reviewer can see the response
- **Skipping threads** — every unresolved thread must be replied to and resolved, even if no code change was made
- **Extra changes** — only change what the comment asked for; don't refactor surrounding code
- **Re-requesting before all threads resolved** — resolve all threads first, then send re-review requests
