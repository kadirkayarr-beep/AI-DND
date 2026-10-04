# Retained verification attempts

Before test execution, the first multi-file patch applied new test files but failed the page hunk because hunks were out of file order. The page remained unchanged; the corrected patch was applied after checking its actual contents.

The initial node --check of tests/spellcasting-panel.test.mjs failed with SyntaxError: Invalid regular expression / Unterminated group, caused by a doubled escape in the source-guard regular expression. This test-only syntax error was corrected before the successful frontend test run.

The first API evidence run passed 71 tests, including an imported test class discovered redundantly. A module import removed that accidental duplicate discovery; the final explicit selection passed 36 tests. Both runner archives remain retained.
