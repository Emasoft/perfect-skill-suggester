---
name: verification-before-completion
description: "Use before reporting any task as done, fixed, passing, or complete — to verify the claim by running it and reading the real output rather than asserting from intent."
---

# Verification before completion

A claim that something works is a hypothesis until it has been run and the output
read. This skill is the check that turns one into the other.

## The procedure

1. **Run it.** Execute the test, the build, the command — whatever would actually
   exercise the behavior. Reasoning about what the code should do is not
   verification, however careful the reasoning was.

2. **Read the real output.** Not the exit code alone, not the part you expected.
   A suite that reports success while skipping the relevant test has told you
   nothing; confirm the test ran.

3. **Report what happened, including what failed.** "Tests pass" when two were
   skipped is a false report. Name what was skipped and why. If part of the task
   is incomplete, say which part — scaling the work down is the requester's call,
   not yours.

4. **When you could not verify something, say so and name what would.** An
   unverified claim stated as fact is the specific failure this exists to
   prevent. "I could not run the integration suite; it needs a live database" is
   a useful report. Silence is not.

## For generated or templated output

A green test suite is not evidence that a **generator** is correct — it only shows
the assertions you thought to write are satisfied. Open the generated artifact and
read it. Placeholders that never substituted, instructions addressed to a component
that does not exist, and references to names that were never emitted all compile,
all pass, and are all visible on sight.

## What does not count as verification

| not verification | why |
|---|---|
| "the edit applied cleanly" | the file changed; nothing says the behavior is right |
| "it compiles" | type-correct and wrong are compatible |
| "the tests I wrote pass" | the untested path is where the bug is |
| "it looks correct" | this is the claim, not evidence for it |
| a summary of your own intent | intent and outcome diverge; that is the whole problem |

## Before you say "done"

- [ ] The change was executed, not just written.
- [ ] The output was read, not just the status.
- [ ] Failures and skips are named explicitly.
- [ ] Anything unverified is flagged as unverified.
- [ ] For generated artifacts: the artifact itself was opened and read.
