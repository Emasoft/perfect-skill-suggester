# Changelog

All notable changes to Perfect Skill Suggester will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-23

### Added
- **Comprehensive multi-project skill discovery**: Scan ALL projects from `~/.claude.json`
- New `--all-projects` flag for `pss_discover_skills.py` to index skills across all registered projects
- New `--generate-pss` flag to create `.pss` metadata files for each discovered skill
- Automatic detection and warning for deleted/missing projects
- `.pss` file generation with schema versioning (v1.0.0)

### Changed
- Updated `/pss-reindex-skills` command to support comprehensive discovery
- Enhanced PSS-ARCHITECTURE.md with multi-project scanning documentation
- Improved skill source tracking (now includes project name for project-based skills)

### Technical Details
- Index is a superset of ALL skills ever discovered
- Agent filters suggestions against its context-injected available skills
- Deleted projects are gracefully skipped with warnings
- 248+ skills indexed across multiple projects

## [1.0.0] - 2026-01-23

### Added
- Initial release of Perfect Skill Suggester
- Two-pass skill indexing architecture (Pass 1: keywords, Pass 2: co-usage)
- AI-analyzed keyword extraction from SKILL.md files
- Weighted scoring algorithm with configurable weights
- Three-tier confidence routing (HIGH/MEDIUM/LOW)
- Synonym expansion for common terms
- Typo correction using Levenshtein distance
- Task decomposition for multi-part prompts
- Co-usage relationship boosting
- 16 skill categories for classification
- Pre-compiled binaries for 5 platforms:
  - macOS Apple Silicon (arm64)
  - macOS Intel (x86_64)
  - Linux x86_64
  - Linux ARM64
  - Windows x86_64
- `/pss-status` command for viewing index stats
- `/pss-reindex-skills` command for regenerating index
- Cross-platform Python hook script with auto-detection
- JSON schema validation for .pss files and skill-index.json

### Technical Details
- Native Rust binary (~10ms execution time)
- ~88% precision in skill matching
- Supports 200+ skills in index
