---
name: scan-tautological-tests
description: Scan a repo's existing unit tests for tautological tests (tests that cannot fail when the code under test breaks) and produce a ranked, report-only list with file:line, pattern, confidence and reason. Manual invocation only, via /scan-tautological-tests [path].
disable-model-invocation: true
---

# Scan for tautological tests

A tautological test passes no matter what the implementation does: it asserts a mock returns what it was told to return, re-computes the expected value with the production logic, has no assertion, and so on. They inflate coverage and give false confidence. This skill finds them and reports; it never changes tests.

Read `patterns.md` first. It defines each pattern and the one question used for judgment: **"If the implementation were deleted or broken, would this test fail?"**

## Rules

- Report only. Do not edit, delete or rewrite any test or source file (the optional mutation pass is the one exception and has its own guardrails below). Fixes are a separate step the user approves, because deciding whether to delete or strengthen a test needs their call.
- Scope is the path argument, or the git root if none is given.
- Every reported finding must cite `file:line` and say why in one line. A finding without a reason is noise.

## Workflow

### 1. Detect frameworks and test files
Identify languages and test conventions from manifests and file layout (e.g. `Cargo.toml` + inline `#[cfg(test)]`/`#[test]`; `package.json` with vitest/jest/bun test; `pytest`/`unittest`; Go `_test.go`). Note that some repos mix several; scan all of them. Exclude vendored dirs, `node_modules`, `target`, fixtures and generated files.

### 2. Heuristic pass (cheap, high recall)
Run:

```bash
python3 "$HOME/.claude/skills/scan-tautological-tests/scripts/find_candidates.py" <scope> > "<scratch-dir>/candidates.tsv"
```

`<scratch-dir>` is your session scratchpad directory if the system prompt names one, otherwise a fresh `mktemp -d`; always an absolute path outside the repo, so scan output never lands in the user's working tree. It prints one candidate per line: `file:line<TAB>test name<TAB>pattern tags<TAB>note`, plus a summary of how many tests were scanned. Tags: `no-assertion`, `only-not-throws`, `always-true`, `mock-heavy`, `self-snapshot`, `discarded-result` (results bound to `_`), `print-only`, `roundtrip-no-compare` (serialize then parse without comparing), `skipped-empty` (an `it.skip`/`#[ignore]` stub with no body: a tombstone that reads as coverage). `wait*`/`waitFor*` calls and same-file helpers containing assertions count as assertions. A line with an empty tag column and a note about an assertion in a helper is an unresolved helper (defined in another file): read it, and drop the candidate if the helper asserts. The script skips `#[should_panic]`/`#[ignore]` tests for `no-assertion`. These are *suspects*, not verdicts: the script matches shapes, and shapes have innocent look-alikes. If the script misses a framework you found in step 1, grep for the equivalent shapes yourself using `patterns.md`.

### 3. Judgment pass
For each candidate, read the whole test plus the code it claims to cover, and apply the question from `patterns.md`. Decide: **tautological**, **weak** (can fail, but only for trivial breakage), or **fine** (false positive). Drop the fine ones.

Prioritize when there are many candidates: strongest first (`always-true`, `discarded-result`, `print-only`, `roundtrip-no-compare`, multi-tag), then `no-assertion`, and `only-not-throws` last. Only a test whose body you have read, together with the code it covers, counts as `judged`; a candidate you only skimmed stays `heuristic`. Expect findings to be a small fraction of the candidates; most flags are fine once read.

Also watch for tests of test-only code (mock or fake helpers): they can pass while proving nothing about product behavior, so note that in the reason.

For more than roughly 40 candidates, split by directory and dispatch one subagent per group, giving each `patterns.md`, its candidate lines, and the instruction to return only `file:line | pattern | tautological/weak | one-line reason`. Reading the code under test is what makes the verdict trustworthy, so do not judge from the grep line alone.

### 4. Mutation check (optional, off by default)
Only run if the user asked for it. It is the strongest evidence, since it observes a test surviving a broken implementation, but it edits source.
- Require a clean `git status`; refuse otherwise.
- For each suspect, make one small breaking change to the code under test (flip a condition, return a constant), run only that test, then `git checkout -- <file>` immediately.
- A test that still passes is **mutation-confirmed**. Confirm the tree is clean again at the end.

### 5. Report
Group by confidence, highest first: `mutation-confirmed` > `judged` (read and reasoned) > `heuristic` (matched a shape, not yet read). Within a group, order by how badly the test misleads. Format:

```
## Summary
<N> tests scanned, <K> candidates flagged: <D> read and dropped as fine, <U> not read, <M> reported (<a> mutation-confirmed, <b> judged, <c> heuristic-only). Frameworks: ...
(Unread candidates are not findings; list their file groups so the user can ask for a follow-up.)

## Findings
| Confidence | Verdict | Location | Pattern | Reason |
|---|---|---|---|---|
| judged | tautological | path/to/file.ts:42 | mock-echo | asserts `getUser` mock returns the object it was configured with; real `UserService` never runs |
```

End with a short "next steps" line (e.g. which findings look safe to delete vs. strengthen) but make no changes.
