# PSS Setup and Verification Checklist

## Table of Contents

- PSS setup and verification checklist items

## Checklist

Use this checklist to verify your PSS workflow is complete:

- [ ] PSS plugin is installed and enabled (`/plugin list` shows it)
- [ ] Skill index has been built at least once (`/pss-reindex-skills`)
- [ ] `/pss-status` shows "Index Status: Exists" with a recent timestamp
- [ ] Skill count in `/pss-status` matches expected number of installed skills
- [ ] Test a natural language prompt and verify suggestions appear
- [ ] HIGH confidence suggestions match your task intent
- [ ] MEDIUM confidence suggestions have relevant evidence
- [ ] After installing new skills, reindex was run again
- [ ] After modifying skill metadata, reindex was run again
- [ ] Skills you authored have `keywords` and `categories` in frontmatter
