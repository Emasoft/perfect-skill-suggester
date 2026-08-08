# Memory scope-leak — PROJECT pages carrying machine/user-private data

The PROJECT memory scope (`<git-root>/.claude/project/memory/`) is git-tracked
and PUSHED, so it MUST NOT carry machine/user-private material. The pages below
carry a leak class that belongs in the LOCAL scope
(`~/.claude/projects/<slug>/memory/`, never pushed). An AGENT should DEMOTE
the offending fact to LOCAL (move it / rewrite the page portable). The
janitor only SURFACES — it never edits a page (RULE 0).

## gitignore guards

- PROJECT .claude/project/memory/ is gitignored — it must be TRACKED and pushed (the shared scope is silently excluded from the repo). Since it lives under .claude/ (commonly ignored), add a gitignore exception: `!.claude/project/`, `!.claude/project/memory/`, then `!.claude/project/memory/**`

_Surfaced by the `memory-scope-leak` detector. Resolve by moving the private fact to the LOCAL scope (the harness `# Memory` dir), or by rewriting the PROJECT page to be portable (no usernames/paths/hosts/secrets). Re-run clears this once the leak is gone._
