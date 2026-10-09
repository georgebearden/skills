# skills
skills for agents

## scan-tautological-tests

Finds tests that can't fail. These are tests that still pass when the code they cover is broken, such as asserting a mock returns what it was told to return, or having no assertions at all. Run `/scan-tautological-tests [path]` and it gives you a ranked, report-only list with file, line, pattern and reason. It never edits your tests.
