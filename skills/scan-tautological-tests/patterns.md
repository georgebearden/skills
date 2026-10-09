# Tautological test patterns

## The question
A test must be able to fail if the behavior it covers is broken. For each suspect ask: **"If I deleted or broke the implementation, would this test fail?"** If not, it is tautological.

## Patterns (tag → what it looks like)

- **mock-echo**: asserts a mock/stub returns what the test just configured it to return. The real code under test never runs, or only passes the value through untouched.
- **reimplemented-logic**: the expected value is computed in the test with the same algorithm as production (or by calling production code), so any bug appears on both sides. Expected values should be hardcoded and independently derived.
- **restated-constant**: asserts constants, config defaults or trivial getters/struct fields against the same literal written in the source.
- **self-snapshot**: snapshot/golden output generated from the current code and treated as the spec, with no human-reviewed expectation.
- **mocks-only**: the unit under test is itself mocked, or so much is mocked that only mocks execute.
- **no-assertion**: no assertion at all, or only "did not throw/panic" when a result exists that could be checked.
- **discarded-result**: results bound to `_` / `let _ =` and never inspected; the test only proves the call compiles and returns.
- **print-only**: output goes to `println!`/`console.log` for a human to eyeball; nothing is asserted.
- **roundtrip-no-compare**: serialize then deserialize (or the reverse) without comparing the decoded value to the original.
- **skipped-empty**: `it.skip(..., () => {})` or `#[ignore]` with an empty body; it counts as a test in totals but exercises nothing.
- **always-true**: assertions that cannot fail (`assert True`, `assert!(true)`, `expect(x).toBe(x)`, `assert_eq!(x, x)`).

## Judgment guidance

- "Did not panic/throw" can be a legitimate test (smoke test, regression for a known crash). Call it **weak**, not tautological, unless a checkable result is being ignored.
- Constants are legitimate to test when the value is a contract (wire format, public API, protocol id). They are tautological when the test just copies the line above.
- Snapshot tests are fine when a human reviewed the snapshot content and the code under test is real; tautological when regenerated blindly.
- Mocking true boundaries (network, clock, filesystem) is correct. Flag only when the mock is the thing being asserted on.
- A test can have an assertion and still be tautological; judge what the assertion is *about*, not whether one exists.
- Verdicts: **tautological** (cannot fail on breakage), **weak** (fails only for trivial breakage), **fine** (drop it).
- A wait whose pattern already appears in the typed input (e.g. waiting for `--max` after typing `--max`) passes without the feature working. The script cannot see this; look for it when reading end-to-end tests.
- `only-not-throws` is low priority when sibling tests assert on the result of the same function: call it weak.
