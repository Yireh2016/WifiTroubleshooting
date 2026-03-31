---
name: review-pr-rereview
description: Re-reviews a PR after the author has pushed updates in response to a prior review. Tracks which concerns were addressed, partially addressed, or ignored. Reviews only new commits for new issues. Produces an updated recommendation. Saves to .vibeos/review.md. Use when an author has pushed changes since your last review and you need to re-assess.
allowed-tools: Bash(gh *), Bash(git *), Read, Write
---

Re-review a PR where a prior review was already submitted and the author has since pushed updates. Track resolution of prior concerns. Look for new issues in new commits only. Give an updated verdict.

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

## Step 1 — Fetch all review history

```bash
# All reviews on this PR — paginated
gh api repos/$REPO/pulls/$PR_NUMBER/reviews --paginate

# From the response above, find this reviewer's reviews:
# Filter where .user.login == $REVIEWER
# Take the one with the latest submitted_at — that is PRIOR_REVIEW_ID and PRIOR_REVIEW_DATE

# Inline comments from the prior review
gh api repos/$REPO/pulls/$PR_NUMBER/reviews/$PRIOR_REVIEW_ID/comments --paginate \
  --jq '.[] | {path, line: (.line // .original_line), body, id}'

# All current inline comments including replies
gh api repos/$REPO/pulls/$PR_NUMBER/comments --paginate \
  --jq '.[] | {id, in_reply_to_id, author: .user.login, path, line: (.line // .original_line), body, created_at}'

# Current full diff
gh pr diff $PR_NUMBER --repo $REPO

# All commits on the PR — to isolate what changed after the prior review
gh pr view $PR_NUMBER --repo $REPO --json commits \
  --jq '.commits[] | {oid: .oid, message: .messageHeadline, committedDate}'

# CI status
gh pr checks $PR_NUMBER --repo $REPO --json name,state,bucket,description
```

**If no prior review by `$REVIEWER` is found:**
Write to `.vibeos/review.md`:
```
No prior review by @{reviewer} was found on this PR. This should be treated as a first review — run /review-pr-first instead.
```
Then stop.

**If no new commits since PRIOR_REVIEW_DATE:**
Write to `.vibeos/review.md`:
```
No new commits have been pushed since the last review on {PRIOR_REVIEW_DATE}. Nothing to re-review.
```
Then stop.

## Step 2 — Identify new commits

From the commits list, filter to those with `committedDate > PRIOR_REVIEW_DATE`. These are the **new commits** — only these are in scope for new issue detection.

## Step 3 — Map prior concerns to current state

For each concern raised in the prior review (inline comments + review body text):

1. Find the relevant file and line in the current diff or by `Read`-ing the file
2. Check if there's a reply thread on that comment (look for comments with `in_reply_to_id` matching the original comment `id`)
3. Classify:
   - ✓ **Addressed** — the fix is clearly present in the code
   - ⚠️ **Partial** — an attempt was made but the fix is incomplete or differs from what was suggested
   - ✗ **Not addressed** — no change to the code, no reply explaining a conscious decision not to fix

Be fair: if the author made a reasonable alternative fix that solves the underlying problem (even if differently than suggested), mark it ✓ Addressed and note the approach taken.

## Step 4 — Review new commits for new issues

Scope this strictly to the changes introduced in the commits identified in Step 2. Apply the same criteria:

- **Correctness** — does the new code do what it's supposed to?
- **Edge cases** — unhandled null/undefined, off-by-one, empty arrays, concurrent access
- **Security** — injection risks, auth bypasses, exposed secrets, IDOR
- **Tests** — are the new changes tested?
- **Code quality** — naming, duplication, dead code, unnecessary complexity

For any **failing CI checks**, fetch logs:
```bash
gh run list --branch $(gh pr view $PR_NUMBER --repo $REPO --json headRefName --jq .headRefName) \
  --limit 5 --json databaseId,status,conclusion,name
gh run view <RUN_ID> --repo $REPO --log-failed 2>/dev/null
```

**Triage rules (same as first review):**
- 🔴 **Blocking** — would cause harm in production. Must fix.
- 🟡 **Non-blocking** — real issue, not a merge blocker.
- 💡 **Suggestion** — optional improvement.

## Step 5 — Write `.vibeos/review.md`

```markdown
# PR Review: {title}
**Repo:** {org/repo} | **PR:** #{N} | **Author:** @{author}
**Reviewed by:** @{reviewer} | **Date:** YYYY-MM-DD | **Type:** Re-review
**Prior review:** {PRIOR_REVIEW_DATE}
**Recommendation:** ✅ Approve | 🔄 Still needs changes | 💬 Comment

---

## TL;DR

{2-3 sentences. What changed since the last review? Were the prior concerns addressed? Is the PR ready now?}

---

## Prior Concerns — Resolution Status

| Concern | File:Line | Status | Evidence |
|---------|-----------|--------|---------|
| {brief concern summary} | `{file}:{line}` | ✓ Addressed | {commit SHA or current line ref showing the fix} |
| {brief concern summary} | `{file}:{line}` | ⚠️ Partial | {what's still missing or incomplete} |
| {brief concern summary} | `{file}:{line}` | ✗ Not addressed | {still present at file:line — no fix, no reply} |

---

## New Issues (commits after {PRIOR_REVIEW_DATE})

{If none: "No new issues found in the commits since the last review."}

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

## Updated Recommendation

{1-2 paragraphs. Were all prior blockers resolved? Are there new blockers? Clear verdict: approve, request changes, or comment.}

---

## Ready-to-Post Review Comment

```
{follow-up review comment — acknowledge what was fixed, note what still needs attention, give the final verdict. Professional and constructive.}
```
```

## Notes

- Only raise new issues for code introduced **after** the prior review date — don't re-raise existing issues that were already in the first review
- If all prior 🔴 Blocking issues are ✓ Addressed and no new 🔴 issues exist → recommend ✅ Approve
- If prior 🔴 issues remain ✗ Not addressed or ⚠️ Partial → recommend 🔄 Still needs changes
- Be fair: acknowledge good-faith effort even when fixes are imperfect
- If the author explicitly decided not to address something (with a reply explaining why), note their reasoning and whether you accept it
