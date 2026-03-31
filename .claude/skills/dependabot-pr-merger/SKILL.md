---
name: dependabot-pr-merger
description: Deep-review a Dependabot pull request before merging — gathers PR context, fetches the package changelog from the web, runs npm audit to surface security vulnerabilities, analyzes where the package is used in the codebase (including transitive deps), evaluates any bot risk assessments (agreeing or disagreeing with reasoning), then produces a structured action plan covering comment resolution, CI/CD fixes, and manual + automated test coverage. Use this skill whenever the user wants to review or merge a dependabot PR, bump a dependency, assess the risk of a version upgrade, check if a dependency update is safe to merge, or asks "can I merge this dependabot PR?". Also trigger when the user passes a branch name like dependabot/npm_and_yarn/... or a GitHub PR URL pointing to a dependency update.
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, WebSearch, WebFetch, AskUserQuestion
---

Deep-review a Dependabot PR — assess risk, analyze impact, and produce a concrete merge plan.

## Usage

```
/dependabot-pr-merger <PR-URL or branch-name>
```

**Examples:**
- `/dependabot-pr-merger https://github.com/org/repo/pull/5294`
- `/dependabot-pr-merger dependabot/npm_and_yarn/main/fast-xml-parser-5.5.6`
- `/dependabot-pr-merger` — auto-detects if current branch is a dependabot branch

---

## Phase 1: Resolve the PR

Determine the PR number and repository from the input.

**If a PR URL is given:**
```bash
# Extract repo and PR number from URL
# e.g. https://github.com/acme/repo/pull/123 → REPO=acme/repo, PR_NUMBER=123
```

**If a branch name is given:**
```bash
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
PR_NUMBER=$(gh pr list --head "$BRANCH" --state open --json number --jq '.[0].number')
```

**If no argument is given:**
```bash
CURRENT_BRANCH=$(git branch --show-current)
PR_NUMBER=$(gh pr list --head "$CURRENT_BRANCH" --state open --json number --jq '.[0].number')
```

If no PR is found, ask the user to provide one.

---

## Phase 2: Gather PR Data

Collect everything — title, body, labels, files, CI status, comments, and security audit.

```bash
REPO=$(gh pr view $PR_NUMBER --json url --jq '.url' | sed 's|https://github.com/||' | cut -d'/' -f1-2)

# Core PR info
gh pr view $PR_NUMBER --json \
  number,title,body,headRefName,baseRefName,url,state,labels,\
  reviews,comments,files,statusCheckRollup

# Inline code comments (most important — often contain bot assessments)
gh api repos/$REPO/pulls/$PR_NUMBER/comments --jq '.[] | {
  id, in_reply_to_id,
  author: .user.login,
  path, line: (.line // .original_line),
  body, created_at
}'

# CI/CD check status
gh pr checks $PR_NUMBER

# For any FAILING checks, fetch the actual failure logs.
# In a monorepo (Nx), a single CI run often has MULTIPLE failing projects — get them all.
gh run list --branch <PR_BRANCH> --limit 5 --json databaseId,status,conclusion,name
# For each failing run, get the full failure log (do not truncate — look for ALL failing test suites):
gh run view <RUN_ID> --log-failed 2>/dev/null
# Scan the entire output for lines like "FAIL", "● ", "snapshot", "× " to identify
# every failing test project and test case name, not just the first one found.
```

**Parse from the PR title:**
- Package name (e.g. `fast-xml-parser`, `@blueprintjs/core`)
- Old version and new version (e.g. `5.4.2 → 5.5.6`)
- Scope/group (if a Dependabot group update, list all packages)

**Run security audit and check what version is actually installed:**
```bash
# Check what version is actually resolved (may differ from what the PR title says
# if it's a transitive dependency or the root package already has a newer version)
npm ls <package-name> 2>/dev/null

# Surface any known CVEs for this package or its transitive deps
npm audit 2>/dev/null | grep -A5 "<package-name>"
# Or for a full picture:
npm audit --json 2>/dev/null | jq '.vulnerabilities | to_entries[] | select(.key == "<package-name>") | {severity: .value.severity, via: .value.via}'
```

Note if the root `package.json` already pins a newer version — the PR may only affect a nested transitive dependency.

---

## Phase 3: Bot Risk Assessment

Scan all comments for automated risk assessments. Look for any bot that leaves structured risk reports — they typically include a RISK level (LOW/MEDIUM/HIGH/CRITICAL), severity badges, CVE references, or score tables.

Extract from each bot comment:
1. Risk level
2. What specifically triggered the assessment
3. Recommended action

Keep these findings — you will evaluate them against your own assessment in Phase 5.

If there are no bot comments, note that and move on.

---

## Phase 4: Fetch the Changelog

Search the web for what changed between the old and new version. Try these sources in order:

1. **GitHub Releases page** — `https://github.com/<owner>/<package>/releases`
2. **CHANGELOG.md in the repo root** — `https://raw.githubusercontent.com/<owner>/<package>/main/CHANGELOG.md`
3. **npm page** — search `<package-name> <version> changelog`
4. **Package homepage** or documentation site

Use `WebSearch` if the repo location is unknown, then `WebFetch` to read the content.

**Extract and summarize:**
- Type of change: patch / minor / major
- Breaking changes (API removed or renamed)
- Security fixes (CVEs patched)
- New features or new transitive dependencies introduced
- Deprecations

If you cannot find a changelog, note this clearly — it increases uncertainty and risk.

---

## Phase 5: Codebase Impact Analysis

Find every place this package is used.

```bash
# Direct imports (JS/TS)
grep -r "from ['\"]<package-name>" --include="*.ts" --include="*.tsx" --include="*.js" -l
grep -r "require(['\"]<package-name>" --include="*.js" --include="*.ts" -l

# For scoped packages like @blueprintjs/core:
grep -r "@blueprintjs/core" --include="*.ts" --include="*.tsx" -l
```

For each file that imports the package:
- Identify which specific exports/APIs are used (`import { X, Y } from 'pkg'`)
- Cross-reference against changelog changes — if the changelog lists a change to `parse()` and the codebase calls `parse()`, flag it explicitly

**Summarize:**
- Number of files using the package
- Which specific APIs are used
- Any APIs that overlap with changelog changes
- Whether usage is test-only or in production code paths

---

## Phase 6: Risk Assessment

Rate the overall risk based on these factors. The highest factor rating sets the overall level.

| Factor | Low | Medium | High | Critical |
|---|---|---|---|---|
| Semver bump | patch | minor | major | major with breaking changes |
| Breaking changes | none | deprecated API used | changed API used | removed API used |
| Security fix | no CVE | low/medium CVE | high CVE | critical CVE |
| Usage breadth | test-only or 0 files | 1–5 files | 6–20 files | 20+ files or core infrastructure |
| Changelog available | yes, clear | yes, partial | missing sections | not found |

Then compare with any bot assessments from Phase 3:
- If you agree: say so and reinforce the reasoning
- If you disagree: state your rating, quote the bot's rating, and explain specifically what the bot got wrong or missed (e.g., "The bot flagged MEDIUM due to a new transitive dependency, but that dependency is only used in a code path this codebase never invokes")

---

## Phase 7: Action Plan

### 7a. Comments to Address

List each open comment with:
- Author and what they asked for
- Your recommendation: address / dismiss / defer
- Brief reasoning

If there are substantial code changes needed, suggest using `/git:address-pr-comments` to work through them.

Note: distinguish between **written review comments** (actionable text) and **pending review requests** (just a reviewer assigned with no comments yet). Don't treat pending requests as open comments.

### 7b. CI/CD Failures

For each failing check, list **every** failing test suite or project found in the logs — in a monorepo there are often multiple. For each one:
- Name of the failing NX project / test suite
- Actual failure message (from the logs fetched in Phase 2)
- Root cause (based on changelog + codebase analysis — e.g., "snapshot mismatch because the package changed SVG path strings")
- Exact fix command (e.g., `npx nx test <project> -- --updateSnapshot`)

### 7c. Test Coverage

**Automated tests** — be specific, not generic:
- List the exact `npx nx test <project>` commands to run for affected areas
- Identify any tests that need updating (e.g., snapshots) and the exact update command
- Suggest new tests only if a previously-untested integration is now at risk

**Manual testing checklist** — list the actual user-facing flows that exercise this package:
- What pages/features to open and what to do
- What to look for (visual regression, error messages, broken functionality)
- Any environment-specific concerns (browser, Node version, feature flags)

### 7d. Merge Recommendation

End with one of:
- **Safe to merge** — low risk, CI passing, no action needed beyond approval
- **Merge after fixes** — list the specific blockers with fix commands
- **Do not merge** — explain what needs to happen first

For security patches (CVE fixes): bias toward merging quickly. If CI is green and the vulnerable API isn't used, that's enough to recommend merging.

---

## Output

Assemble the full report using this format, then **write it to `.vibeos/review.md`**:

```markdown
## Dependabot PR Review: <package> <old> → <new>

### PR Summary
[title, link, files changed, whether PR is already merged]

### Security Audit
[npm audit findings for this package; note if root package.json already has newer version pinned]

### Changelog Highlights
[bullet list of relevant changes]

### Bot Risk Assessments
[each bot's rating + your agreement/disagreement; or "No bot comments found"]

### Codebase Impact
[files using package, APIs used, overlap with changelog]

### Risk Assessment
**Overall: LOW / MEDIUM / HIGH / CRITICAL**
[one sentence per factor that's not obviously low]

### Action Plan

#### Comments to Address
[list, or "No open comments"]

#### CI/CD Fixes
[list with exact commands, or "CI is passing"]

#### Test Coverage
**Automated:**
- `npx nx test <project>` — [why]
**Manual checklist:**
- [ ] [specific flow to test]

#### Merge Recommendation
[Safe to merge / Merge after fixes / Do not merge]
[next steps if any]
```

---

## Important Notes

- Always detect the repository dynamically — never hardcode repo names
- Do not merge or push anything — the output is a plan and report only
- If a changelog is unavailable, increase the risk rating by one level
- For monorepo group updates, repeat the codebase impact analysis for each bumped package
- Always check `npm ls <package>` to confirm what version is actually installed — the PR title may be about a transitive dep that the root already pins at a newer version
