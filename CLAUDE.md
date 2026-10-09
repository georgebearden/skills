## Unit Tests: No Tautologies

A test must be able to fail if the behavior it covers is broken. Before
finishing any test, ask: "If I deleted or broke the implementation, would
this test fail?" If not, rewrite or remove it.

Avoid:
- Asserting a mock returns what you just told it to return.
- Re-implementing the production logic in the test to compute the expected
  value (use hardcoded, independently-derived expected values).
- Asserting on constants/config/getters that merely restate the code.
- Snapshotting the output of the code under test and treating that as the spec.
- Mocking the unit under test, or mocking so much that only the mocks run.
- Assertions that can't fail (`assert True`, `expect(x).toBe(x)`, checking
  only that no exception was thrown when a result exists to check).

Prefer: testing observable behavior and outputs for known inputs, including
edge cases and error paths, with expected values written by hand. Mock only
true boundaries (network, clock, filesystem).

Verify: watch each new test fail first (or run it against a deliberately
broken implementation) to confirm it can fail.
