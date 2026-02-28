# Adding Elements from External Sources

## Table of Contents

- [4.1 From a local file or folder](#41-from-a-local-file-or-folder)
- [4.2 From an installed plugin](#42-from-an-installed-plugin)
- [4.3 From a marketplace plugin (not installed)](#43-from-a-marketplace-plugin-not-installed)
- [4.4 From a GitHub/git repository URL](#44-from-a-githubgit-repository-url)
- [4.5 From a network shared folder](#45-from-a-network-shared-folder)
- [4.6 From a URL to a raw file](#46-from-a-url-to-a-raw-file)
- [Phase 4 Completion Checklist](#phase-4-completion-checklist)

---

The user, orchestrator, or the agent's own gap analysis may identify elements not in the current index. These can come from ANY source:

**4.1 From a local file or folder**

```
"Add the skill at /path/to/my-custom-skill/SKILL.md"
```

Action:
1. Read the file at the specified path
2. Extract name, description, keywords from frontmatter/content
3. **Evaluate** it using the same criteria as indexed candidates (relevance, compatibility, conflicts)
4. Verify it doesn't conflict with already-selected elements
5. Add to the appropriate section and tier in `.agent.toml`

**4.2 From an installed plugin**

```
"Add the agent from the multi-platform-apps plugin"
```

Action:
1. Search plugin cache: `~/.claude/plugins/cache/*/multi-platform-apps/*/agents/*.md`
2. Also check: `~/.claude/plugins/multi-platform-apps/agents/*.md`
3. Read each available agent's `.md` file
4. **Evaluate** relevance and compatibility — don't blindly add everything
5. Add only the elements that pass evaluation

**4.3 From a marketplace plugin (not installed)**

```
"Add skills from the claude-plugins-validation plugin on the marketplace"
```

Action:
1. Fetch the plugin manifest: `gh api repos/<owner>/<repo>/contents/.claude-plugin/plugin.json`
2. Fetch individual skill/agent files: `gh api repos/<owner>/<repo>/contents/skills/<name>/SKILL.md`
3. **Read and evaluate** each element before adding
4. Add with `source = "plugin:<name>"` in the `[agent]` section comment
5. Note: The plugin must be installed for the agent to actually USE these elements at runtime

**4.4 From a GitHub/git repository URL**

```
"Add the security skill from https://github.com/user/repo"
```

Action:
1. Fetch repo contents: `gh api repos/<owner>/<repo>/contents/skills` or `/agents`
2. Or clone to temp: `git clone --depth 1 <url> /tmp/pss-fetch-<hash>`
3. Read `.md` files in standard locations (skills/, agents/, commands/, rules/)
4. **Evaluate** each element — read the content, check compatibility, detect conflicts
5. Add qualified elements with a comment noting the source URL

**4.5 From a network shared folder**

```
"Add agents from /mnt/shared/team-agents/"
```

Action:
1. List `.md` files in the directory
2. Read each, extract metadata and understand capabilities
3. **Evaluate** against the same criteria as all other candidates
4. Add qualified elements to `.agent.toml`

**4.6 From a URL to a raw file**

```
"Add the skill at https://raw.githubusercontent.com/user/repo/main/skills/my-skill/SKILL.md"
```

Action:
1. Fetch the file content via WebFetch
2. **Read and evaluate** the content — understand what it does, check compatibility
3. Add to `.agent.toml` only if it passes evaluation

**Phase 4 Completion Checklist** (ALL items must be checked before proceeding to Phase 5):

- [ ] Every external element has been read in full (not just accepted based on name/source)
- [ ] Every external element evaluated against Phase 3 criteria (relevance, compatibility, conflicts)
- [ ] No external element added without checking for conflicts with already-selected elements
- [ ] For plugin sources: correct version and path confirmed
- [ ] For GitHub/URL sources: content fetched and read (not assumed from URL alone)
- [ ] For network share sources: file exists and is readable
- [ ] All added external elements assigned to correct tier (primary/secondary/specialized)
- [ ] `agent.source` field value prepared for any plugin-sourced elements

**If no external elements were requested: mark all items N/A and proceed.**
