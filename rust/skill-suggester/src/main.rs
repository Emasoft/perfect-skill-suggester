//! Perfect Skill Suggester (PSS) - High-accuracy skill activation for Claude Code
//!
//! Combines best features from 4 skill activators:
//! - claude-rio: AI-analyzed keywords via Haiku agents
//! - catalyst: Rust binary efficiency (~10ms startup)
//! - LimorAI: 70+ synonym expansion patterns, skills-first ordering
//! - reliable: Weighted scoring, three-tier confidence routing, commitment mechanism
//!
//! # Input (via stdin)
//! JSON with fields: prompt, cwd, sessionId, transcriptPath, permissionMode
//!
//! # Output (via stdout)
//! JSON with additionalContext array containing matched skills with confidence levels
//!
//! # Performance
//! - ~5-15ms total execution time
//! - O(n*k) matching where n=skills, k=keywords per skill

use chrono::Utc;
use clap::Parser;
use colored::Colorize;
use lazy_static::lazy_static;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;
use thiserror::Error;
use tracing::{debug, error, info, warn};

// ============================================================================
// CLI Arguments
// ============================================================================

/// Perfect Skill Suggester (PSS) - High-accuracy skill activation for Claude Code
#[derive(Parser, Debug)]
#[command(name = "pss")]
#[command(version = "2.0.0")]
#[command(about = "High-accuracy skill suggester for Claude Code")]
struct Cli {
    /// Run in incomplete mode for Pass 2 co-usage analysis.
    /// In this mode, co_usage fields are ignored and only keyword
    /// similarity is used to find candidate skills.
    #[arg(long, default_value_t = false)]
    incomplete_mode: bool,

    /// Return only the top N candidates (default: 4, reduced from 10 to save context)
    #[arg(long, default_value_t = 4)]
    top: usize,

    /// Minimum score threshold - skip suggestions below this normalized score (default: 0.5)
    /// Score is normalized to 0.0-1.0 range. Helps filter low-confidence matches.
    #[arg(long, default_value_t = 0.5)]
    min_score: f64,

    /// Output format: "hook" (default) or "json" (raw skill list)
    #[arg(long, default_value = "hook")]
    format: String,

    /// Load and merge .pss files (per-skill matcher files) into the index.
    /// By default, only skill-index.json is used (PSS files are transient).
    #[arg(long, default_value_t = false)]
    load_pss: bool,

    /// Path to skill-index.json. Overrides the default (~/.claude/cache/skill-index.json).
    /// Required on WASM targets where home directory is unavailable.
    /// Can also be set via PSS_INDEX_PATH environment variable.
    #[arg(long)]
    index: Option<String>,

    /// Path to domain-registry.json. Overrides the default (~/.claude/cache/domain-registry.json).
    /// When provided, domain gates are enforced as hard pre-filters.
    /// Can also be set via PSS_REGISTRY_PATH environment variable.
    #[arg(long)]
    registry: Option<String>,

    /// Run in agent-profile mode: score all skills against an agent descriptor
    /// JSON file and return tiered recommendations. The JSON file should contain
    /// name, description, role, duties, tools, domains, and requirements_summary.
    /// Bypasses stdin reading — input comes from the file, not the hook.
    #[arg(long)]
    agent_profile: Option<String>,
}

// ============================================================================
// Constants
// ============================================================================

/// Default index file location
const INDEX_FILE: &str = "skill-index.json";

/// Default domain registry file location
const REGISTRY_FILE: &str = "domain-registry.json";

/// Cache directory name under ~/.claude/
const CACHE_DIR: &str = "cache";

/// Maximum number of suggestions to keep after matching (internal buffer)
/// Set higher than --top default (10) to allow co-usage boosting to surface related skills
const MAX_SUGGESTIONS: usize = 20;

/// PSS file extension for per-skill matcher files
#[allow(dead_code)]  // Used for documentation and future file detection
const PSS_EXTENSION: &str = ".pss";

/// Log file name for activation logging
const ACTIVATION_LOG_FILE: &str = "pss-activations.jsonl";

/// Log directory under ~/.claude/
const LOG_DIR: &str = "logs";

/// Maximum prompt length to store in logs (for privacy)
const MAX_LOG_PROMPT_LENGTH: usize = 100;

/// Maximum number of log entries before rotation (keep logs manageable)
const MAX_LOG_ENTRIES: usize = 10000;

// ============================================================================
// Scoring Weights (from reliable skill activator)
// ============================================================================

/// Scoring weights for different match types
struct MatchWeights {
    /// Skill in matching directory
    directory: i32,
    /// Prompt mentions file path pattern
    path: i32,
    /// Action verb matches skill intent
    intent: i32,
    /// Regex pattern matches
    pattern: i32,
    /// Simple keyword match
    keyword: i32,
    /// First keyword bonus (from LimorAI)
    first_match: i32,
    /// Keyword in original prompt (not just expanded)
    original_bonus: i32,
    /// Maximum capped score to prevent keyword inflation
    capped_max: i32,
}

impl Default for MatchWeights {
    fn default() -> Self {
        Self {
            directory: 5,
            path: 4,
            intent: 4,
            pattern: 3,
            keyword: 2,
            first_match: 10,
            original_bonus: 3,
            capped_max: 30,
        }
    }
}

/// Confidence thresholds (from reliable)
struct ConfidenceThresholds {
    /// Score >= this is HIGH confidence
    high: i32,
    /// Score >= this (but < high) is MEDIUM confidence
    medium: i32,
}

impl Default for ConfidenceThresholds {
    fn default() -> Self {
        Self {
            high: 12,
            medium: 6,
        }
    }
}

// ============================================================================
// Error Types
// ============================================================================

#[derive(Error, Debug)]
pub enum SuggesterError {
    #[error("Failed to read stdin: {0}")]
    StdinRead(#[from] io::Error),

    #[error("Failed to parse input JSON: {0}")]
    InputParse(#[from] serde_json::Error),

    #[error("Failed to read skill index from {path}: {source}")]
    IndexRead { path: PathBuf, source: io::Error },

    #[error("Failed to parse skill index: {0}")]
    IndexParse(String),

    #[error("Home directory not found")]
    NoHomeDir,

    #[error("Skill index not found at {0}")]
    IndexNotFound(PathBuf),
}

// ============================================================================
// PSS File Types (per-skill matcher files)
// ============================================================================

/// PSS file format v1.0 - Per-skill matcher file
#[derive(Debug, Deserialize)]
pub struct PssFile {
    /// PSS format version (must be "1.0")
    pub version: String,

    /// Skill identification
    pub skill: PssSkill,

    /// Matcher keywords and patterns
    pub matchers: PssMatchers,

    /// Scoring hints
    #[serde(default)]
    pub scoring: PssScoring,

    /// Generation metadata
    pub metadata: PssMetadata,
}

/// Skill identification in PSS file
#[derive(Debug, Deserialize)]
pub struct PssSkill {
    /// Skill name (kebab-case)
    pub name: String,

    /// Type: skill, agent, or command
    #[serde(rename = "type")]
    pub skill_type: String,

    /// Source: user, project, or plugin
    #[serde(default)]
    pub source: String,

    /// Relative path to SKILL.md
    #[serde(default)]
    pub path: String,
}

/// Matcher keywords and patterns in PSS file
#[derive(Debug, Deserialize)]
pub struct PssMatchers {
    /// Primary trigger keywords (lowercase)
    pub keywords: Vec<String>,

    /// Intent phrases for matching
    #[serde(default)]
    pub intents: Vec<String>,

    /// Regex patterns for complex matching
    #[serde(default)]
    pub patterns: Vec<String>,

    /// Directory names that suggest this skill
    #[serde(default)]
    pub directories: Vec<String>,

    /// Keywords that should NOT trigger this skill
    #[serde(default)]
    pub negative_keywords: Vec<String>,
}

/// Scoring hints in PSS file
#[derive(Debug, Deserialize, Default)]
pub struct PssScoring {
    /// Element importance tier: primary, secondary, specialized
    #[serde(default)]
    pub tier: String,

    /// Skill category for grouping
    #[serde(default)]
    pub category: String,

    /// Score boost (-10 to +10)
    #[serde(default)]
    pub boost: i32,
}

/// Generation metadata in PSS file
#[derive(Debug, Deserialize)]
pub struct PssMetadata {
    /// How the matchers were generated: ai, manual, hybrid
    pub generated_by: String,

    /// ISO-8601 timestamp of generation
    pub generated_at: String,

    /// Version of the generator tool
    #[serde(default)]
    pub generator_version: String,

    /// SHA-256 hash of SKILL.md for staleness detection
    #[serde(default)]
    pub skill_hash: String,
}

// ============================================================================
// Input Types (from Claude Code hook)
// ============================================================================

/// Input payload from Claude Code UserPromptSubmit hook
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HookInput {
    /// The user's prompt text
    pub prompt: String,

    /// Current working directory
    #[serde(default)]
    pub cwd: String,

    /// Session ID
    #[serde(default)]
    pub session_id: String,

    /// Path to conversation transcript
    #[serde(default)]
    pub transcript_path: String,

    /// Permission mode (ask, auto, etc.)
    #[serde(default)]
    pub permission_mode: String,

    // Context metadata detected by Python hook

    /// Detected platforms from project context (e.g., ["ios", "macos"])
    #[serde(default)]
    pub context_platforms: Vec<String>,

    /// Detected frameworks from project context (e.g., ["swiftui", "react"])
    #[serde(default)]
    pub context_frameworks: Vec<String>,

    /// Detected languages from project context (e.g., ["swift", "rust"])
    #[serde(default)]
    pub context_languages: Vec<String>,

    /// Detected domains from conversation context (e.g., ["writing", "graphics"])
    #[serde(default)]
    pub context_domains: Vec<String>,

    /// Detected tools from conversation context (e.g., ["ffmpeg", "pandoc"])
    #[serde(default)]
    pub context_tools: Vec<String>,

    /// Detected file types from conversation context (e.g., ["pdf", "xlsx"])
    #[serde(default)]
    pub context_file_types: Vec<String>,
}

/// Input for --agent-profile mode: describes an agent to profile against the skill index.
/// The profiler agent writes this JSON file, then invokes the binary with --agent-profile <path>.
#[derive(Debug, Deserialize)]
pub struct AgentProfileInput {
    /// Agent name (e.g., "security-auditor")
    pub name: String,

    /// Full agent description — what the agent does, its specialization
    #[serde(default)]
    pub description: String,

    /// Agent's primary role (e.g., "developer", "tester", "reviewer")
    #[serde(default)]
    pub role: String,

    /// List of duties/responsibilities extracted from the agent definition
    #[serde(default)]
    pub duties: Vec<String>,

    /// Tools the agent uses (e.g., ["grep", "semgrep", "bandit"])
    #[serde(default)]
    pub tools: Vec<String>,

    /// Domain tags (e.g., ["security", "testing"])
    #[serde(default)]
    pub domains: Vec<String>,

    /// Condensed summary of all requirements/design documents
    #[serde(default)]
    pub requirements_summary: String,

    /// Current working directory for project context scanning
    #[serde(default)]
    pub cwd: String,
}

/// Output for --agent-profile mode: tiered skill recommendations
#[derive(Debug, Serialize)]
pub struct AgentProfileOutput {
    /// Agent name
    pub agent: String,

    /// Tiered skill recommendations
    pub skills: AgentProfileSkills,

    /// Complementary agents found via co_usage data
    pub complementary_agents: Vec<String>,

    /// Recommended slash commands for this agent
    pub commands: Vec<AgentProfileCandidate>,

    /// Rules that should be active when this agent runs
    pub rules: Vec<AgentProfileCandidate>,

    /// MCP servers that enhance this agent's capabilities
    pub mcp: Vec<AgentProfileCandidate>,

    /// LSP servers relevant to this agent
    pub lsp: Vec<AgentProfileCandidate>,
}

/// Tiered skill lists for agent profile output
#[derive(Debug, Serialize)]
pub struct AgentProfileSkills {
    /// Core skills (score >= 60% of max)
    pub primary: Vec<AgentProfileCandidate>,

    /// Useful skills (score 30-59% of max)
    pub secondary: Vec<AgentProfileCandidate>,

    /// Niche skills (score 15-29% of max)
    pub specialized: Vec<AgentProfileCandidate>,
}

/// A single skill candidate in the agent profile output
#[derive(Debug, Serialize)]
pub struct AgentProfileCandidate {
    pub name: String,
    pub path: String,
    pub score: f64,
    pub confidence: String,
    pub evidence: Vec<String>,
    pub description: String,
}

/// Typed candidate tuple for skill entries: (name, score, evidence, path, confidence, description, entry_type)
type SkillCandidate = (String, i32, Vec<String>, String, String, String, String);

/// Typed candidate tuple for non-skill entries: (name, score, evidence, path, confidence, description)
type TypedCandidate = (String, i32, Vec<String>, String, String, String);

/// Project context for filtering skills by platform/framework/language/domain/tools/file-types
#[derive(Debug, Clone, Default)]
pub struct ProjectContext {
    /// Detected platforms from project (e.g., ["ios", "macos"])
    pub platforms: Vec<String>,
    /// Detected frameworks from project (e.g., ["swiftui", "react"])
    pub frameworks: Vec<String>,
    /// Detected languages from project (e.g., ["swift", "rust"])
    pub languages: Vec<String>,
    /// Detected domains from conversation (e.g., ["writing", "graphics", "media"])
    pub domains: Vec<String>,
    /// Detected tools from conversation (e.g., ["ffmpeg", "pandoc"])
    pub tools: Vec<String>,
    /// Detected file types from conversation (e.g., ["pdf", "xlsx"])
    pub file_types: Vec<String>,
}

impl ProjectContext {
    /// Create context from HookInput fields
    pub fn from_hook_input(input: &HookInput) -> Self {
        ProjectContext {
            platforms: input.context_platforms.clone(),
            frameworks: input.context_frameworks.clone(),
            languages: input.context_languages.clone(),
            domains: input.context_domains.clone(),
            tools: input.context_tools.clone(),
            file_types: input.context_file_types.clone(),
        }
    }

    /// Merge Rust project scan results into this context, adding items that
    /// are not already present (case-insensitive dedup). This ensures the
    /// scoring boosts in match_skill() benefit from fresh on-disk project data,
    /// not just the hook-provided metadata.
    pub fn merge_scan(&mut self, scan: &ProjectScanResult) {
        for item in &scan.languages {
            if !self.languages.iter().any(|l| l.eq_ignore_ascii_case(item)) {
                self.languages.push(item.clone());
            }
        }
        for item in &scan.frameworks {
            if !self.frameworks.iter().any(|f| f.eq_ignore_ascii_case(item)) {
                self.frameworks.push(item.clone());
            }
        }
        for item in &scan.platforms {
            if !self.platforms.iter().any(|p| p.eq_ignore_ascii_case(item)) {
                self.platforms.push(item.clone());
            }
        }
        for item in &scan.tools {
            if !self.tools.iter().any(|t| t.eq_ignore_ascii_case(item)) {
                self.tools.push(item.clone());
            }
        }
        for item in &scan.file_types {
            if !self.file_types.iter().any(|ft| ft.eq_ignore_ascii_case(item)) {
                self.file_types.push(item.clone());
            }
        }
    }

    /// Check if context is empty (no filtering)
    pub fn is_empty(&self) -> bool {
        self.platforms.is_empty()
            && self.frameworks.is_empty()
            && self.languages.is_empty()
            && self.domains.is_empty()
            && self.tools.is_empty()
            && self.file_types.is_empty()
    }

    /// Calculate context match score for a skill entry
    /// Returns (score_boost, should_filter_out)
    /// - score_boost: +10 for platform match, +8 for framework match, +6 for language match
    /// - should_filter_out: true if skill is platform-specific but context doesn't match
    pub fn match_skill(&self, skill: &SkillEntry) -> (i32, bool) {
        let mut boost = 0i32;
        let mut should_filter = false;

        // Platform matching
        if !skill.platforms.is_empty() && !skill.platforms.contains(&"universal".to_string()) {
            // Skill is platform-specific
            if !self.platforms.is_empty() {
                // We have context - check for match
                let has_platform_match = skill.platforms.iter().any(|p| {
                    self.platforms.iter().any(|cp| cp.to_lowercase() == p.to_lowercase())
                });
                if has_platform_match {
                    boost += 10; // Strong boost for matching platform
                } else {
                    should_filter = true; // Filter out non-matching platform-specific skills
                }
            }
            // If no context, don't filter but don't boost either
        }

        // Framework matching (less strict - don't filter, just boost)
        if !skill.frameworks.is_empty() && !self.frameworks.is_empty() {
            let has_framework_match = skill.frameworks.iter().any(|f| {
                self.frameworks.iter().any(|cf| cf.to_lowercase() == f.to_lowercase())
            });
            if has_framework_match {
                boost += 8; // Good boost for matching framework
            }
        }

        // Language matching (less strict - don't filter, just boost)
        if !skill.languages.is_empty()
            && !skill.languages.contains(&"any".to_string())
            && !self.languages.is_empty()
        {
            let has_lang_match = skill.languages.iter().any(|l| {
                self.languages.iter().any(|cl| cl.to_lowercase() == l.to_lowercase())
            });
            if has_lang_match {
                boost += 6; // Moderate boost for matching language
            }
        }

        // Domain matching (boost for matching domain expertise)
        if !skill.domains.is_empty() && !self.domains.is_empty() {
            let has_domain_match = skill.domains.iter().any(|d| {
                self.domains.iter().any(|cd| cd.to_lowercase() == d.to_lowercase())
            });
            if has_domain_match {
                boost += 8; // Good boost for matching domain
            }
        }

        // Tool matching (strong boost for matching specific tools)
        if !skill.tools.is_empty() && !self.tools.is_empty() {
            let has_tool_match = skill.tools.iter().any(|t| {
                self.tools.iter().any(|ct| ct.to_lowercase() == t.to_lowercase())
            });
            if has_tool_match {
                boost += 12; // Very strong boost for matching tools (specific expertise)
            }
        }

        // File type matching (boost for matching file formats)
        if !skill.file_types.is_empty() && !self.file_types.is_empty() {
            let has_file_type_match = skill.file_types.iter().any(|ft| {
                self.file_types.iter().any(|cft| cft.to_lowercase() == ft.to_lowercase())
            });
            if has_file_type_match {
                boost += 10; // Strong boost for matching file types
            }
        }

        (boost, should_filter)
    }
}

// ============================================================================
// Project Context Scanning (Rust-native, runs on every invocation)
// ============================================================================

/// Result of scanning the project directory for context signals.
/// Detected from config files and directory entries in the project root.
/// Augments the Python hook's context_* fields with fresh, on-disk data
/// because project contents can change at any time (e.g., monorepo migrating
/// from Node.js to Bun, or adding an Objective-C lib to a Swift iOS app).
#[derive(Debug, Default)]
pub struct ProjectScanResult {
    /// Programming languages detected from config files (e.g., "rust", "python", "swift")
    pub languages: Vec<String>,
    /// Frameworks detected from dependency files (e.g., "react", "django", "flutter")
    pub frameworks: Vec<String>,
    /// Target platforms detected from project structure (e.g., "ios", "macos", "mobile")
    pub platforms: Vec<String>,
    /// Build tools, package managers, and dev tools (e.g., "cargo", "bun", "docker")
    pub tools: Vec<String>,
    /// File formats present in the project root (e.g., "svg", "pdf", "json")
    pub file_types: Vec<String>,
}

/// Scan the project directory for context signals by checking config files.
/// This runs on every PSS invocation to capture the current project state.
/// Optimized for speed: one readdir call + targeted stat checks + minimal file reads.
/// Typical execution: <1ms for a normal project directory.
fn scan_project_context(cwd: &str) -> ProjectScanResult {
    let mut result = ProjectScanResult::default();
    let dir = Path::new(cwd);

    // Guard: empty cwd or non-directory path
    if cwd.is_empty() || !dir.is_dir() {
        return result;
    }

    // Collect root directory entry names once (single readdir syscall).
    // All subsequent checks use this list instead of individual stat calls.
    let root_entries: Vec<String> = fs::read_dir(dir)
        .map(|entries| {
            entries
                .flatten()
                .map(|e| e.file_name().to_string_lossy().to_string())
                .collect()
        })
        .unwrap_or_default();

    // Helper: check if any root entry ends with a given suffix
    let has_suffix = |suffix: &str| -> bool {
        root_entries.iter().any(|name| name.ends_with(suffix))
    };

    // Helper: check if a specific filename exists in root
    let has_file = |name: &str| -> bool {
        root_entries.iter().any(|n| n == name)
    };

    // ====================================================================
    // MAINSTREAM LANGUAGES & ECOSYSTEMS
    // ====================================================================

    // -- Rust --
    if has_file("Cargo.toml") {
        result.languages.push("rust".into());
        result.tools.push("cargo".into());
        // Rust embedded: check for .cargo/config.toml with target thumbv* or riscv*
        if dir.join(".cargo").join("config.toml").exists() {
            if let Ok(cargo_cfg) = fs::read_to_string(dir.join(".cargo").join("config.toml")) {
                let cfg_lower = cargo_cfg.to_lowercase();
                if cfg_lower.contains("thumbv") || cfg_lower.contains("riscv")
                    || cfg_lower.contains("cortex") || cfg_lower.contains("no_std")
                {
                    result.platforms.push("embedded".into());
                }
            }
        }
    }

    // -- Python --
    let has_pyproject = has_file("pyproject.toml");
    let has_requirements = has_file("requirements.txt");
    if has_pyproject || has_requirements || has_file("setup.py") || has_file("setup.cfg") {
        result.languages.push("python".into());
        // Parse dependency files to detect frameworks and ML tools
        if has_pyproject {
            if let Ok(content) = fs::read_to_string(dir.join("pyproject.toml")) {
                scan_python_deps(&content, &mut result);
            }
        }
        if has_requirements {
            if let Ok(content) = fs::read_to_string(dir.join("requirements.txt")) {
                scan_python_deps(&content, &mut result);
            }
        }
        if has_file("uv.lock") {
            result.tools.push("uv".into());
        }
        if has_file("Pipfile") {
            result.tools.push("pipenv".into());
        }
        if has_file("conda.yaml") || has_file("environment.yml") || has_file("environment.yaml") {
            result.tools.push("conda".into());
        }
    }

    // -- JavaScript / TypeScript (package.json) --
    if has_file("package.json") {
        if let Ok(content) = fs::read_to_string(dir.join("package.json")) {
            scan_package_json(&content, &root_entries, &mut result);
        }
    }
    if has_file("tsconfig.json") && !result.languages.contains(&"typescript".to_string()) {
        result.languages.push("typescript".into());
    }
    if has_file("deno.json") || has_file("deno.jsonc") {
        result.languages.push("typescript".into());
        result.tools.push("deno".into());
    }

    // -- Go --
    if has_file("go.mod") {
        result.languages.push("go".into());
    }

    // -- Swift / iOS / macOS / watchOS / tvOS --
    if has_file("Package.swift") {
        result.languages.push("swift".into());
    }
    if has_suffix(".xcodeproj") || has_suffix(".xcworkspace") {
        result.languages.push("swift".into());
        result.platforms.push("ios".into());
        result.platforms.push("macos".into());
        result.tools.push("xcode".into());
    }
    if has_file("Podfile") {
        result.tools.push("cocoapods".into());
    }
    // Carthage dependency manager for Apple platforms
    if has_file("Cartfile") {
        result.tools.push("carthage".into());
    }

    // -- Ruby --
    if has_file("Gemfile") {
        result.languages.push("ruby".into());
    }

    // -- Java / Kotlin --
    if has_file("pom.xml") {
        result.languages.push("java".into());
        result.tools.push("maven".into());
    }
    if has_file("build.gradle") || has_file("build.gradle.kts") {
        result.languages.push("java".into());
        result.tools.push("gradle".into());
        if has_file("build.gradle.kts") {
            result.languages.push("kotlin".into());
        }
        // Android detection: presence of AndroidManifest.xml or Android-flavored gradle
        scan_gradle_project(dir, &root_entries, &mut result);
    }

    // -- .NET / C# / F# --
    if has_suffix(".sln") || has_suffix(".csproj") || has_suffix(".fsproj") {
        result.languages.push("csharp".into());
        result.platforms.push("dotnet".into());
        if has_suffix(".fsproj") {
            result.languages.push("fsharp".into());
        }
    }
    // .NET nanoFramework for bare-metal microcontrollers (ESP32, STM32, etc.)
    if has_suffix(".nfproj") {
        result.languages.push("csharp".into());
        result.frameworks.push("nanoframework".into());
        result.platforms.push("embedded".into());
        result.platforms.push("dotnet".into());
    }
    // Meadow (Wilderness Labs) IoT .NET platform
    if (has_file("meadow.config.yaml") || has_file("app.config.yaml"))
        && has_suffix(".csproj") {
            result.frameworks.push("meadow".into());
            result.platforms.push("embedded".into());
        }

    // -- Docker --
    if has_file("Dockerfile")
        || has_file("docker-compose.yml")
        || has_file("docker-compose.yaml")
        || has_file(".dockerignore")
    {
        result.tools.push("docker".into());
    }

    // -- Dart / Flutter --
    if has_file("pubspec.yaml") {
        result.languages.push("dart".into());
        result.frameworks.push("flutter".into());
        // Flutter for embedded: Sony/Toyota embedder uses flutter-elinux
        if has_file("flutter-elinux.yaml") || has_file("flutter_embedder.h") {
            result.platforms.push("embedded".into());
        }
    }

    // -- Elixir --
    if has_file("mix.exs") {
        result.languages.push("elixir".into());
        // Nerves: Elixir IoT/embedded framework
        if let Ok(content) = fs::read_to_string(dir.join("mix.exs")) {
            if content.contains("nerves") {
                result.frameworks.push("nerves".into());
                result.platforms.push("embedded".into());
            }
        }
    }

    // -- PHP --
    if has_file("composer.json") {
        result.languages.push("php".into());
    }

    // -- Zig --
    if has_file("build.zig") {
        result.languages.push("zig".into());
    }

    // -- Haskell --
    if has_file("stack.yaml") || has_suffix(".cabal") {
        result.languages.push("haskell".into());
    }

    // -- Scala --
    if has_file("build.sbt") {
        result.languages.push("scala".into());
        result.tools.push("sbt".into());
    }

    // -- Nim --
    if has_suffix(".nimble") || has_file("nim.cfg") {
        result.languages.push("nim".into());
    }

    // -- Lua --
    if has_file(".luacheckrc") || has_suffix(".rockspec") {
        result.languages.push("lua".into());
    }

    // -- R --
    if has_file("DESCRIPTION") && has_file("NAMESPACE") {
        result.languages.push("r".into());
    }

    // -- Julia --
    if has_file("Project.toml") && has_file("Manifest.toml") {
        result.languages.push("julia".into());
    }

    // -- OCaml --
    if has_file("dune-project") || has_suffix(".opam") {
        result.languages.push("ocaml".into());
    }

    // -- Erlang --
    if has_file("rebar.config") || has_file("rebar3.config") {
        result.languages.push("erlang".into());
    }

    // -- Clojure --
    if has_file("project.clj") || has_file("deps.edn") {
        result.languages.push("clojure".into());
    }

    // -- Perl --
    if has_file("Makefile.PL") || has_file("cpanfile") || has_file("dist.ini") {
        result.languages.push("perl".into());
    }

    // -- Objective-C detection (from .m/.mm files in root entries) --
    if root_entries.iter().any(|n| n.ends_with(".m") || n.ends_with(".mm")) {
        result.languages.push("objective-c".into());
    }

    // ====================================================================
    // EMBEDDED SYSTEMS, FIRMWARE & RTOS
    // ====================================================================

    // -- PlatformIO (universal embedded IDE/build system) --
    if has_file("platformio.ini") {
        result.tools.push("platformio".into());
        result.platforms.push("embedded".into());
        // Parse platformio.ini to detect board/framework
        if let Ok(content) = fs::read_to_string(dir.join("platformio.ini")) {
            scan_platformio_ini(&content, &mut result);
        }
    }

    // -- Arduino --
    if has_suffix(".ino") {
        result.languages.push("cpp".into());
        result.frameworks.push("arduino".into());
        result.platforms.push("embedded".into());
    }

    // -- Zephyr RTOS --
    if has_file("prj.conf") && (has_file("CMakeLists.txt") || has_file("west.yml")) {
        result.frameworks.push("zephyr".into());
        result.platforms.push("embedded".into());
        result.tools.push("west".into());
    }
    if has_file("west.yml") {
        result.tools.push("west".into());
    }

    // -- FreeRTOS --
    if has_file("FreeRTOSConfig.h") {
        result.frameworks.push("freertos".into());
        result.platforms.push("embedded".into());
    }

    // -- Mbed OS --
    if has_file("mbed_app.json") || has_file("mbed-os.lib") || has_file("mbed_settings.py") {
        result.frameworks.push("mbed-os".into());
        result.platforms.push("embedded".into());
    }

    // -- Azure RTOS (ThreadX) --
    if root_entries.iter().any(|n| n.contains("threadx") || n.contains("azure_rtos")) {
        result.frameworks.push("azure-rtos".into());
        result.platforms.push("embedded".into());
    }

    // -- RIOT OS (ultra-low-power IoT) --
    if has_file("Makefile.include") && root_entries.iter().any(|n| n.contains("RIOT")) {
        result.frameworks.push("riot-os".into());
        result.platforms.push("embedded".into());
    }

    // -- STM32 (STMicroelectronics) --
    if has_suffix(".ioc") {
        result.tools.push("stm32cubemx".into());
        result.platforms.push("embedded".into());
        result.languages.push("c".into());
    }
    if has_file(".cproject") || has_file(".mxproject") {
        result.tools.push("stm32cubeide".into());
        result.platforms.push("embedded".into());
    }

    // -- Keil MDK-ARM --
    if has_suffix(".uvprojx") || has_suffix(".uvproj") {
        result.tools.push("keil-mdk".into());
        result.platforms.push("embedded".into());
        result.languages.push("c".into());
    }

    // -- Microchip MPLAB X --
    if has_suffix(".mc3") || has_suffix(".mcp") || has_suffix(".X") {
        result.tools.push("mplab-x".into());
        result.platforms.push("embedded".into());
        result.languages.push("c".into());
    }

    // -- IAR Embedded Workbench --
    if has_suffix(".ewp") || has_suffix(".eww") {
        result.tools.push("iar".into());
        result.platforms.push("embedded".into());
    }

    // -- Texas Instruments Code Composer Studio --
    if has_file(".ccsproject") || has_suffix(".ccxml") {
        result.tools.push("ti-ccs".into());
        result.platforms.push("embedded".into());
    }

    // -- NXP MCUXpresso --
    if has_file(".mcuxpressoide") {
        result.tools.push("mcuxpresso".into());
        result.platforms.push("embedded".into());
    }

    // -- OpenOCD debugger --
    if has_file("openocd.cfg") {
        result.tools.push("openocd".into());
        result.platforms.push("embedded".into());
    }

    // -- JTAG / SWD debug configuration --
    if has_suffix(".jlink") || has_suffix(".svd") {
        result.tools.push("jtag".into());
        result.platforms.push("embedded".into());
    }

    // -- Device Tree (Linux kernel / Zephyr) --
    if has_suffix(".dts") || has_suffix(".dtsi") || has_file("devicetree.overlay") {
        result.tools.push("device-tree".into());
        result.platforms.push("embedded".into());
    }

    // -- Kconfig / Linux kernel build system --
    if has_file("Kconfig") || has_file(".config") {
        result.tools.push("kconfig".into());
    }

    // -- Linker scripts --
    if has_suffix(".ld") || has_suffix(".lds") || has_suffix(".icf") {
        result.platforms.push("embedded".into());
    }

    // ====================================================================
    // EMBEDDED LINUX DISTRIBUTIONS
    // ====================================================================

    // -- Yocto Project --
    if dir.join("conf").join("local.conf").exists()
        || dir.join("conf").join("bblayers.conf").exists()
        || has_suffix(".bb")
        || has_suffix(".bbappend")
    {
        result.tools.push("yocto".into());
        result.frameworks.push("openembedded".into());
        result.platforms.push("embedded-linux".into());
    }

    // -- Buildroot --
    if has_file("Config.in") && has_file("Makefile") && !has_file("package") {
        // Buildroot has Config.in + Makefile at root
        // More reliable: check for buildroot-specific files
    }
    if has_file("buildroot-config") || has_file(".br2-external.mk") {
        result.tools.push("buildroot".into());
        result.platforms.push("embedded-linux".into());
    }

    // -- OpenWrt (routers/gateways) --
    if has_file("feeds.conf") || has_file("feeds.conf.default") {
        result.tools.push("openwrt".into());
        result.platforms.push("embedded-linux".into());
    }

    // ====================================================================
    // MOBILE PLATFORMS
    // ====================================================================

    // -- Android (detected from AndroidManifest.xml or gradle android plugin) --
    if has_file("AndroidManifest.xml") || dir.join("app").join("src").is_dir() {
        result.platforms.push("android".into());
        result.languages.push("java".into());
        result.languages.push("kotlin".into());
    }
    // Android NDK (native C/C++ for Android)
    if (has_file("Android.mk") || has_file("Application.mk") || has_file("CMakeLists.txt"))
        && (has_file("AndroidManifest.xml") || !has_file("jni")) {
            // Only tag android-ndk if Android project context exists
        }
    if dir.join("jni").is_dir() {
        result.tools.push("android-ndk".into());
        result.platforms.push("android".into());
    }

    // -- React Native / Expo (detected in scan_package_json, add platform) --
    // Platform tags are added in scan_package_json via framework detection

    // -- Kotlin Multiplatform --
    if has_file("build.gradle.kts") {
        if let Ok(content) = fs::read_to_string(dir.join("build.gradle.kts")) {
            if content.contains("kotlin(\"multiplatform\")") || content.contains("KotlinMultiplatform") {
                result.frameworks.push("kotlin-multiplatform".into());
                result.platforms.push("mobile".into());
            }
        }
    }

    // ====================================================================
    // AUTOMOTIVE & TRANSPORTATION
    // ====================================================================

    // -- AUTOSAR (Classic & Adaptive) --
    if has_suffix(".arxml") || root_entries.iter().any(|n| n.contains("autosar")) {
        result.frameworks.push("autosar".into());
        result.platforms.push("automotive".into());
    }

    // -- CAN / CAN FD bus --
    if has_suffix(".dbc") || has_suffix(".kcd") {
        result.tools.push("can-bus".into());
        result.platforms.push("automotive".into());
    }

    // -- Vector tools (CANoe/CANalyzer) --
    if has_suffix(".cfg") && root_entries.iter().any(|n| n.contains("canoe") || n.contains("canalyzer")) {
        result.tools.push("vector-canoe".into());
        result.platforms.push("automotive".into());
    }

    // -- dSPACE HIL testing --
    if has_suffix(".sdf") && root_entries.iter().any(|n| n.contains("dspace")) {
        result.tools.push("dspace".into());
        result.platforms.push("automotive".into());
    }

    // -- MISRA C/C++ (usually indicated by MISRA config files) --
    if root_entries.iter().any(|n| n.to_lowercase().contains("misra")) {
        result.tools.push("misra".into());
        result.platforms.push("safety-critical".into());
    }

    // ====================================================================
    // INDUSTRIAL AUTOMATION & PLC
    // ====================================================================

    // -- CODESYS (IEC 61131-3 PLC programming) --
    if has_suffix(".project") && root_entries.iter().any(|n| n.to_lowercase().contains("codesys")) {
        result.tools.push("codesys".into());
        result.platforms.push("industrial".into());
    }

    // -- Beckhoff TwinCAT --
    if has_suffix(".tsproj") || has_suffix(".tmc") {
        result.tools.push("twincat".into());
        result.platforms.push("industrial".into());
    }

    // -- IEC 61131-3 Structured Text --
    if has_suffix(".st") || has_suffix(".scl") {
        result.languages.push("structured-text".into());
        result.platforms.push("industrial".into());
    }

    // -- Siemens TIA Portal --
    if has_suffix(".ap17") || has_suffix(".ap16") || has_suffix(".ap15") {
        result.tools.push("tia-portal".into());
        result.platforms.push("industrial".into());
    }

    // ====================================================================
    // ROBOTICS, DRONES & MOTION
    // ====================================================================

    // -- ROS 2 (Robot Operating System) --
    if has_file("package.xml") || has_file("colcon.meta") {
        if let Ok(content) = fs::read_to_string(dir.join("package.xml")) {
            if content.contains("ament") || content.contains("catkin") || content.contains("rosidl") {
                result.frameworks.push("ros2".into());
                result.platforms.push("robotics".into());
            }
        } else {
            // colcon.meta alone is strong ROS indicator
            if has_file("colcon.meta") {
                result.frameworks.push("ros2".into());
                result.platforms.push("robotics".into());
            }
        }
    }

    // -- PX4 Autopilot / ArduPilot (drones) --
    if has_file("ArduPilot.parm") || root_entries.iter().any(|n| n.contains("ardupilot")) {
        result.frameworks.push("ardupilot".into());
        result.platforms.push("robotics".into());
    }
    if root_entries.iter().any(|n| n.contains("px4")) {
        result.frameworks.push("px4".into());
        result.platforms.push("robotics".into());
    }

    // ====================================================================
    // FPGA & HDL (Hardware Description Languages)
    // ====================================================================

    // -- VHDL --
    if has_suffix(".vhd") || has_suffix(".vhdl") {
        result.languages.push("vhdl".into());
        result.platforms.push("fpga".into());
    }

    // -- Verilog / SystemVerilog --
    if has_suffix(".v") || has_suffix(".sv") || has_suffix(".svh") {
        result.languages.push("verilog".into());
        result.platforms.push("fpga".into());
    }

    // -- Xilinx Vivado --
    if has_suffix(".xpr") || has_suffix(".xdc") {
        result.tools.push("vivado".into());
        result.platforms.push("fpga".into());
    }

    // -- Intel Quartus --
    if has_suffix(".qpf") || has_suffix(".qsf") || has_suffix(".sof") {
        result.tools.push("quartus".into());
        result.platforms.push("fpga".into());
    }

    // -- Lattice Diamond / Radiant --
    if has_suffix(".ldf") || has_suffix(".lpf") {
        result.tools.push("lattice".into());
        result.platforms.push("fpga".into());
    }

    // ====================================================================
    // GPU COMPUTING, HPC & PARALLEL
    // ====================================================================

    // -- CUDA --
    if has_suffix(".cu") || has_suffix(".cuh") {
        result.languages.push("cuda".into());
        result.tools.push("nvidia-cuda".into());
        result.platforms.push("gpu".into());
    }

    // -- OpenCL --
    if has_suffix(".cl") {
        result.languages.push("opencl".into());
        result.platforms.push("gpu".into());
    }

    // -- Metal shaders (Apple GPU) --
    if has_suffix(".metal") {
        result.languages.push("metal".into());
        result.platforms.push("gpu".into());
    }

    // -- GLSL / HLSL shaders --
    if has_suffix(".glsl") || has_suffix(".vert") || has_suffix(".frag") {
        result.languages.push("glsl".into());
        result.platforms.push("gpu".into());
    }
    if has_suffix(".hlsl") {
        result.languages.push("hlsl".into());
        result.platforms.push("gpu".into());
    }

    // -- WGSL (WebGPU shading language) --
    if has_suffix(".wgsl") {
        result.languages.push("wgsl".into());
        result.platforms.push("gpu".into());
    }

    // -- OpenMPI / MPI parallel computing --
    if root_entries.iter().any(|n| n.contains("mpi") && n.contains("hostfile"))
        || has_file("hostfile")
    {
        result.tools.push("openmpi".into());
        result.platforms.push("hpc".into());
    }

    // ====================================================================
    // WIRELESS, SDR & RADIO
    // ====================================================================

    // -- GNU Radio --
    if has_suffix(".grc") {
        result.tools.push("gnuradio".into());
        result.platforms.push("sdr".into());
    }

    // -- Bluetooth / BLE --
    if root_entries.iter().any(|n| n.to_lowercase().contains("bluetooth") || n.to_lowercase().contains("nimble")) {
        result.tools.push("bluetooth".into());
        result.platforms.push("wireless".into());
    }

    // -- LoRaWAN --
    if root_entries.iter().any(|n| n.to_lowercase().contains("lorawan") || n.to_lowercase().contains("lora")) {
        result.tools.push("lorawan".into());
        result.platforms.push("wireless".into());
    }

    // -- Zigbee / Thread / Matter --
    if root_entries.iter().any(|n| {
        let l = n.to_lowercase();
        l.contains("zigbee") || l.contains("thread") || l.contains("matter")
    }) {
        result.tools.push("zigbee".into());
        result.platforms.push("wireless".into());
    }

    // ====================================================================
    // SECURITY, CRYPTOGRAPHY & REVERSE ENGINEERING
    // ====================================================================

    // -- Ghidra reverse engineering --
    if has_suffix(".gpr") || has_suffix(".rep") {
        result.tools.push("ghidra".into());
        result.platforms.push("reverse-engineering".into());
    }

    // -- IDA Pro --
    if has_suffix(".idb") || has_suffix(".i64") {
        result.tools.push("ida-pro".into());
        result.platforms.push("reverse-engineering".into());
    }

    // -- Hardware security: TPM / HSM config --
    if root_entries.iter().any(|n| n.to_lowercase().contains("tpm") || n.to_lowercase().contains("hsm")) {
        result.tools.push("hardware-security".into());
        result.platforms.push("security".into());
    }

    // ====================================================================
    // 3D PRINTING & FABRICATION
    // ====================================================================

    // -- Marlin firmware --
    if has_file("Configuration.h") && has_file("Configuration_adv.h") {
        result.frameworks.push("marlin".into());
        result.platforms.push("3d-printing".into());
    }

    // -- Klipper firmware --
    if has_file("printer.cfg") || has_file("klipper.cfg") {
        result.frameworks.push("klipper".into());
        result.platforms.push("3d-printing".into());
    }

    // -- G-code files --
    if has_suffix(".gcode") || has_suffix(".nc") {
        result.platforms.push("3d-printing".into());
    }

    // ====================================================================
    // UI FRAMEWORKS (EMBEDDED & DESKTOP)
    // ====================================================================

    // -- Qt (C++/QML) --
    if has_suffix(".pro") || has_suffix(".pri") || has_suffix(".qbs") {
        result.frameworks.push("qt".into());
        result.languages.push("cpp".into());
    }
    if has_suffix(".qml") {
        result.languages.push("qml".into());
        result.frameworks.push("qt".into());
    }
    // Qt for MCUs (resource-constrained embedded UI)
    if has_file("qmlproject") || root_entries.iter().any(|n| n.contains("qtformcu")) {
        result.frameworks.push("qt-for-mcu".into());
        result.platforms.push("embedded".into());
    }

    // -- LVGL (Light and Versatile Graphics Library for MCUs) --
    if has_file("lv_conf.h") || root_entries.iter().any(|n| n == "lvgl") {
        result.frameworks.push("lvgl".into());
        result.platforms.push("embedded".into());
    }

    // -- TouchGFX (STMicroelectronics embedded UI) --
    if has_suffix(".touchgfx") {
        result.frameworks.push("touchgfx".into());
        result.platforms.push("embedded".into());
    }

    // -- Avalonia UI (.NET cross-platform) --
    if root_entries.iter().any(|n| n.to_lowercase().contains("avalonia")) {
        result.frameworks.push("avalonia".into());
    }

    // ====================================================================
    // INSTRUMENTATION & SCIENTIFIC
    // ====================================================================

    // -- LabVIEW --
    if has_suffix(".vi") || has_suffix(".lvproj") || has_suffix(".lvlib") {
        result.tools.push("labview".into());
        result.languages.push("labview-g".into());
        result.platforms.push("instrumentation".into());
    }

    // -- MATLAB / Simulink --
    if has_suffix(".mlx") || has_suffix(".slx") || has_suffix(".mdl") {
        result.tools.push("matlab".into());
        result.languages.push("matlab".into());
        if has_suffix(".slx") || has_suffix(".mdl") {
            result.tools.push("simulink".into());
        }
    }

    // -- Jupyter notebooks --
    if has_suffix(".ipynb") {
        result.tools.push("jupyter".into());
    }

    // ====================================================================
    // ASSEMBLY & LOW-LEVEL LANGUAGES
    // ====================================================================

    // -- Assembly --
    if has_suffix(".asm") || has_suffix(".s") || has_suffix(".S") {
        result.languages.push("assembly".into());
    }

    // -- Ada / SPARK --
    if has_suffix(".adb") || has_suffix(".ads") || has_suffix(".gpr") {
        result.languages.push("ada".into());
        // SPARK subset of Ada for safety-critical
        if root_entries.iter().any(|n| n.to_lowercase().contains("spark")) {
            result.frameworks.push("spark-ada".into());
            result.platforms.push("safety-critical".into());
        }
    }

    // -- Forth --
    if has_suffix(".fs") || has_suffix(".fth") || has_suffix(".4th") {
        // .fs conflicts with F# — only tag Forth if no .fsproj exists
        if !has_suffix(".fsproj") || has_suffix(".fth") || has_suffix(".4th") {
            result.languages.push("forth".into());
        }
    }

    // ====================================================================
    // CI/CD & DEVOPS
    // ====================================================================

    // -- GitHub Actions (subdirectory check - separate stat call) --
    if dir.join(".github").join("workflows").is_dir() {
        result.tools.push("github-actions".into());
    }

    // -- GitLab CI --
    if has_file(".gitlab-ci.yml") {
        result.tools.push("gitlab-ci".into());
    }

    // -- Jenkins --
    if has_file("Jenkinsfile") {
        result.tools.push("jenkins".into());
    }

    // -- CircleCI --
    if dir.join(".circleci").join("config.yml").exists() {
        result.tools.push("circleci".into());
    }

    // -- Travis CI --
    if has_file(".travis.yml") {
        result.tools.push("travis-ci".into());
    }

    // -- Terraform --
    if has_suffix(".tf") {
        result.tools.push("terraform".into());
        result.platforms.push("cloud".into());
    }

    // -- Pulumi --
    if has_file("Pulumi.yaml") || has_file("Pulumi.yml") {
        result.tools.push("pulumi".into());
        result.platforms.push("cloud".into());
    }

    // -- Kubernetes --
    if has_file("skaffold.yaml") || !has_file("helm") {
        // More reliable K8s detection
    }
    if has_file("skaffold.yaml") || has_file("Chart.yaml") {
        result.tools.push("kubernetes".into());
        result.platforms.push("cloud".into());
    }
    if has_file("Chart.yaml") {
        result.tools.push("helm".into());
    }

    // -- Vagrant --
    if has_file("Vagrantfile") {
        result.tools.push("vagrant".into());
    }

    // -- Ansible --
    if has_file("ansible.cfg") || has_file("playbook.yml") || has_file("playbook.yaml") {
        result.tools.push("ansible".into());
    }

    // ====================================================================
    // NETWORKING & SERVER INFRASTRUCTURE
    // ====================================================================

    // -- DPDK (Data Plane Development Kit) --
    if root_entries.iter().any(|n| n.to_lowercase().contains("dpdk")) {
        result.tools.push("dpdk".into());
        result.platforms.push("networking".into());
    }

    // -- OpenBMC (server management) --
    if root_entries.iter().any(|n| n.to_lowercase().contains("openbmc")) {
        result.tools.push("openbmc".into());
        result.platforms.push("server-management".into());
    }

    // -- Protocol Buffers / gRPC --
    if has_suffix(".proto") {
        result.tools.push("protobuf".into());
    }

    // -- GraphQL --
    if has_suffix(".graphql") || has_suffix(".gql") {
        result.tools.push("graphql".into());
    }

    // ====================================================================
    // BUILD TOOLS & GENERAL
    // ====================================================================

    // -- C / C++ (CMake, Make, Meson, Bazel) --
    if has_file("CMakeLists.txt") {
        result.languages.push("c".into());
        result.languages.push("cpp".into());
        result.tools.push("cmake".into());
    }
    if has_file("Makefile") || has_file("makefile") || has_file("GNUmakefile") {
        result.tools.push("make".into());
    }
    if has_file("meson.build") {
        result.tools.push("meson".into());
        result.languages.push("c".into());
        result.languages.push("cpp".into());
    }
    if has_file("BUILD") || has_file("BUILD.bazel") || has_file("WORKSPACE") || has_file("WORKSPACE.bazel") {
        result.tools.push("bazel".into());
    }
    if has_file("SConstruct") || has_file("SConscript") {
        result.tools.push("scons".into());
    }
    if has_file("premake5.lua") || has_file("premake4.lua") {
        result.tools.push("premake".into());
    }
    if has_file("xmake.lua") {
        result.tools.push("xmake".into());
    }

    // -- Conan (C/C++ package manager) --
    if has_file("conanfile.py") || has_file("conanfile.txt") {
        result.tools.push("conan".into());
    }

    // -- vcpkg (C/C++ package manager) --
    if has_file("vcpkg.json") {
        result.tools.push("vcpkg".into());
    }

    // ====================================================================
    // JAVA EMBEDDED & SPECIALIZED
    // ====================================================================

    // -- Java Card (smartcard development) --
    if has_suffix(".cap") || root_entries.iter().any(|n| n.to_lowercase().contains("javacard")) {
        result.languages.push("java".into());
        result.frameworks.push("javacard".into());
        result.platforms.push("smartcard".into());
    }

    // -- MicroEJ VEE (Java for MCUs) --
    if root_entries.iter().any(|n| n.to_lowercase().contains("microej")) {
        result.languages.push("java".into());
        result.frameworks.push("microej".into());
        result.platforms.push("embedded".into());
    }

    // -- AOSP / Android Automotive OS --
    if has_file("Android.bp") || has_file("build.soong") {
        result.tools.push("aosp".into());
        result.platforms.push("android".into());
    }

    // ====================================================================
    // MEDICAL, SAFETY-CRITICAL & AEROSPACE
    // ====================================================================

    // -- Safety-critical standards markers --
    if root_entries.iter().any(|n| {
        let l = n.to_lowercase();
        l.contains("iec62304") || l.contains("iec_62304")
            || l.contains("iso13485") || l.contains("iso_13485")
            || l.contains("iso14971") || l.contains("iso_14971")
    }) {
        result.platforms.push("medical".into());
        result.platforms.push("safety-critical".into());
    }
    if root_entries.iter().any(|n| {
        let l = n.to_lowercase();
        l.contains("iso26262") || l.contains("iso_26262")
            || l.contains("asil") || l.contains("do-178")
    }) {
        result.platforms.push("safety-critical".into());
    }

    // ====================================================================
    // WEBASSEMBLY
    // ====================================================================
    if has_suffix(".wasm") || has_suffix(".wat") || has_suffix(".wast") {
        result.languages.push("wasm".into());
        result.platforms.push("webassembly".into());
    }

    // ====================================================================
    // GAME DEVELOPMENT
    // ====================================================================

    // -- Unity --
    if !has_file("ProjectSettings") {
        // Unity detection via Assets directory
    }
    if dir.join("Assets").is_dir() && dir.join("ProjectSettings").is_dir() {
        result.tools.push("unity".into());
        result.languages.push("csharp".into());
        result.platforms.push("gamedev".into());
    }

    // -- Unreal Engine --
    if has_suffix(".uproject") {
        result.tools.push("unreal-engine".into());
        result.languages.push("cpp".into());
        result.platforms.push("gamedev".into());
    }

    // -- Godot --
    if has_file("project.godot") {
        result.tools.push("godot".into());
        result.platforms.push("gamedev".into());
    }

    // -- Bevy (Rust game engine) --
    if has_file("Cargo.toml") {
        if let Ok(content) = fs::read_to_string(dir.join("Cargo.toml")) {
            if content.contains("bevy") {
                result.frameworks.push("bevy".into());
                result.platforms.push("gamedev".into());
            }
        }
    }

    // ====================================================================
    // OTA, DEPLOYMENT & SIGNING
    // ====================================================================

    // -- Mender.io OTA --
    if (has_file("mender.conf") || !has_file("mender-artifact"))
        && has_file("mender.conf") {
            result.tools.push("mender".into());
            result.platforms.push("embedded".into());
        }

    // -- SWUpdate --
    if has_file("sw-description") {
        result.tools.push("swupdate".into());
        result.platforms.push("embedded".into());
    }

    // -- RAUC --
    if has_file("system.conf") && root_entries.iter().any(|n| n.contains("rauc")) {
        result.tools.push("rauc".into());
        result.platforms.push("embedded".into());
    }

    // ====================================================================
    // FILE TYPE DETECTION & CLEANUP
    // ====================================================================

    // -- File type detection from root directory entries --
    scan_root_file_types(&root_entries, &mut result);

    // Deduplicate all vectors while preserving insertion order
    dedup_vec(&mut result.languages);
    dedup_vec(&mut result.frameworks);
    dedup_vec(&mut result.platforms);
    dedup_vec(&mut result.tools);
    dedup_vec(&mut result.file_types);

    result
}

/// Parse a Gradle project for Android/Kotlin/Spring indicators.
/// Reads build.gradle(.kts) looking for common plugins and dependencies.
fn scan_gradle_project(dir: &Path, root_entries: &[String], result: &mut ProjectScanResult) {
    // Try to read the gradle build file (prefer .kts, fall back to .groovy)
    let gradle_path = if root_entries.iter().any(|n| n == "build.gradle.kts") {
        dir.join("build.gradle.kts")
    } else {
        dir.join("build.gradle")
    };

    let content = match fs::read_to_string(&gradle_path) {
        Ok(c) => c.to_lowercase(),
        Err(_) => return,
    };

    // Android detection via AGP plugin or AndroidManifest
    if content.contains("com.android.application")
        || content.contains("com.android.library")
        || root_entries.iter().any(|n| n == "AndroidManifest.xml")
        || dir.join("app/src/main/AndroidManifest.xml").exists()
    {
        result.platforms.push("android".into());
        result.frameworks.push("android-sdk".into());
    }

    // Kotlin Multiplatform
    if content.contains("kotlin(\"multiplatform\")")
        || content.contains("org.jetbrains.kotlin.multiplatform")
    {
        result.languages.push("kotlin".into());
        result.frameworks.push("kotlin-multiplatform".into());
    }

    // Spring Boot
    if content.contains("org.springframework.boot") {
        result.frameworks.push("spring-boot".into());
    }

    // Quarkus
    if content.contains("io.quarkus") {
        result.frameworks.push("quarkus".into());
    }

    // Micronaut
    if content.contains("io.micronaut") {
        result.frameworks.push("micronaut".into());
    }

    // AOSP / Android native
    if content.contains("android.ndk") || content.contains("com.android.tools.build") {
        result.tools.push("android-ndk".into());
    }

    // Compose
    if content.contains("compose") {
        result.frameworks.push("jetpack-compose".into());
    }
}

/// Parse platformio.ini content to detect board family, framework, and platform.
/// PlatformIO INI uses `[env:xxx]` sections with `board`, `framework`, `platform` keys.
fn scan_platformio_ini(content: &str, result: &mut ProjectScanResult) {
    let lower = content.to_lowercase();

    // Detect frameworks declared in platformio.ini
    let pio_frameworks: &[(&str, &str)] = &[
        ("framework = arduino", "arduino"),
        ("framework = espidf", "esp-idf"),
        ("framework = mbed", "mbed-os"),
        ("framework = zephyr", "zephyr"),
        ("framework = stm32cube", "stm32cube"),
        ("framework = libopencm3", "libopencm3"),
        ("framework = spl", "stm32-spl"),
        ("framework = cmsis", "cmsis"),
        ("framework = freertos", "freertos"),
    ];
    for (pattern, fw) in pio_frameworks {
        if lower.contains(pattern) {
            result.frameworks.push((*fw).to_string());
        }
    }

    // Detect platform families from `platform = xxx`
    let pio_platforms: &[(&str, &str)] = &[
        ("platform = espressif32", "esp32"),
        ("platform = espressif8266", "esp8266"),
        ("platform = ststm32", "stm32"),
        ("platform = atmelsam", "sam"),
        ("platform = atmelavr", "avr"),
        ("platform = nordicnrf52", "nrf52"),
        ("platform = teensy", "teensy"),
        ("platform = raspberrypi", "raspberry-pi"),
        ("platform = sifive", "risc-v"),
        ("platform = linux_arm", "linux-arm"),
        ("platform = linux_x86_64", "linux-x86"),
        ("platform = native", "native"),
    ];
    for (pattern, plat) in pio_platforms {
        if lower.contains(pattern) {
            result.platforms.push((*plat).to_string());
        }
    }

    // Detect common boards to infer platform
    if lower.contains("esp32") {
        result.platforms.push("esp32".into());
    }
    if lower.contains("esp8266") {
        result.platforms.push("esp8266".into());
    }
    if lower.contains("nrf52") {
        result.platforms.push("nrf52".into());
    }
    if lower.contains("stm32") {
        result.platforms.push("stm32".into());
    }

    // Detect RTOS usage in lib_deps
    if lower.contains("freertos") {
        result.frameworks.push("freertos".into());
    }
}

/// Scan Python dependency files (pyproject.toml, requirements.txt) for framework
/// and ML tool keywords. Uses simple string matching — no TOML parser needed.
fn scan_python_deps(content: &str, result: &mut ProjectScanResult) {
    let lower = content.to_lowercase();

    // Web frameworks
    let frameworks: &[(&str, &str)] = &[
        ("django", "django"),
        ("flask", "flask"),
        ("fastapi", "fastapi"),
        ("starlette", "starlette"),
        ("tornado", "tornado"),
        ("aiohttp", "aiohttp"),
        ("sanic", "sanic"),
        ("pyramid", "pyramid"),
        ("bottle", "bottle"),
        ("streamlit", "streamlit"),
        ("gradio", "gradio"),
        ("litestar", "litestar"),
        ("robyn", "robyn"),
        ("falcon", "falcon"),
        ("quart", "quart"),
    ];
    for (keyword, framework) in frameworks {
        if lower.contains(keyword) {
            result.frameworks.push((*framework).to_string());
        }
    }

    // AI/ML tools
    let ml_tools: &[(&str, &str)] = &[
        ("torch", "pytorch"),
        ("tensorflow", "tensorflow"),
        ("jax", "jax"),
        ("scikit-learn", "sklearn"),
        ("transformers", "huggingface"),
        ("langchain", "langchain"),
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("keras", "keras"),
        ("onnx", "onnx"),
        ("mlflow", "mlflow"),
        ("wandb", "wandb"),
        ("ray", "ray"),
        ("dask", "dask"),
        ("polars", "polars"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("matplotlib", "matplotlib"),
        ("plotly", "plotly"),
        ("seaborn", "seaborn"),
        ("bokeh", "bokeh"),
    ];
    for (keyword, tool) in ml_tools {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
        }
    }

    // Embedded / IoT / Hardware Python
    let embedded_py: &[(&str, &str, &str)] = &[
        // (keyword_in_deps, framework_or_tool_name, category: "framework"|"tool"|"platform")
        ("micropython", "micropython", "framework"),
        ("circuitpython", "circuitpython", "framework"),
        ("adafruit", "circuitpython", "framework"),
        ("rpi.gpio", "raspberry-pi", "platform"),
        ("gpiozero", "raspberry-pi", "platform"),
        ("smbus", "i2c", "tool"),
        ("spidev", "spi", "tool"),
        ("pyserial", "serial", "tool"),
        ("esptool", "esp32", "platform"),
        ("machine", "micropython", "framework"),
    ];
    for (keyword, name, category) in embedded_py {
        if lower.contains(keyword) {
            match *category {
                "framework" => result.frameworks.push((*name).to_string()),
                "tool" => result.tools.push((*name).to_string()),
                "platform" => result.platforms.push((*name).to_string()),
                _ => {}
            }
        }
    }

    // Robotics / ROS Python packages
    let robotics_py: &[(&str, &str)] = &[
        ("rospy", "ros"),
        ("rclpy", "ros2"),
        ("catkin", "ros"),
        ("ament", "ros2"),
        ("moveit", "moveit"),
        ("geometry_msgs", "ros"),
        ("sensor_msgs", "ros"),
        ("nav2", "ros2-nav2"),
    ];
    for (keyword, fw) in robotics_py {
        if lower.contains(keyword) {
            result.frameworks.push((*fw).to_string());
            result.platforms.push("robotics".into());
        }
    }

    // Industrial / automation Python packages
    let industrial_py: &[(&str, &str)] = &[
        ("pymodbus", "modbus"),
        ("opcua", "opcua"),
        ("asyncua", "opcua"),
        ("pycomm3", "allen-bradley"),
        ("snap7", "siemens-s7"),
        ("minimalmodbus", "modbus"),
    ];
    for (keyword, tool) in industrial_py {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
            result.platforms.push("industrial".into());
        }
    }

    // MQTT / messaging
    let messaging_py: &[(&str, &str)] = &[
        ("paho-mqtt", "mqtt"),
        ("paho.mqtt", "mqtt"),
        ("aiomqtt", "mqtt"),
        ("hbmqtt", "mqtt"),
        ("celery", "celery"),
        ("kombu", "amqp"),
        ("aio-pika", "rabbitmq"),
    ];
    for (keyword, tool) in messaging_py {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
        }
    }

    // Computer vision
    let cv_py: &[(&str, &str)] = &[
        ("opencv", "opencv"),
        ("cv2", "opencv"),
        ("pillow", "pillow"),
        ("ultralytics", "yolo"),
        ("detectron2", "detectron2"),
        ("mediapipe", "mediapipe"),
    ];
    for (keyword, tool) in cv_py {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
        }
    }

    // Scientific / instrumentation
    let science_py: &[(&str, &str)] = &[
        ("pyvisa", "visa"),
        ("nidaqmx", "ni-daq"),
        ("pymeasure", "pymeasure"),
        ("bluesky", "bluesky"),
        ("ophyd", "ophyd"),
        ("epics", "epics"),
    ];
    for (keyword, tool) in science_py {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
            result.platforms.push("instrumentation".into());
        }
    }

    // Testing frameworks
    let test_py: &[(&str, &str)] = &[
        ("pytest", "pytest"),
        ("unittest", "unittest"),
        ("hypothesis", "hypothesis"),
        ("tox", "tox"),
        ("nox", "nox"),
    ];
    for (keyword, tool) in test_py {
        if lower.contains(keyword) {
            result.tools.push((*tool).to_string());
        }
    }
}

/// Parse package.json content and check lock files to detect JS/TS frameworks,
/// package managers, and dev tools.
fn scan_package_json(content: &str, root_entries: &[String], result: &mut ProjectScanResult) {
    result.languages.push("javascript".into());

    // Detect package manager from lock files (order matters: most specific first)
    let has_file = |name: &str| root_entries.iter().any(|n| n == name);
    if has_file("bun.lockb") || has_file("bun.lock") {
        result.tools.push("bun".into());
    } else if has_file("pnpm-lock.yaml") {
        result.tools.push("pnpm".into());
    } else if has_file("yarn.lock") {
        result.tools.push("yarn".into());
    } else if has_file("package-lock.json") {
        result.tools.push("npm".into());
    }

    // Parse JSON to extract dependency names for framework/tool detection
    let pkg: serde_json::Value = match serde_json::from_str(content) {
        Ok(v) => v,
        Err(_) => return, // Malformed package.json — skip silently
    };

    let mut all_deps: Vec<String> = Vec::new();
    for section in &["dependencies", "devDependencies"] {
        if let Some(deps) = pkg.get(*section).and_then(|d| d.as_object()) {
            for key in deps.keys() {
                all_deps.push(key.to_lowercase());
            }
        }
    }

    // Framework detection from dependency names
    let frameworks: &[(&str, &str)] = &[
        // Frontend frameworks
        ("react", "react"),
        ("next", "nextjs"),
        ("vue", "vue"),
        ("nuxt", "nuxt"),
        ("svelte", "svelte"),
        ("@angular/core", "angular"),
        ("solid-js", "solidjs"),
        ("preact", "preact"),
        ("qwik", "qwik"),
        ("lit", "lit"),
        ("alpine", "alpinejs"),
        ("htmx.org", "htmx"),
        // Meta-frameworks / SSR / SSG
        ("gatsby", "gatsby"),
        ("remix", "remix"),
        ("astro", "astro"),
        // Backend frameworks
        ("express", "express"),
        ("fastify", "fastify"),
        ("hono", "hono"),
        ("koa", "koa"),
        ("@nestjs/core", "nestjs"),
        ("@trpc/server", "trpc"),
        ("@feathersjs/feathers", "feathersjs"),
        ("adonis", "adonisjs"),
        // Desktop / cross-platform
        ("electron", "electron"),
        ("tauri", "tauri"),
        ("neutralinojs", "neutralino"),
        // Mobile / hybrid
        ("react-native", "react-native"),
        ("expo", "expo"),
        ("@capacitor/core", "capacitor"),
        ("@ionic/core", "ionic"),
        ("nativescript", "nativescript"),
        // IoT / hardware JS
        ("johnny-five", "johnny-five"),
        ("cylon", "cylon"),
        ("onoff", "gpio"),
        ("raspi-io", "raspberry-pi"),
        ("serialport", "serialport"),
        // MQTT / messaging
        ("mqtt", "mqtt"),
        ("amqplib", "rabbitmq"),
        ("kafkajs", "kafka"),
        ("bullmq", "bullmq"),
        // Realtime
        ("socket.io", "socketio"),
        ("ws", "websocket"),
        ("@supabase/supabase-js", "supabase"),
        ("firebase", "firebase"),
        // 3D / game / graphics
        ("three", "threejs"),
        ("@babylonjs/core", "babylonjs"),
        ("pixi.js", "pixijs"),
        ("phaser", "phaser"),
        ("aframe", "a-frame"),
        ("@react-three/fiber", "react-three-fiber"),
    ];
    for (dep_name, framework) in frameworks {
        if all_deps.iter().any(|d| d == *dep_name) {
            result.frameworks.push((*framework).to_string());
        }
    }

    // Platform detection from mobile/desktop/embedded frameworks
    if all_deps.iter().any(|d| d == "react-native" || d == "expo") {
        result.platforms.push("mobile".into());
    }
    if all_deps.iter().any(|d| {
        d == "@capacitor/core" || d == "@ionic/core" || d == "nativescript"
    }) {
        result.platforms.push("mobile".into());
    }
    if all_deps.iter().any(|d| d == "electron" || d == "tauri" || d == "neutralinojs") {
        result.platforms.push("desktop".into());
    }
    if all_deps.iter().any(|d| {
        d == "johnny-five" || d == "cylon" || d == "onoff" || d == "raspi-io"
    }) {
        result.platforms.push("embedded".into());
    }

    // TypeScript detection from dependencies
    if all_deps.iter().any(|d| d == "typescript") {
        result.languages.push("typescript".into());
    }

    // Dev tool detection from dependency names
    let tools: &[(&str, &str)] = &[
        // Bundlers
        ("webpack", "webpack"),
        ("vite", "vite"),
        ("esbuild", "esbuild"),
        ("rollup", "rollup"),
        ("parcel", "parcel"),
        ("swc", "swc"),
        ("tsup", "tsup"),
        // Monorepo tools
        ("turbo", "turbo"),
        ("nx", "nx"),
        ("lerna", "lerna"),
        // Test frameworks
        ("jest", "jest"),
        ("vitest", "vitest"),
        ("mocha", "mocha"),
        ("ava", "ava"),
        ("tap", "tap"),
        // E2E / browser testing
        ("cypress", "cypress"),
        ("playwright", "playwright"),
        ("puppeteer", "puppeteer"),
        ("@testing-library/react", "testing-library"),
        ("storybook", "storybook"),
        // ORM / database
        ("prisma", "prisma"),
        ("drizzle-orm", "drizzle"),
        ("typeorm", "typeorm"),
        ("sequelize", "sequelize"),
        ("knex", "knex"),
        ("mongoose", "mongoose"),
        // CSS / styling
        ("tailwindcss", "tailwind"),
        ("styled-components", "styled-components"),
        ("@emotion/react", "emotion"),
        ("sass", "sass"),
        ("postcss", "postcss"),
        // State management
        ("zustand", "zustand"),
        ("redux", "redux"),
        ("@tanstack/react-query", "react-query"),
        ("swr", "swr"),
        ("jotai", "jotai"),
        ("recoil", "recoil"),
        // Validation
        ("zod", "zod"),
        ("yup", "yup"),
        ("joi", "joi"),
        // Auth
        ("next-auth", "nextauth"),
        ("passport", "passport"),
        // Documentation
        ("typedoc", "typedoc"),
        ("swagger-ui-express", "swagger"),
        // Linting / formatting
        ("eslint", "eslint"),
        ("prettier", "prettier"),
        ("biome", "biome"),
        ("oxlint", "oxlint"),
    ];
    for (dep_name, tool) in tools {
        if all_deps.iter().any(|d| d == *dep_name) {
            result.tools.push((*tool).to_string());
        }
    }
}

/// Scan root directory entries for notable file extensions and add them
/// to the file_types list. Only recognizes data/media/document formats,
/// not source code extensions (those are covered by language detection).
fn scan_root_file_types(entries: &[String], result: &mut ProjectScanResult) {
    let mut seen: HashSet<String> = HashSet::new();

    for name in entries {
        if let Some(ext) = name.rsplit('.').next() {
            let ext_lower = ext.to_lowercase();
            if seen.contains(&ext_lower) {
                continue;
            }
            // Add recognized data/media/document/hardware/embedded file types.
            // Source code extensions are not added here — they are detected
            // via config files above (Cargo.toml → rust, package.json → javascript, etc.)
            match ext_lower.as_str() {
                // Data / config formats
                "json" | "yaml" | "yml" | "toml" | "xml" | "csv" | "tsv" | "parquet"
                | "avro" | "arrow" | "ndjson" | "jsonl" | "ini" | "cfg" | "conf" | "env"
                | "properties" =>
                {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Documentation / text
                "md" | "txt" | "rst" | "adoc" | "tex" | "latex" | "org" | "rtf" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Web / markup
                "html" | "htm" | "xhtml" | "css" | "scss" | "sass" | "less" | "styl" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Images / graphics
                "svg" | "png" | "jpg" | "jpeg" | "gif" | "webp" | "ico" | "bmp" | "tiff"
                | "tga" | "psd" | "ai" | "eps" | "heic" | "avif" | "dds" | "exr" | "hdr" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Documents / office
                "pdf" | "epub" | "docx" | "xlsx" | "pptx" | "odt" | "ods" | "odp" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Audio / video
                "mp4" | "mp3" | "wav" | "webm" | "ogg" | "flac" | "aac" | "m4a" | "avi"
                | "mkv" | "mov" | "wmv" | "flv" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // 3D / CAD / game assets
                "obj" | "fbx" | "gltf" | "glb" | "stl" | "step" | "stp" | "iges" | "igs"
                | "3mf" | "blend" | "dae" | "usd" | "usda" | "usdc" | "usdz" | "abc" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // WebAssembly / binary interchange
                "wasm" | "wat" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // API / schema / serialization
                "proto" | "graphql" | "gql" | "thrift" | "avdl" | "capnp" | "fbs" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Database
                "sql" | "db" | "sqlite" | "sqlite3" | "mdb" | "accdb" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Embedded / firmware / hardware
                "hex" | "bin" | "elf" | "axf" | "s19" | "srec" | "uf2" | "dfu" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Device tree / hardware description
                "dts" | "dtsi" | "dtb" | "svd" | "pdsc" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // FPGA / HDL bitstreams
                "sof" | "bit" | "mcs" | "jed" | "pof" | "rbf" | "bin_fpga" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // GPU / shader
                "glsl" | "hlsl" | "wgsl" | "metal" | "spv" | "cg" | "frag" | "vert"
                | "geom" | "comp" | "tesc" | "tese" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Automotive / industrial
                "arxml" | "dbc" | "ldf" | "cdd" | "odx" | "pdx" | "a2l" | "aml" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // EDA / PCB / schematic
                "kicad_pcb" | "kicad_sch" | "brd" | "sch" | "gerber" | "gbr" | "drl"
                | "dsn" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // SDR / radio / signal
                "grc" | "sigmf" | "iq" | "cfile" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Instrumentation / lab
                "vi" | "lvproj" | "mlx" | "slx" | "mdl" | "mat" | "fig" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // G-code / CNC / 3D printing
                "gcode" | "nc" | "ngc" | "tap" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Reverse engineering
                "gpr" | "idb" | "i64" | "bndb" | "rzdb" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Notebook / interactive
                "ipynb" | "rmd" | "qmd" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Container / deployment descriptors
                "dockerfile" | "containerfile" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Qt / UI
                "qml" | "ui" | "qrc" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Maps / GIS
                "geojson" | "gpx" | "kml" | "kmz" | "shp" | "tif" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                // Certificates / security
                "pem" | "crt" | "cer" | "key" | "p12" | "pfx" | "jks" => {
                    result.file_types.push(ext_lower.clone());
                    seen.insert(ext_lower);
                }
                _ => {}
            }
        }
    }
}

/// Deduplicate a Vec<String> in place while preserving first-occurrence order.
fn dedup_vec(v: &mut Vec<String>) {
    let mut seen = HashSet::new();
    v.retain(|item| seen.insert(item.clone()));
}

// ============================================================================
// Skill Index Types (rio v3.0 format - enhanced)
// ============================================================================

/// The complete skill index (enhanced v3.0 format)
#[derive(Debug, Deserialize)]
pub struct SkillIndex {
    /// Index version
    pub version: String,

    /// When the index was generated
    #[serde(default)]
    pub generated: String,

    /// Generation method (ai-analyzed, heuristic, etc.)
    #[serde(default)]
    pub method: String,

    /// Number of skills in index
    #[serde(default)]
    pub skills_count: usize,

    /// Map of skill name to skill entry
    pub skills: HashMap<String, SkillEntry>,
}

/// A single skill entry in the index (enhanced with intents, patterns, directories)
#[derive(Debug, Deserialize)]
pub struct SkillEntry {
    /// Where the skill comes from: user, project, plugin
    #[serde(default)]
    pub source: String,

    /// Full path to SKILL.md
    pub path: String,

    /// Type: skill, agent, or command
    #[serde(rename = "type")]
    pub skill_type: String,

    /// Flat array of lowercase keywords/phrases
    #[serde(default)]
    pub keywords: Vec<String>,

    /// Action verbs/intents (deploy, test, build, etc.)
    #[serde(default)]
    pub intents: Vec<String>,

    /// Regex patterns to match
    #[serde(default)]
    pub patterns: Vec<String>,

    /// Directory patterns where skill is relevant
    #[serde(default)]
    pub directories: Vec<String>,

    /// Path patterns for file matching
    #[serde(default)]
    pub path_patterns: Vec<String>,

    /// One-line description
    #[serde(default)]
    pub description: String,

    /// Keywords that should NOT trigger this skill (from PSS)
    #[serde(default)]
    pub negative_keywords: Vec<String>,

    /// Element importance tier: primary, secondary, specialized (from PSS)
    #[serde(default)]
    pub tier: String,

    /// Score boost from PSS file (-10 to +10)
    #[serde(default)]
    pub boost: i32,

    /// Skill category for grouping (from PSS)
    #[serde(default)]
    pub category: String,

    // Platform/Framework/Language specificity metadata (from Pass 1)

    /// Platforms this skill targets: ["ios", "macos", "android", "windows", "linux"] or ["universal"]
    #[serde(default)]
    pub platforms: Vec<String>,

    /// Frameworks this skill targets: ["swiftui", "uikit", "react", "vue", "django"] or []
    #[serde(default)]
    pub frameworks: Vec<String>,

    /// Programming languages this skill targets: ["swift", "rust", "python", "typescript"] or ["any"]
    #[serde(default)]
    pub languages: Vec<String>,

    /// Domain expertise areas: ["writing", "graphics", "media", "file-formats", "security", "research", "ai-ml", "data", "devops"]
    #[serde(default)]
    pub domains: Vec<String>,

    /// Specific tools the skill uses: ["ffmpeg", "imagemagick", "pandoc", "stable-diffusion", "whisper"]
    #[serde(default)]
    pub tools: Vec<String>,

    /// File formats the skill handles: ["xlsx", "docx", "pdf", "epub", "mp4", "svg", "png"]
    #[serde(default)]
    pub file_types: Vec<String>,

    /// Domain gates: hard prerequisite filters for skill activation.
    /// Keys are gate names (e.g., "target_language", "cloud_provider"),
    /// values are arrays of lowercase keywords that satisfy the gate.
    /// ALL gates must pass for the skill to be considered.
    /// Special keyword "generic" means the gate passes whenever the domain is detected.
    #[serde(default)]
    pub domain_gates: HashMap<String, Vec<String>>,

    // MCP server additional metadata (only for type=mcp entries)

    /// MCP server transport type (stdio, sse)
    #[serde(default)]
    pub server_type: String,

    /// MCP server launch command
    #[serde(default)]
    pub server_command: String,

    /// MCP server command arguments
    #[serde(default)]
    pub server_args: Vec<String>,

    // LSP server additional metadata (only for type=lsp entries)

    /// LSP language identifiers (e.g., ["python"], ["typescript", "javascript"])
    #[serde(default)]
    pub language_ids: Vec<String>,

    // Co-usage fields (from Pass 2)

    /// Skills often used in the SAME session/task
    #[serde(default)]
    pub usually_with: Vec<String>,

    /// Skills typically used BEFORE this skill
    #[serde(default)]
    pub precedes: Vec<String>,

    /// Skills typically used AFTER this skill
    #[serde(default)]
    pub follows: Vec<String>,

    /// Skills that solve the SAME problem differently
    #[serde(default)]
    pub alternatives: Vec<String>,
}

// ============================================================================
// Domain Registry Types (for domain gate enforcement)
// ============================================================================

/// The complete domain registry (generated by pss_aggregate_domains.py)
#[derive(Debug, Deserialize, Clone)]
pub struct DomainRegistry {
    /// Registry version
    pub version: String,

    /// When the registry was generated
    #[serde(default)]
    pub generated: String,

    /// Path to the source skill-index.json
    #[serde(default)]
    pub source_index: String,

    /// Number of domains
    #[serde(default)]
    pub domain_count: usize,

    /// Map of canonical domain name to domain entry
    pub domains: HashMap<String, DomainRegistryEntry>,
}

/// A single domain in the registry
#[derive(Debug, Deserialize, Clone)]
pub struct DomainRegistryEntry {
    /// Canonical name for this domain (snake_case)
    pub canonical_name: String,

    /// All original gate names normalized to this canonical name
    #[serde(default)]
    pub aliases: Vec<String>,

    /// All keywords found across all skills for this domain.
    /// Used to detect whether the user prompt involves this domain.
    #[serde(default)]
    pub example_keywords: Vec<String>,

    /// True if at least one skill uses the "generic" wildcard for this domain
    #[serde(default)]
    pub has_generic: bool,

    /// Number of skills with a gate for this domain
    #[serde(default)]
    pub skill_count: usize,

    /// Names of skills that have a gate for this domain
    #[serde(default)]
    pub skills: Vec<String>,
}

// ============================================================================
// Output Types (Claude Code hook response)
// ============================================================================

/// Confidence level for skill activation
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Confidence {
    /// Score >= 12: Auto-suggest, minimal context needed
    High,
    /// Score 6-11: Show evidence, require YES/NO evaluation
    Medium,
    /// Score < 6: Full evaluation with alternatives
    Low,
}

impl Confidence {
    fn as_str(&self) -> &'static str {
        match self {
            Confidence::High => "HIGH",
            Confidence::Medium => "MEDIUM",
            Confidence::Low => "LOW",
        }
    }
}

/// Output payload for Claude Code hook (UserPromptSubmit format)
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HookOutput {
    /// Hook-specific output wrapper required by Claude Code
    pub hook_specific_output: HookSpecificOutput,
}

/// Hook-specific output for UserPromptSubmit
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HookSpecificOutput {
    /// Event name - must be "UserPromptSubmit"
    pub hook_event_name: String,

    /// Additional context to inject into Claude's context (as a string)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub additional_context: Option<String>,
}

/// Internal struct for building context items before formatting as string
#[derive(Debug)]
pub struct ContextItem {
    /// Type: skill, agent, or command
    pub item_type: String,

    /// Name of the skill/agent/command
    pub name: String,

    /// Path to the definition file
    pub path: String,

    /// Description of when to use
    pub description: String,

    /// Match score (0.0 to 1.0)
    pub score: f64,

    /// Confidence level: HIGH, MEDIUM, LOW
    pub confidence: String,

    /// Number of keyword matches (for debugging)
    pub match_count: usize,

    /// Match evidence (what triggered this suggestion)
    pub evidence: Vec<String>,

    /// Commitment reminder for HIGH confidence (from reliable)
    pub commitment: Option<String>,
}

impl ContextItem {
    /// Format context items as a readable string for additionalContext
    pub fn format_as_context(items: &[ContextItem]) -> Option<String> {
        if items.is_empty() {
            return None;
        }

        let mut context = String::from("<pss-skill-suggestions>\n");

        for item in items {
            context.push_str(&format!(
                "SUGGESTED: {} [{}]\n  Path: {}\n  Confidence: {} (score: {:.2})\n  Evidence: {}\n",
                item.name,
                item.item_type,
                item.path,
                item.confidence,
                item.score,
                item.evidence.join(", ")
            ));

            if let Some(commitment) = &item.commitment {
                context.push_str(&format!("  Commitment: {}\n", commitment));
            }
            context.push('\n');
        }

        context.push_str("</pss-skill-suggestions>");
        Some(context)
    }
}

impl HookOutput {
    /// Create an empty hook output (no suggestions)
    pub fn empty() -> Self {
        HookOutput {
            hook_specific_output: HookSpecificOutput {
                hook_event_name: "UserPromptSubmit".to_string(),
                additional_context: None,
            },
        }
    }

    /// Create a hook output with skill suggestions
    pub fn with_suggestions(items: Vec<ContextItem>) -> Self {
        HookOutput {
            hook_specific_output: HookSpecificOutput {
                hook_event_name: "UserPromptSubmit".to_string(),
                additional_context: ContextItem::format_as_context(&items),
            },
        }
    }
}

// ============================================================================
// Activation Logging Types
// ============================================================================

/// A single activation log entry (JSONL format)
#[derive(Debug, Serialize, Deserialize)]
pub struct ActivationLogEntry {
    /// ISO-8601 timestamp of the activation
    pub timestamp: String,

    /// Session ID (if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,

    /// Truncated prompt (for privacy, max 100 chars)
    pub prompt_preview: String,

    /// Full prompt hash for deduplication/analysis
    pub prompt_hash: String,

    /// Number of sub-tasks detected (1 = single task)
    pub subtask_count: usize,

    /// Working directory context
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cwd: Option<String>,

    /// List of matched skills
    pub matches: Vec<ActivationMatch>,

    /// Processing time in milliseconds
    #[serde(skip_serializing_if = "Option::is_none")]
    pub processing_ms: Option<u64>,
}

/// A matched skill in the activation log
#[derive(Debug, Serialize, Deserialize)]
pub struct ActivationMatch {
    /// Skill name
    pub name: String,

    /// Skill type: skill, agent, command
    #[serde(rename = "type")]
    pub skill_type: String,

    /// Match score
    pub score: i32,

    /// Confidence level: HIGH, MEDIUM, LOW
    pub confidence: String,

    /// Match evidence (keywords, intents, patterns, etc.)
    pub evidence: Vec<String>,
}

// ============================================================================
// Typo Tolerance (from Claude-Rio patterns)
// ============================================================================

lazy_static! {
    /// Common typos and their corrections (from Claude-Rio typo-tolerant pattern)
    static ref TYPO_CORRECTIONS: HashMap<&'static str, &'static str> = {
        let mut m = HashMap::new();

        // Common programming language typos
        m.insert("typscript", "typescript");
        m.insert("typescrpt", "typescript");
        m.insert("tyepscript", "typescript");
        m.insert("javscript", "javascript");
        m.insert("javascipt", "javascript");
        m.insert("javasript", "javascript");
        m.insert("pyhton", "python");
        m.insert("pythn", "python");
        m.insert("ptyhon", "python");
        m.insert("rusr", "rust");
        m.insert("ruts", "rust");

        // DevOps/Cloud typos
        m.insert("kuberntes", "kubernetes");
        m.insert("kuberentes", "kubernetes");
        m.insert("kubenretes", "kubernetes");
        m.insert("k8", "kubernetes");
        m.insert("dokcer", "docker");
        m.insert("dcoker", "docker");
        m.insert("doker", "docker");
        m.insert("containr", "container");
        m.insert("contaner", "container");

        // Git/GitHub typos
        m.insert("githb", "github");
        m.insert("gihub", "github");
        m.insert("gihtub", "github");
        m.insert("gtihub", "github");
        m.insert("comit", "commit");
        m.insert("commti", "commit");
        m.insert("brach", "branch");
        m.insert("brnach", "branch");
        m.insert("mege", "merge");
        m.insert("mreged", "merged");
        m.insert("rebas", "rebase");

        // CI/CD typos
        m.insert("pipline", "pipeline");
        m.insert("pipleine", "pipeline");
        m.insert("dpeloy", "deploy");
        m.insert("deplyo", "deploy");
        m.insert("dploy", "deploy");
        m.insert("realease", "release");
        m.insert("relase", "release");

        // Testing typos
        m.insert("tset", "test");
        m.insert("tets", "test");
        m.insert("tesst", "test");
        m.insert("uint", "unit");
        m.insert("intgration", "integration");
        m.insert("integartion", "integration");

        // Database typos
        m.insert("databse", "database");
        m.insert("databsae", "database");
        m.insert("postgrse", "postgres");
        m.insert("postgrs", "postgres");
        m.insert("sqll", "sql");
        m.insert("qurey", "query");
        m.insert("qeury", "query");

        // API typos
        m.insert("endpont", "endpoint");
        m.insert("endpiont", "endpoint");
        m.insert("reuqest", "request");
        m.insert("reqeust", "request");
        m.insert("repsone", "response");
        m.insert("respone", "response");

        // General coding typos
        m.insert("funciton", "function");
        m.insert("fucntion", "function");
        m.insert("functoin", "function");
        m.insert("calss", "class");
        m.insert("clas", "class");
        m.insert("metohd", "method");
        m.insert("mehod", "method");
        m.insert("varaible", "variable");
        m.insert("variabel", "variable");
        m.insert("improt", "import");
        m.insert("imoprt", "import");
        m.insert("exprot", "export");
        m.insert("exoprt", "export");

        // Framework typos
        m.insert("raect", "react");
        m.insert("reat", "react");
        m.insert("angualr", "angular");
        m.insert("agular", "angular");
        m.insert("nextjs", "next.js");
        m.insert("nodjes", "nodejs");
        m.insert("noed", "node");

        // Error/Debug typos
        m.insert("erorr", "error");
        m.insert("eroor", "error");
        m.insert("errro", "error");
        m.insert("dbug", "debug");
        m.insert("deubg", "debug");
        m.insert("bgu", "bug");
        m.insert("fixe", "fix");

        // Config typos
        m.insert("cofig", "config");
        m.insert("confg", "config");
        m.insert("configuation", "configuration");
        m.insert("configuartion", "configuration");
        m.insert("settigns", "settings");
        m.insert("setings", "settings");

        // Cloud provider typos
        m.insert("awss", "aws");
        m.insert("s3s", "s3");
        m.insert("gpc", "gcp");
        m.insert("azrue", "azure");
        m.insert("azuer", "azure");

        // MCP/Claude typos
        m.insert("mpc", "mcp");
        m.insert("cladue", "claude");
        m.insert("cluade", "claude");
        m.insert("antropic", "anthropic");
        m.insert("antrhoic", "anthropic");

        m
    };
}

/// Apply typo corrections to a string
fn correct_typos(text: &str) -> String {
    let words: Vec<&str> = text.split_whitespace().collect();
    let mut corrected_words: Vec<String> = Vec::new();

    for word in words {
        let word_lower = word.to_lowercase();
        // Check if word is a known typo
        if let Some(&correction) = TYPO_CORRECTIONS.get(word_lower.as_str()) {
            corrected_words.push(correction.to_string());
        } else {
            corrected_words.push(word.to_string());
        }
    }

    corrected_words.join(" ")
}

/// Calculate Damerau-Levenshtein edit distance between two strings
/// This variant counts transpositions (swapped adjacent chars) as 1 edit,
/// which is crucial for typo detection (e.g., "git" vs "gti" = 1 edit, not 2)
fn damerau_levenshtein_distance(a: &str, b: &str) -> usize {
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let a_len = a_chars.len();
    let b_len = b_chars.len();

    if a_len == 0 { return b_len; }
    if b_len == 0 { return a_len; }

    // Use a larger matrix to handle transposition lookback
    let mut matrix: Vec<Vec<usize>> = vec![vec![0; b_len + 1]; a_len + 1];

    // Initialize first column and row for edit distance matrix
    #[allow(clippy::needless_range_loop)]
    for i in 0..=a_len { matrix[i][0] = i; }
    #[allow(clippy::needless_range_loop)]
    for j in 0..=b_len { matrix[0][j] = j; }

    for i in 1..=a_len {
        for j in 1..=b_len {
            let cost = if a_chars[i-1] == b_chars[j-1] { 0 } else { 1 };

            // Standard Levenshtein operations
            matrix[i][j] = (matrix[i-1][j] + 1)      // deletion
                .min(matrix[i][j-1] + 1)              // insertion
                .min(matrix[i-1][j-1] + cost);        // substitution

            // Damerau extension: check for transposition (adjacent swap)
            // Only if i > 1 && j > 1 && chars at positions are swapped
            if i > 1 && j > 1
                && a_chars[i-1] == b_chars[j-2]
                && a_chars[i-2] == b_chars[j-1]
            {
                matrix[i][j] = matrix[i][j].min(matrix[i-2][j-2] + 1); // transposition
            }
        }
    }

    matrix[a_len][b_len]
}

/// Normalize separators: collapse hyphens, underscores, and camelCase boundaries
/// into a single canonical form (all lowercase, no separators).
/// "geo-json" / "geo_json" / "geoJson" / "geojson" → "geojson"
fn normalize_separators(word: &str) -> String {
    let mut result = String::with_capacity(word.len());
    let chars: Vec<char> = word.chars().collect();
    for (i, &ch) in chars.iter().enumerate() {
        match ch {
            '-' | '_' | ' ' => {} // strip separators
            _ => {
                // Insert boundary at camelCase transitions: "geoJson" → "geojson"
                // We just lowercase everything — the split is not needed since we
                // are comparing normalized forms directly.
                if ch.is_uppercase() && i > 0 && chars[i - 1].is_lowercase() {
                    // camelCase boundary — just lowercase, no separator
                }
                result.push(ch.to_ascii_lowercase());
            }
        }
    }
    result
}

/// Simple English morphological stemmer for keyword matching.
/// Strips common suffixes to produce a stem that allows matching across
/// grammatical forms: "deploys"→"deploy", "configuring"→"configure",
/// "configured"→"configure", "tests"→"test", "libraries"→"library".
///
/// This is intentionally conservative — it only handles high-confidence
/// suffix removals to avoid false conflations.
fn stem_word(word: &str) -> String {
    let result = stem_word_inner(word);
    // Post-process: strip trailing silent 'e' from ALL stems for consistency.
    // This ensures "configure" and "configured" both stem to "configur",
    // "generate" and "generating" both stem to "generat", etc.
    strip_trailing_silent_e(&result)
}

/// Strip a trailing 'e' that follows a consonant (English silent-e pattern).
/// "configure" → "configur", "generate" → "generat", "cache" → "cach"
/// Does NOT strip 'e' after vowels: "free" → "free", "tree" → "tree"
fn strip_trailing_silent_e(s: &str) -> String {
    let len = s.len();
    if len > 3 && s.ends_with('e') {
        let bytes = s.as_bytes();
        let before_e = bytes[len - 2];
        if !matches!(before_e, b'a' | b'e' | b'i' | b'o' | b'u') {
            return s[..len - 1].to_string();
        }
    }
    s.to_string()
}

fn stem_word_inner(word: &str) -> String {
    let w = word.to_lowercase();
    let len = w.len();

    // Too short to stem meaningfully
    if len < 4 {
        return w;
    }

    // Order matters: check longer suffixes before shorter ones

    // -ying → -y (e.g. "copying" → "copy") — but not "dying"→"d"
    if len > 5 && w.ends_with("ying") {
        let stem = &w[..len - 4];
        if stem.len() >= 3 {
            return format!("{}y", stem);
        }
    }

    // -ies → -y (e.g. "libraries" → "library", "dependencies" → "dependency")
    if len > 4 && w.ends_with("ies") {
        return format!("{}y", &w[..len - 3]);
    }

    // -ling → -le (e.g. "bundling" → "bundle")
    if len > 5 && w.ends_with("ling") {
        let stem = &w[..len - 4];
        if stem.len() >= 3 {
            return format!("{}le", stem);
        }
    }

    // -ting → -te (e.g. "generating" → "generate") — but not "setting"→"sete"
    // Only apply when preceded by a vowel: "crea-ting" → "create", "genera-ting" → "generate"
    if len > 5 && w.ends_with("ting") {
        let before = w.as_bytes()[len - 5];
        if matches!(before, b'a' | b'e' | b'i' | b'o' | b'u') {
            return format!("{}te", &w[..len - 4]);
        }
    }

    // Doubled consonant + ing: "running"→"run", "mapping"→"map", "debugging"→"debug"
    // Pattern: the char before "ing" is doubled (e.g. "nn" in "running", "pp" in "mapping")
    if len > 5 && w.ends_with("ing") {
        let bytes = w.as_bytes();
        let before_ing = bytes[len - 4]; // char right before "ing"
        if len >= 6 && bytes[len - 5] == before_ing
            && !matches!(before_ing, b'a' | b'e' | b'i' | b'o' | b'u')
        {
            // Doubled consonant: strip the doubled char + "ing" → keep root
            // "running" → bytes: r,u,n,n,i,n,g → strip from pos len-4 onward,
            // but also remove one of the doubled chars → w[..len-4]
            let stem = &w[..len - 4];
            if stem.len() >= 2 {
                return stem.to_string();
            }
        }
    }

    // -ation → strip to just remove "ation" (not add "ate", which causes over-stemming)
    // "validation"→"valid", "configuration"→"configur", "generation"→"gener"
    // These stems are imperfect but consistent: the same stem is produced from
    // "validate"→(strip -ate)→"valid", so they still match.
    if len > 6 && w.ends_with("ation") {
        let stem = &w[..len - 5];
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -ment (e.g. "deployment" → "deploy", "management" → "manage")
    if len > 5 && w.ends_with("ment") {
        let stem = &w[..len - 4];
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -ing (general, after more specific -Xing rules above)
    // e.g. "testing" → "test", "building" → "build"
    if len > 4 && w.ends_with("ing") {
        let stem = &w[..len - 3];
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -ised / -ized → -ise / -ize (e.g. "optimized" → "optimize")
    // Just strip the trailing "d" since the base already ends in 'e'
    if len > 5 && (w.ends_with("ised") || w.ends_with("ized")) {
        return w[..len - 1].to_string();
    }

    // -ed (e.g. "configured" → "configur", "deployed" → "deploy")
    // For consistency, "configure" also stems to "configur" via trailing-e stripping below.
    if len > 4 && w.ends_with("ed") {
        let stem = &w[..len - 2]; // strip "ed"
        // Double consonant before -ed: "mapped" → "map" (strip "ped")
        if stem.len() >= 3 {
            let bytes = stem.as_bytes();
            let last = bytes[stem.len() - 1];
            let prev = bytes[stem.len() - 2];
            if last == prev && !matches!(last, b'a' | b'e' | b'i' | b'o' | b'u') {
                return stem[..stem.len() - 1].to_string();
            }
        }
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -er (e.g. "bundler" → "bundle", "compiler" → "compile")
    if len > 4 && w.ends_with("er") {
        let stem = &w[..len - 2];
        // "bundler" → "bundl" — need to add back 'e': "bundle"
        // But "docker" → "dock", not "docke"
        // Heuristic: if stem ends in a consonant cluster, try adding 'e'
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -ly (e.g. "automatically" → "automatic")
    if len > 4 && w.ends_with("ly") {
        let stem = &w[..len - 2];
        if stem.len() >= 3 {
            return stem.to_string();
        }
    }

    // -es (e.g. "patches" → "patch", "fixes" → "fix")
    if len > 4 && w.ends_with("es") {
        let stem = &w[..len - 2];
        if stem.len() >= 3 {
            // "patches" → "patch", "fixes" → "fix", "databases" → "databas" (ok for matching)
            return stem.to_string();
        }
    }

    // -s (e.g. "tests" → "test", "deploys" → "deploy")
    // Must be after -es, -ies checks
    if len > 3 && w.ends_with('s') && !w.ends_with("ss") {
        return w[..len - 1].to_string();
    }

    w
}

/// Common tech abbreviation pairs (short form → long form).
/// Used in Phase 2.5 to match abbreviations against their full forms.
/// Both directions are checked: "config" matches "configuration" and vice versa.
const ABBREVIATIONS: &[(&str, &str)] = &[
    ("config", "configuration"),
    ("repo", "repository"),
    ("env", "environment"),
    ("auth", "authentication"),
    ("authn", "authentication"),
    ("authz", "authorization"),
    ("admin", "administration"),
    ("app", "application"),
    ("args", "arguments"),
    ("async", "asynchronous"),
    ("auto", "automatic"),
    ("bg", "background"),
    ("bin", "binary"),
    ("bool", "boolean"),
    ("calc", "calculate"),
    ("cert", "certificate"),
    ("cfg", "configuration"),
    ("char", "character"),
    ("cmd", "command"),
    ("cmp", "compare"),
    ("concat", "concatenate"),
    ("cond", "condition"),
    ("conn", "connection"),
    ("const", "constant"),
    ("ctrl", "control"),
    ("ctx", "context"),
    ("db", "database"),
    ("decl", "declaration"),
    ("def", "definition"),
    ("del", "delete"),
    ("dep", "dependency"),
    ("deps", "dependencies"),
    ("desc", "description"),
    ("dest", "destination"),
    ("dev", "development"),
    ("dict", "dictionary"),
    ("diff", "difference"),
    ("dir", "directory"),
    ("dirs", "directories"),
    ("dist", "distribution"),
    ("doc", "documentation"),
    ("docs", "documentation"),
    ("elem", "element"),
    ("err", "error"),
    ("eval", "evaluate"),
    ("exec", "execute"),
    ("expr", "expression"),
    ("ext", "extension"),
    ("fmt", "format"),
    ("fn", "function"),
    ("func", "function"),
    ("gen", "generate"),
    ("hw", "hardware"),
    ("impl", "implementation"),
    ("import", "import"),
    ("info", "information"),
    ("init", "initialize"),
    ("iter", "iterator"),
    ("lang", "language"),
    ("len", "length"),
    ("lib", "library"),
    ("libs", "libraries"),
    ("ln", "link"),
    ("loc", "location"),
    ("max", "maximum"),
    ("mem", "memory"),
    ("mgmt", "management"),
    ("min", "minimum"),
    ("misc", "miscellaneous"),
    ("mod", "module"),
    ("msg", "message"),
    ("nav", "navigation"),
    ("num", "number"),
    ("obj", "object"),
    ("ops", "operations"),
    ("opt", "option"),
    ("org", "organization"),
    ("os", "operating_system"),
    ("param", "parameter"),
    ("params", "parameters"),
    ("perf", "performance"),
    ("pkg", "package"),
    ("pref", "preference"),
    ("prev", "previous"),
    ("proc", "process"),
    ("prod", "production"),
    ("prog", "program"),
    ("prop", "property"),
    ("props", "properties"),
    ("proto", "protocol"),
    ("pub", "public"),
    ("qty", "quantity"),
    ("recv", "receive"),
    ("ref", "reference"),
    ("regex", "regular_expression"),
    ("req", "request"),
    ("res", "response"),
    ("ret", "return"),
    ("rm", "remove"),
    ("sec", "security"),
    ("sel", "select"),
    ("sep", "separator"),
    ("seq", "sequence"),
    ("sig", "signature"),
    ("spec", "specification"),
    ("specs", "specifications"),
    ("src", "source"),
    ("srv", "server"),
    ("str", "string"),
    ("struct", "structure"),
    ("sub", "subscribe"),
    ("svc", "service"),
    ("sw", "software"),
    ("sync", "synchronize"),
    ("sys", "system"),
    ("temp", "temporary"),
    ("tmp", "temporary"),
    ("val", "value"),
    ("var", "variable"),
    ("vars", "variables"),
    ("ver", "version"),
];

/// Check if two normalized words match via abbreviation expansion.
/// Returns true if one is a known abbreviation of the other.
fn is_abbreviation_match(a: &str, b: &str) -> bool {
    for &(short, long) in ABBREVIATIONS {
        // Check both directions: a=short,b=long or a=long,b=short
        if (a == short && b == long) || (a == long && b == short) {
            return true;
        }
    }
    false
}

/// Check if two words are fuzzy matches (within edit distance threshold)
/// Threshold is adaptive: 1 for short words (<=4), 2 for medium (<=8), 3 for long
fn is_fuzzy_match(word: &str, keyword: &str) -> bool {
    let word_len = word.len();
    let keyword_len = keyword.len();

    // Don't fuzzy match short words — too many false positives (lint→link, fix→fax).
    // Use max length: a deletion typo like "githb" (5 chars) should still match "github" (6 chars)
    // because the longer word meets the threshold.
    let max_len = word_len.max(keyword_len);
    if max_len < 6 {
        return false;
    }

    // Length difference threshold - don't match if lengths are too different
    let len_diff = (word_len as i32 - keyword_len as i32).abs();
    if len_diff > 2 {
        return false;
    }

    // Adaptive threshold based on word length
    let threshold = if keyword_len <= 8 {
        1  // 6-8 chars: allow 1 edit
    } else if keyword_len <= 12 {
        2  // 9-12 chars: allow 2 edits
    } else {
        3  // 13+ chars: allow 3 edits
    };

    damerau_levenshtein_distance(word, keyword) <= threshold
}

// ============================================================================
// Task Decomposition (from LimorAI - break complex prompts into sub-tasks)
// ============================================================================

lazy_static! {
    /// Patterns for task decomposition - detect multi-task prompts
    /// NOTE: We handle sentence-based decomposition separately (not via regex)
    /// because Rust's regex crate doesn't support lookahead assertions
    static ref TASK_SEPARATORS: Vec<Regex> = vec![
        // "X and then Y" - sequential tasks
        Regex::new(r"(?i)\s+and\s+then\s+").unwrap(),
        // "X then Y" - sequential tasks
        Regex::new(r"(?i)\s+then\s+").unwrap(),
        // "X; Y" - semicolon separation
        Regex::new(r"\s*;\s*").unwrap(),
        // "first X, then Y" - explicit ordering
        Regex::new(r"(?i),?\s*then\s+").unwrap(),
        // "X, and Y" - comma with and
        Regex::new(r",\s+and\s+").unwrap(),
        // "X also Y" - additional task
        Regex::new(r"(?i)\s+also\s+").unwrap(),
        // "X as well as Y" - additional task
        Regex::new(r"(?i)\s+as\s+well\s+as\s+").unwrap(),
        // "X plus Y" - additional task
        Regex::new(r"(?i)\s+plus\s+").unwrap(),
        // "X additionally Y" - additional task
        Regex::new(r"(?i)\s+additionally\s+").unwrap(),
    ];

    /// Regex for splitting on sentence boundaries (period + space + optional capital)
    static ref SENTENCE_BOUNDARY: Regex = Regex::new(r"\.\s+").unwrap();

    /// Action verbs that indicate task starts
    static ref ACTION_VERBS: Vec<&'static str> = vec![
        "help", "create", "build", "write", "fix", "debug", "deploy", "test",
        "run", "check", "configure", "set", "add", "remove", "update", "install",
        "generate", "implement", "refactor", "optimize", "analyze", "review",
        "setup", "migrate", "convert", "delete", "modify", "explain", "show",
        "find", "search", "list", "get", "make", "start", "stop", "restart",
    ];
}

/// Decompose a complex prompt into individual sub-tasks
/// Returns a vector of sub-task strings, or a single-element vector if no decomposition needed
fn decompose_tasks(prompt: &str) -> Vec<String> {
    let prompt_lower = prompt.to_lowercase();
    let prompt_trimmed = prompt.trim();

    // Skip decomposition for short prompts (likely single task)
    if prompt_trimmed.len() < 20 {
        return vec![prompt_trimmed.to_string()];
    }

    // Skip decomposition if no action verbs found
    let has_action = ACTION_VERBS.iter().any(|v| prompt_lower.contains(v));
    if !has_action {
        return vec![prompt_trimmed.to_string()];
    }

    // Try each separator pattern
    for separator in TASK_SEPARATORS.iter() {
        if separator.is_match(prompt_trimmed) {
            let parts: Vec<String> = separator
                .split(prompt_trimmed)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty() && s.len() > 5) // Filter out tiny fragments
                .collect();

            if parts.len() > 1 {
                debug!("Decomposed prompt into {} sub-tasks using separator", parts.len());
                return parts;
            }
        }
    }

    // Sentence-based decomposition: "X. Y" where Y starts with action verb
    // We can't use regex lookahead, so we split on ". " and filter manually
    if SENTENCE_BOUNDARY.is_match(prompt_trimmed) {
        let parts: Vec<String> = SENTENCE_BOUNDARY
            .split(prompt_trimmed)
            .map(|s| s.trim().to_string())
            .filter(|s| {
                if s.is_empty() || s.len() <= 5 {
                    return false;
                }
                // Keep if starts with an action verb (case-insensitive)
                let s_lower = s.to_lowercase();
                ACTION_VERBS.iter().any(|verb| {
                    s_lower.starts_with(verb) ||
                    s_lower.starts_with(&format!("{} ", verb))
                })
            })
            .collect();

        // Only use sentence decomposition if we got multiple action-verb sentences
        if parts.len() > 1 {
            debug!("Decomposed prompt into {} sentence-based sub-tasks", parts.len());
            return parts;
        }
    }

    // Detect numbered lists: "1. X 2. Y 3. Z"
    let numbered_re = Regex::new(r"(?m)^\s*\d+[\.\)]\s*").unwrap();
    if numbered_re.is_match(prompt_trimmed) {
        let parts: Vec<String> = numbered_re
            .split(prompt_trimmed)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty() && s.len() > 5)
            .collect();

        if parts.len() > 1 {
            debug!("Decomposed prompt into {} numbered sub-tasks", parts.len());
            return parts;
        }
    }

    // Detect bullet lists: "- X - Y" or "* X * Y"
    let bullet_re = Regex::new(r"(?m)^\s*[-*•]\s+").unwrap();
    if bullet_re.is_match(prompt_trimmed) {
        let parts: Vec<String> = bullet_re
            .split(prompt_trimmed)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty() && s.len() > 5)
            .collect();

        if parts.len() > 1 {
            debug!("Decomposed prompt into {} bulleted sub-tasks", parts.len());
            return parts;
        }
    }

    // No decomposition needed
    vec![prompt_trimmed.to_string()]
}

/// Aggregate matches from multiple sub-tasks, deduplicating and combining scores
fn aggregate_subtask_matches(
    all_matches: Vec<Vec<MatchedSkill>>,
) -> Vec<MatchedSkill> {
    let mut aggregated: HashMap<String, MatchedSkill> = HashMap::new();

    for task_matches in all_matches {
        for matched_skill in task_matches {
            let name = matched_skill.name.clone();

            if let Some(existing) = aggregated.get_mut(&name) {
                // Skill already seen - aggregate scores and evidence
                // Take max score (skill matched multiple sub-tasks well)
                if matched_skill.score > existing.score {
                    existing.score = matched_skill.score;
                    existing.confidence = matched_skill.confidence;
                }

                // Merge evidence, avoiding duplicates
                for ev in &matched_skill.evidence {
                    if !existing.evidence.contains(ev) {
                        existing.evidence.push(ev.clone());
                    }
                }

                // Boost score slightly for matching multiple sub-tasks
                existing.score += 2; // Multi-task relevance bonus
            } else {
                // New skill - add to aggregated
                aggregated.insert(name, matched_skill);
            }
        }
    }

    // Convert back to vector and re-sort
    let mut result: Vec<MatchedSkill> = aggregated.into_values().collect();

    // Re-calculate confidence after aggregation
    let thresholds = ConfidenceThresholds::default();
    for skill in &mut result {
        skill.confidence = if skill.score >= thresholds.high {
            Confidence::High
        } else if skill.score >= thresholds.medium {
            Confidence::Medium
        } else {
            Confidence::Low
        };
    }

    // Sort by score descending, with skills-first ordering
    result.sort_by(|a, b| {
        let score_cmp = b.score.cmp(&a.score);
        if score_cmp != std::cmp::Ordering::Equal {
            return score_cmp;
        }
        let type_order = |t: &str| match t {
            "skill" => 0,
            "agent" => 1,
            "command" => 2,
            _ => 3,
        };
        type_order(&a.skill_type).cmp(&type_order(&b.skill_type))
    });

    // Limit results
    result.truncate(MAX_SUGGESTIONS);

    result
}

// ============================================================================
// Synonym Expansion (70+ patterns from LimorAI)
// ============================================================================

lazy_static! {
    // Compiled regex patterns for synonym expansion
    static ref RE_PR: Regex = Regex::new(r"(?i)\bpr\b").unwrap();
    static ref RE_DB: Regex = Regex::new(r"(?i)\b(db|database|postgres|postgresql|sql)\b").unwrap();
    static ref RE_DEPLOY: Regex = Regex::new(r"(?i)\b(deploy|deployment|deploying|release)\b").unwrap();
    static ref RE_TEST: Regex = Regex::new(r"(?i)\b(test|testing|tests|spec)\b").unwrap();
    static ref RE_GIT: Regex = Regex::new(r"(?i)\b(git|github|repo|repository)\b").unwrap();
    static ref RE_TROUBLE: Regex = Regex::new(r"(?i)(troubleshoot|debug|error|problem|fail|bug)").unwrap();
    static ref RE_CONTEXT: Regex = Regex::new(r"(?i)(context|memory|optimi)").unwrap();
    static ref RE_RAG: Regex = Regex::new(r"(?i)\b(rag|retrieval|vector|embeddings?)\b").unwrap();
    static ref RE_PROMPT: Regex = Regex::new(r"(?i)(prompt.engineer|system.prompt|llm.prompt)").unwrap();
    static ref RE_API: Regex = Regex::new(r"(?i)(api.design|rest.api|graphql|openapi)").unwrap();
    static ref RE_API_FIRST: Regex = Regex::new(r"(?i)(api.first|check.api|validate.api|api.source)").unwrap();
    static ref RE_TRACE: Regex = Regex::new(r"(?i)(tracing|distributed.trace|opentelemetry|jaeger)").unwrap();
    static ref RE_GRAFANA: Regex = Regex::new(r"(?i)(grafana|prometheus|metrics|dashboard.monitor)").unwrap();
    static ref RE_SQL_OPT: Regex = Regex::new(r"(?i)(sql.optimi|query.optimi|index.optimi|explain.analyze)").unwrap();
    static ref RE_FEEDBACK: Regex = Regex::new(r"(?i)\b(feedback|review|rating|thumbs)\b").unwrap();
    static ref RE_AI: Regex = Regex::new(r"(?i)\b(ai|llm|gemini|vertex|model)\b").unwrap();
    static ref RE_VALIDATE: Regex = Regex::new(r"(?i)\b(validate|validation|verify|check|confirm)\b").unwrap();
    static ref RE_MCP: Regex = Regex::new(r"(?i)\b(mcp|tool.server)\b").unwrap();
    static ref RE_SACRED: Regex = Regex::new(r"(?i)\b(sacred|golden.?rule|commandment|compliance)\b").unwrap();
    static ref RE_HEBREW: Regex = Regex::new(r"(?i)\b(hebrew|עברית|rtl|israeli)\b").unwrap();
    static ref RE_BEECOM: Regex = Regex::new(r"(?i)\b(beecom|pos|orders?|products?|restaurant)\b").unwrap();
    static ref RE_SHIFT: Regex = Regex::new(r"(?i)\b(shift|schedule|labor|employee.hours)\b").unwrap();
    static ref RE_REVENUE: Regex = Regex::new(r"(?i)\b(revenue|sales|income)\b").unwrap();
    static ref RE_SESSION: Regex = Regex::new(r"(?i)\b(session|workflow|start.session|end.session|checkpoint)\b").unwrap();
    static ref RE_PERPLEXITY: Regex = Regex::new(r"(?i)\b(perplexity|research|search.online|web.search)\b").unwrap();
    static ref RE_BLUEPRINT: Regex = Regex::new(r"(?i)\b(blueprint|architecture|feature.context|how.does.*work)\b").unwrap();
    static ref RE_PARITY: Regex = Regex::new(r"(?i)\b(parity|environment.match|localhost.vs|staging.vs)\b").unwrap();
    static ref RE_CACHE: Regex = Regex::new(r"(?i)\b(cache|caching|cached|ttl|invalidate)\b").unwrap();
    static ref RE_WHATSAPP: Regex = Regex::new(r"(?i)\b(whatsapp|messaging|chat.bot|webhook)\b").unwrap();
    static ref RE_SYNC: Regex = Regex::new(r"(?i)\b(sync|syncing|migration|migrate|backfill)\b").unwrap();
    static ref RE_SEMANTIC: Regex = Regex::new(r"(?i)\b(semantic|query.router|tier|embedding)\b").unwrap();
    static ref RE_VISUAL: Regex = Regex::new(r"(?i)\b(visual|screenshot|regression|baseline|ui.test)\b").unwrap();
    static ref RE_SKILL: Regex = Regex::new(r"(?i)\b(skill|create.skill|add.skill|update.skill|retrospective)\b").unwrap();
    static ref RE_CI: Regex = Regex::new(r"(?i)\b(ci|cd|pipeline|workflow|action)\b").unwrap();
    static ref RE_DOCKER: Regex = Regex::new(r"(?i)\b(docker|container|dockerfile|compose|kubernetes|k8s)\b").unwrap();
    static ref RE_AWS: Regex = Regex::new(r"(?i)\b(aws|s3|ec2|lambda|cloudformation)\b").unwrap();
    static ref RE_GCP: Regex = Regex::new(r"(?i)\b(gcp|gcloud|cloud.run|bigquery|pubsub)\b").unwrap();
    static ref RE_AZURE: Regex = Regex::new(r"(?i)\b(azure|blob|functions|cosmos)\b").unwrap();
    static ref RE_SECURITY: Regex = Regex::new(r"(?i)\b(security|auth|oauth|jwt|encryption)\b").unwrap();
    static ref RE_PERF: Regex = Regex::new(r"(?i)\b(performance|slow|latency|optimize|profil)\b").unwrap();
}

/// Expand synonyms in the prompt to improve matching (from LimorAI)
fn expand_synonyms(prompt: &str) -> String {
    let msg = prompt.to_lowercase();
    let mut expanded = msg.clone();

    // GitHub operations
    if RE_PR.is_match(&msg) {
        expanded.push_str(" github pull request");
    }
    if msg.contains("pull") && msg.contains("request") {
        expanded.push_str(" github pr");
    }
    if msg.contains("issue") {
        expanded.push_str(" github");
    }
    if msg.contains("fork") {
        expanded.push_str(" github repository");
    }

    // Authentication / HTTP codes
    if msg.contains("403") {
        expanded.push_str(" oauth2 authentication forbidden");
    }
    if msg.contains("401") {
        expanded.push_str(" authentication unauthorized");
    }
    if msg.contains("auth") && msg.contains("error") {
        expanded.push_str(" authentication oauth2");
    }
    if msg.contains("404") {
        expanded.push_str(" routing endpoint notfound");
    }
    if msg.contains("500") {
        expanded.push_str(" server error crash internal");
    }

    // Database patterns
    if RE_DB.is_match(&msg) {
        expanded.push_str(" database");
    }
    if msg.contains("econnrefused") {
        expanded.push_str(" credentials database connection refused");
    }
    if msg.contains("connection") && msg.contains("refused") {
        expanded.push_str(" database credentials");
    }
    if msg.contains("connection") && msg.contains("error") {
        expanded.push_str(" database credentials troubleshooting");
    }

    // Gaps & Sync
    if msg.contains("gap") {
        expanded.push_str(" gap-detection sync parity");
    }
    if msg.contains("missing") && msg.contains("data") {
        expanded.push_str(" gap sync parity api-first");
    }
    if msg.contains("missing") {
        expanded.push_str(" gap detection");
    }

    // Deployment
    if RE_DEPLOY.is_match(&msg) {
        expanded.push_str(" deployment");
    }
    if msg.contains("staging") {
        expanded.push_str(" deployment environment staging");
    }
    if msg.contains("production") {
        expanded.push_str(" deployment environment production");
    }
    if msg.contains("traffic") {
        expanded.push_str(" cloud-run traffic routing");
    }
    if msg.contains("cloud") && msg.contains("run") {
        expanded.push_str(" cloud-run deployment traffic gcp");
    }

    // Testing
    if RE_TEST.is_match(&msg) {
        expanded.push_str(" testing");
    }
    if msg.contains("jest") {
        expanded.push_str(" testing unit javascript");
    }
    if msg.contains("playwright") {
        expanded.push_str(" testing e2e visual browser");
    }
    if msg.contains("pytest") || msg.contains("unittest") {
        expanded.push_str(" testing python unit");
    }
    if msg.contains("baseline") {
        expanded.push_str(" baseline testing methodology");
    }

    // Git
    if RE_GIT.is_match(&msg) {
        expanded.push_str(" github version-control");
    }
    if msg.contains("conflict") {
        expanded.push_str(" merge pr-merge validation");
    }
    if msg.contains("merge") {
        expanded.push_str(" pr-merge validation github");
    }

    // Troubleshooting
    if RE_TROUBLE.is_match(&msg) {
        expanded.push_str(" troubleshooting workflow debugging");
    }

    // Context optimization
    if RE_CONTEXT.is_match(&msg) {
        expanded.push_str(" context optimization tokens");
    }
    if msg.contains("token") {
        expanded.push_str(" context optimization llm");
    }

    // RAG/Embeddings
    if RE_RAG.is_match(&msg) {
        expanded.push_str(" rag embeddings llm-application semantic vector");
    }
    if msg.contains("pgvector") || msg.contains("hnsw") {
        expanded.push_str(" rag database ai vector");
    }

    // Prompt engineering
    if RE_PROMPT.is_match(&msg) {
        expanded.push_str(" prompt-engineering llm-application");
    }

    // API design
    if RE_API.is_match(&msg) {
        expanded.push_str(" api-design backend architecture");
    }
    if RE_API_FIRST.is_match(&msg) {
        expanded.push_str(" api-first validation");
    }
    if msg.contains("api") {
        expanded.push_str(" api endpoint rest");
    }

    // Tracing/Observability
    if RE_TRACE.is_match(&msg) {
        expanded.push_str(" distributed-tracing observability");
    }
    if RE_GRAFANA.is_match(&msg) {
        expanded.push_str(" grafana prometheus observability monitoring");
    }

    // SQL optimization
    if RE_SQL_OPT.is_match(&msg) {
        expanded.push_str(" sql-optimization database postgresql");
    }

    // Phase 2 patterns
    if RE_FEEDBACK.is_match(&msg) {
        expanded.push_str(" feedback user-feedback");
    }
    if RE_AI.is_match(&msg) {
        expanded.push_str(" ai llm artificial-intelligence");
    }
    if RE_VALIDATE.is_match(&msg) {
        expanded.push_str(" validation");
    }
    if RE_MCP.is_match(&msg) {
        expanded.push_str(" mcp model-context-protocol tools");
    }
    if RE_SACRED.is_match(&msg) {
        expanded.push_str(" sacred commandments rules");
    }
    if RE_HEBREW.is_match(&msg) {
        expanded.push_str(" hebrew preservation encoding i18n");
    }
    if RE_BEECOM.is_match(&msg) {
        expanded.push_str(" beecom pos ecommerce");
    }
    if RE_SHIFT.is_match(&msg) {
        expanded.push_str(" shift labor status scheduling");
    }
    if RE_REVENUE.is_match(&msg) {
        expanded.push_str(" revenue calculation analytics");
    }

    // Phase 3 patterns
    if RE_SESSION.is_match(&msg) {
        expanded.push_str(" session workflow start protocol");
    }
    if RE_PERPLEXITY.is_match(&msg) {
        expanded.push_str(" perplexity research memory web");
    }
    if RE_BLUEPRINT.is_match(&msg) {
        expanded.push_str(" blueprint architecture design");
    }
    if RE_PARITY.is_match(&msg) {
        expanded.push_str(" parity validation environment consistency");
    }
    if RE_CACHE.is_match(&msg) {
        expanded.push_str(" cache optimization redis memcached");
    }

    // Phase 4 patterns
    if RE_WHATSAPP.is_match(&msg) {
        expanded.push_str(" whatsapp monitoring messaging");
    }
    if RE_SYNC.is_match(&msg) {
        expanded.push_str(" sync migration database etl");
    }
    if RE_SEMANTIC.is_match(&msg) {
        expanded.push_str(" semantic query router search");
    }
    if RE_VISUAL.is_match(&msg) {
        expanded.push_str(" visual regression testing ui");
    }

    // Skills
    if RE_SKILL.is_match(&msg) {
        expanded.push_str(" skill maintenance creation claude");
    }

    // Performance
    if RE_PERF.is_match(&msg) {
        expanded.push_str(" performance optimization speed");
    }
    if msg.contains("slow") || msg.contains("latency") {
        expanded.push_str(" response time optimization performance");
    }

    // CI/CD
    if RE_CI.is_match(&msg) {
        expanded.push_str(" cicd deployment automation github-actions");
    }

    // Cloud platforms
    if RE_DOCKER.is_match(&msg) {
        expanded.push_str(" docker containerization devops");
    }
    if RE_AWS.is_match(&msg) {
        expanded.push_str(" aws cloud amazon infrastructure");
    }
    if RE_GCP.is_match(&msg) {
        expanded.push_str(" gcp google-cloud infrastructure");
    }
    if RE_AZURE.is_match(&msg) {
        expanded.push_str(" azure microsoft cloud infrastructure");
    }

    // Security
    if RE_SECURITY.is_match(&msg) {
        expanded.push_str(" security authentication authorization");
    }

    // PostgreSQL / MCP
    if msg.contains("postgresql") || (msg.contains("postgres") && msg.contains("mcp")) {
        expanded.push_str(" postgresql mcp database sql");
    }

    expanded
}

// ============================================================================
// Domain Gate Detection and Filtering
// ============================================================================

/// Detected domains from the user prompt, mapped from canonical domain name
/// to the set of matching keywords found in the prompt.
pub type DetectedDomains = HashMap<String, Vec<String>>;

/// Detect which domains are relevant to the user prompt by scanning for
/// keywords from the domain registry.
///
/// Returns a map: canonical_domain_name -> [matched_keywords]
/// A domain is "detected" if at least one of its example_keywords appears in the prompt.
#[cfg(test)]
fn detect_domains_from_prompt(
    prompt: &str,
    registry: &DomainRegistry,
) -> DetectedDomains {
    detect_domains_from_prompt_with_context(prompt, registry, &[])
}

/// Detect domains from prompt text AND project context signals.
///
/// Two sources of domain detection:
/// 1. Keyword matches in the prompt text (primary)
/// 2. Project context signals from the hook (languages, frameworks, platforms, tools)
///    that match domain registry keywords. This ensures that e.g. a project with
///    Objective-C files triggers the "programming_language" or "target_language" domain
///    even if the user doesn't explicitly mention it in the prompt.
fn detect_domains_from_prompt_with_context(
    prompt: &str,
    registry: &DomainRegistry,
    context_signals: &[String],
) -> DetectedDomains {
    let prompt_lower = prompt.to_lowercase();
    let mut detected: DetectedDomains = HashMap::new();

    // Build a combined text for matching: prompt + context signals
    // Context signals are lowercased tokens from project analysis
    let context_lower: Vec<String> = context_signals.iter().map(|s| s.to_lowercase()).collect();

    for (canonical_name, domain_entry) in &registry.domains {
        let mut matched_keywords: Vec<String> = Vec::new();

        for keyword in &domain_entry.example_keywords {
            // Skip the "generic" meta-keyword — it's not a detection keyword
            if keyword == "generic" {
                continue;
            }

            let kw_lower = keyword.to_lowercase();

            // Source 1: keyword found in prompt text (substring match)
            if prompt_lower.contains(&kw_lower) {
                matched_keywords.push(keyword.clone());
                continue;
            }

            // Source 2: keyword matches a project context signal
            // This catches cases like project having objective-c files but prompt
            // not mentioning it — the domain is still relevant
            if context_lower.iter().any(|ctx| ctx.contains(&kw_lower) || kw_lower.contains(ctx.as_str())) {
                matched_keywords.push(format!("ctx:{}", keyword));
            }
        }

        if !matched_keywords.is_empty() {
            debug!(
                "Domain '{}' detected via keywords: {:?}",
                canonical_name, matched_keywords
            );
            detected.insert(canonical_name.clone(), matched_keywords);
        }
    }

    detected
}

/// Check whether a single skill passes ALL its domain gates.
///
/// Gate logic:
/// - For each gate in the skill's domain_gates:
///   1. Normalize the gate name to canonical form (already done at index time)
///   2. Check if the canonical domain was detected from the prompt
///   3. If the gate contains "generic": passes if domain is detected (any keyword)
///   4. Otherwise: passes if at least one gate keyword appears in the prompt
/// - ALL gates must pass. If any gate fails, the skill is filtered out.
///
/// Returns (passes, failed_gate_name) — passes=true means all gates OK.
fn check_domain_gates(
    skill_name: &str,
    domain_gates: &HashMap<String, Vec<String>>,
    detected_domains: &DetectedDomains,
    prompt_lower: &str,
    registry: &DomainRegistry,
) -> (bool, Option<String>) {
    // Skills with no domain gates always pass
    if domain_gates.is_empty() {
        return (true, None);
    }

    for (gate_name, gate_keywords) in domain_gates {
        // The gate_name in skill-index.json should already be canonical
        // (set by haiku during indexing), but we do a lookup in the registry
        // to handle any aliases
        let canonical_name = find_canonical_domain(gate_name, registry);

        // Check if this domain was detected from the prompt
        let domain_detected = detected_domains.contains_key(&canonical_name);

        if !domain_detected {
            // Domain not detected in prompt at all — gate fails
            debug!(
                "Skill '{}' gate '{}' (canonical: '{}'): domain NOT detected in prompt → FAIL",
                skill_name, gate_name, canonical_name
            );
            return (false, Some(gate_name.clone()));
        }

        // Domain was detected. Now check if the specific gate keywords match.
        let has_generic = gate_keywords.iter().any(|kw| kw.to_lowercase() == "generic");

        if has_generic {
            // "generic" wildcard: domain detected = gate passes
            debug!(
                "Skill '{}' gate '{}': domain detected + generic wildcard → PASS",
                skill_name, gate_name
            );
            continue;
        }

        // Check if any gate keyword appears in the prompt
        let gate_passes = gate_keywords.iter().any(|kw| {
            prompt_lower.contains(&kw.to_lowercase())
        });

        if !gate_passes {
            debug!(
                "Skill '{}' gate '{}': domain detected but no gate keyword matched ({:?}) → FAIL",
                skill_name, gate_name, gate_keywords
            );
            return (false, Some(gate_name.clone()));
        }

        debug!(
            "Skill '{}' gate '{}': gate keyword matched → PASS",
            skill_name, gate_name
        );
    }

    (true, None)
}

/// Find the canonical domain name for a gate name.
/// Checks the registry domains and their aliases.
/// Falls back to the gate name itself if no match found.
fn find_canonical_domain(gate_name: &str, registry: &DomainRegistry) -> String {
    let gate_lower = gate_name.to_lowercase();

    // Direct match on canonical name
    if registry.domains.contains_key(&gate_lower) {
        return gate_lower;
    }

    // Check aliases in each domain
    for (canonical_name, entry) in &registry.domains {
        for alias in &entry.aliases {
            if alias.to_lowercase() == gate_lower {
                return canonical_name.clone();
            }
        }
    }

    // No match found — return gate name as-is (will likely fail detection)
    gate_lower
}

// ============================================================================
// Matching Logic (Enhanced with weighted scoring)
// ============================================================================

/// A matched skill with scoring details
#[derive(Debug)]
struct MatchedSkill {
    name: String,
    path: String,
    skill_type: String,
    description: String,
    score: i32,
    confidence: Confidence,
    evidence: Vec<String>,
}

/// Find matching skills with weighted scoring (combines reliable + LimorAI approaches)
///
/// # Arguments
/// * `original_prompt` - The original user prompt
/// * `expanded_prompt` - The prompt after synonym expansion
/// * `index` - The skill index to search
/// * `cwd` - Current working directory for directory context matching
/// * `context` - Project context for platform/framework/language filtering
/// * `incomplete_mode` - If true, skip co_usage boosts (for Pass 2 candidate finding)
#[allow(clippy::too_many_arguments)]
fn find_matches(
    original_prompt: &str,
    expanded_prompt: &str,
    index: &SkillIndex,
    cwd: &str,
    context: &ProjectContext,
    incomplete_mode: bool,
    detected_domains: &DetectedDomains,
    registry: Option<&DomainRegistry>,
) -> Vec<MatchedSkill> {
    let weights = MatchWeights::default();
    let thresholds = ConfidenceThresholds::default();
    let mut matches: Vec<MatchedSkill> = Vec::new();

    let original_lower = original_prompt.to_lowercase();
    let expanded_lower = expanded_prompt.to_lowercase();

    if incomplete_mode {
        debug!("INCOMPLETE MODE: Skipping tier boost and explicit boost fields");
    }

    // NOTE: The global domain gate early-exit (when ALL skills are gated and no
    // keyword matches) is handled in run() BEFORE this function is called. That
    // check uses a flat HashSet scan which is O(K) where K = total unique gate
    // keywords. By the time we reach this loop, at least one keyword matched or
    // some skills are ungated. Per-skill gate checks below handle individual filtering.

    for (name, entry) in &index.skills {
        let mut score: i32 = 0;
        let mut evidence: Vec<String> = Vec::new();
        let mut keyword_matches = 0;

        // Check negative keywords first (PSS feature) - skip if any match
        let has_negative = entry.negative_keywords.iter().any(|nk| {
            let nk_lower = nk.to_lowercase();
            original_lower.contains(&nk_lower) || expanded_lower.contains(&nk_lower)
        });
        if has_negative {
            debug!("Skipping skill '{}' due to negative keyword match", name);
            continue;
        }

        // Domain gate hard pre-filter: ALL gates must pass or skill is skipped entirely.
        // This runs before scoring because failing a gate is a hard disqualification.
        if let Some(reg) = registry {
            let (passes, failed_gate) = check_domain_gates(
                name,
                &entry.domain_gates,
                detected_domains,
                &original_lower,
                reg,
            );
            if !passes {
                debug!(
                    "Skipping skill '{}' due to domain gate '{}' failure",
                    name,
                    failed_gate.unwrap_or_default()
                );
                continue;
            }
        }

        // Project context matching (platform/framework/language)
        // This filters out platform-specific skills that don't match the detected context
        let (context_boost, should_filter) = context.match_skill(entry);
        if should_filter {
            debug!(
                "Skipping skill '{}' due to platform mismatch (skill: {:?}, context: {:?})",
                name, entry.platforms, context.platforms
            );
            continue;
        }
        if context_boost > 0 {
            score += context_boost;
            if !context.platforms.is_empty() && !entry.platforms.is_empty() {
                evidence.push(format!("platform:{:?}", entry.platforms));
            }
            if !context.frameworks.is_empty() && !entry.frameworks.is_empty() {
                evidence.push(format!("framework:{:?}", entry.frameworks));
            }
            if !context.languages.is_empty() && !entry.languages.is_empty() {
                evidence.push(format!("lang:{:?}", entry.languages));
            }
        }

        // Directory context matching
        for dir in &entry.directories {
            if cwd.contains(dir) {
                score += weights.directory;
                evidence.push(format!("dir:{}", dir));
            }
        }

        // Path pattern matching
        for path_pattern in &entry.path_patterns {
            if original_lower.contains(path_pattern) {
                score += weights.path;
                evidence.push(format!("path:{}", path_pattern));
            }
        }

        // Intent (verb) matching
        for intent in &entry.intents {
            if original_lower.contains(intent) || expanded_lower.contains(intent) {
                score += weights.intent;
                evidence.push(format!("intent:{}", intent));
            }
        }

        // Pattern (regex) matching
        for pattern in &entry.patterns {
            if let Ok(re) = Regex::new(pattern) {
                if re.is_match(&original_lower) || re.is_match(&expanded_lower) {
                    score += weights.pattern;
                    evidence.push(format!("pattern:{}", pattern));
                }
            }
        }

        // Keyword matching with first-match bonus (from LimorAI)
        // Also includes fuzzy matching for typo tolerance
        // Fixed: Now handles multi-word keyword phrases properly
        let prompt_words: Vec<&str> = expanded_lower.split_whitespace().collect();

        for keyword in &entry.keywords {
            let kw_lower = keyword.to_lowercase();
            let mut matched = false;
            let mut is_fuzzy = false;

            // Phase 1: Exact substring match (keyword phrase in prompt)
            if expanded_lower.contains(&kw_lower) {
                matched = true;
            }

            // Phase 2: Reverse word match (prompt words in keyword phrase)
            // This handles multi-word keywords like "bun bundler setup" when prompt is "implement bun"
            if !matched {
                // Split keyword into words for matching
                let keyword_words: Vec<&str> = kw_lower.split_whitespace().collect();

                // Check if any significant prompt word appears in the keyword phrase
                for prompt_word in &prompt_words {
                    // Skip very short words (articles, prepositions)
                    if prompt_word.len() < 3 {
                        continue;
                    }
                    // Check if prompt word matches any keyword word
                    for kw_word in &keyword_words {
                        if *prompt_word == *kw_word {
                            matched = true;
                            break;
                        }
                    }
                    if matched {
                        break;
                    }
                }
            }

            // Phase 2.5: Normalized + stemmed + abbreviation matching
            // Handles separator variants (geojson / geo-json / geo_json),
            // morphological forms (deploys/deploying/deployed → deploy,
            // tests/testing → test, libraries → library),
            // and common abbreviations (config ↔ configuration, repo ↔ repository).
            if !matched {
                let kw_norm = normalize_separators(&kw_lower);
                let kw_stem = stem_word(&kw_norm);
                for prompt_word in &prompt_words {
                    if prompt_word.len() < 2 {
                        continue;
                    }
                    let pw_norm = normalize_separators(prompt_word);
                    // Normalized form match (separator variants)
                    if pw_norm == kw_norm {
                        matched = true;
                        break;
                    }
                    // Stemmed form match (grammatical variants)
                    let pw_stem = stem_word(&pw_norm);
                    if pw_stem == kw_stem && pw_stem.len() >= 3 {
                        matched = true;
                        break;
                    }
                    // Abbreviation match (config ↔ configuration, etc.)
                    if is_abbreviation_match(&pw_norm, &kw_norm) {
                        matched = true;
                        break;
                    }
                }
            }

            // Phase 3: Fuzzy matching for typo tolerance (edit-distance, long words only)
            if !matched {
                // Split keyword into words for multi-word fuzzy matching
                let keyword_words: Vec<&str> = kw_lower.split_whitespace().collect();

                if keyword_words.len() == 1 {
                    // Single-word keyword - existing fuzzy logic
                    for word in &prompt_words {
                        if is_fuzzy_match(word, &kw_lower) {
                            matched = true;
                            is_fuzzy = true;
                            break;
                        }
                    }
                } else {
                    // Multi-word keyword - match each prompt word against each keyword word
                    for prompt_word in &prompt_words {
                        if prompt_word.len() < 3 {
                            continue;
                        }
                        for kw_word in &keyword_words {
                            if is_fuzzy_match(prompt_word, kw_word) {
                                matched = true;
                                is_fuzzy = true;
                                break;
                            }
                        }
                        if matched {
                            break;
                        }
                    }
                }
            }

            if matched {
                if keyword_matches == 0 {
                    // First keyword gets big bonus
                    score += weights.first_match;
                } else {
                    // Fuzzy matches get slightly less score than exact matches
                    score += if is_fuzzy { weights.keyword - 1 } else { weights.keyword };
                }
                keyword_matches += 1;

                // Original prompt bonus (not just expanded synonym match)
                if original_lower.contains(&kw_lower) {
                    score += weights.original_bonus;
                    evidence.push(format!("keyword*:{}", keyword)); // * = original
                } else if is_fuzzy {
                    evidence.push(format!("keyword~:{}", keyword)); // ~ = fuzzy match
                } else {
                    evidence.push(format!("keyword:{}", keyword));
                }
            }
        }

        // Apply tier boost from PSS file (skip in incomplete_mode - populated in Pass 2)
        if !incomplete_mode {
            let tier_boost = match entry.tier.as_str() {
                "primary" => 5,    // Primary elements get boost
                "secondary" => 0,  // Default, no change
                "specialized" => -2,   // Specialized elements slightly deprioritized
                _ => 0,
            };
            score += tier_boost;

            // Apply explicit boost from PSS file (-10 to +10)
            score += entry.boost.clamp(-10, 10);
        }

        // Cap score to prevent keyword stuffing
        score = score.min(weights.capped_max);

        // Determine confidence level (from reliable)
        let confidence = if score >= thresholds.high {
            Confidence::High
        } else if score >= thresholds.medium {
            Confidence::Medium
        } else {
            Confidence::Low
        };

        // Only include if score is meaningful
        if score >= 3 {
            matches.push(MatchedSkill {
                name: name.clone(),
                path: entry.path.clone(),
                skill_type: entry.skill_type.clone(),
                description: entry.description.clone(),
                score,
                confidence,
                evidence,
            });
        }
    }

    // Co-usage boosting (skip in incomplete_mode)
    // If a high-scoring skill lists another skill in usually_with, boost that skill
    if !incomplete_mode {
        // Collect names of high-scoring skills
        let high_score_threshold = 8;
        let high_scoring: Vec<String> = matches
            .iter()
            .filter(|m| m.score >= high_score_threshold)
            .map(|m| m.name.clone())
            .collect();

        // Build map of skill names that should get co-usage boost, with booster scores
        // Map: related_skill -> Vec<(booster_name, booster_score)>
        let mut co_usage_boosts: std::collections::HashMap<String, Vec<(String, i32)>> =
            std::collections::HashMap::new();

        // Create a score lookup from matches
        let score_lookup: std::collections::HashMap<&str, i32> = matches
            .iter()
            .map(|m| (m.name.as_str(), m.score))
            .collect();

        for matched_name in &high_scoring {
            if let Some(entry) = index.skills.get(matched_name) {
                let booster_score = *score_lookup.get(matched_name.as_str()).unwrap_or(&0);
                for related in &entry.usually_with {
                    co_usage_boosts
                        .entry(related.clone())
                        .or_default()
                        .push((matched_name.clone(), booster_score));
                }
            }
        }

        // Apply co-usage boosts to existing matches (proportional to booster score)
        for m in &mut matches {
            if let Some(boosters) = co_usage_boosts.get(&m.name) {
                // Boost is 50% of the highest booster's score, minimum 8
                // This ensures co-used skills rank near their boosters
                let max_booster_score = boosters.iter().map(|(_, s)| *s).max().unwrap_or(0);
                let co_boost = std::cmp::max(8, (max_booster_score * 50) / 100);
                m.score += co_boost;
                for (booster, _) in boosters {
                    m.evidence.push(format!("co_usage:{}", booster));
                }
            }
        }

        // Also add skills from co_usage that weren't matched at all
        for (related_name, boosters) in &co_usage_boosts {
            // Skip if already in matches
            if matches.iter().any(|m| &m.name == related_name) {
                continue;
            }
            // Add the related skill with score based on booster scores
            if let Some(entry) = index.skills.get(related_name) {
                let evidence: Vec<String> = boosters
                    .iter()
                    .map(|(b, _)| format!("co_usage:{}", b))
                    .collect();
                // Score is 40% of highest booster score + 2 per additional booster
                let max_booster_score = boosters.iter().map(|(_, s)| *s).max().unwrap_or(0);
                let score = std::cmp::max(10, (max_booster_score * 40) / 100) + ((boosters.len() as i32 - 1) * 2);
                matches.push(MatchedSkill {
                    name: related_name.clone(),
                    path: entry.path.clone(),
                    skill_type: entry.skill_type.clone(),
                    description: entry.description.clone(),
                    score,
                    confidence: Confidence::Medium,
                    evidence,
                });
            }
        }
    }

    // Sort by score descending, with skills-first ordering (from LimorAI/Scott Spence pattern)
    // Skills before agents before commands, within same score
    matches.sort_by(|a, b| {
        // First compare by score (descending)
        let score_cmp = b.score.cmp(&a.score);
        if score_cmp != std::cmp::Ordering::Equal {
            return score_cmp;
        }

        // If scores equal, order by type: skill > agent > command
        let type_order = |t: &str| match t {
            "skill" => 0,
            "agent" => 1,
            "command" => 2,
            _ => 3,
        };
        type_order(&a.skill_type).cmp(&type_order(&b.skill_type))
    });

    // Limit results
    matches.truncate(MAX_SUGGESTIONS);

    matches
}

/// Calculate relative score (0.0 to 1.0)
fn calculate_relative_score(score: i32, max_score: i32) -> f64 {
    if max_score <= 0 {
        return 0.0;
    }
    (score as f64) / (max_score as f64)
}

// ============================================================================
// Index Loading
// ============================================================================

/// Get the path to the skill index file.
/// Resolution order: --index CLI flag > PSS_INDEX_PATH env var > ~/.claude/cache/skill-index.json
fn get_index_path(cli_index: Option<&str>) -> Result<PathBuf, SuggesterError> {
    // 1. CLI flag takes priority (required on WASM targets)
    if let Some(path) = cli_index {
        return Ok(PathBuf::from(path));
    }

    // 2. Environment variable fallback
    if let Ok(path) = std::env::var("PSS_INDEX_PATH") {
        if !path.is_empty() {
            return Ok(PathBuf::from(path));
        }
    }

    // 3. Default: ~/.claude/cache/skill-index.json (native targets only)
    #[cfg(not(target_arch = "wasm32"))]
    {
        let home = dirs::home_dir().ok_or(SuggesterError::NoHomeDir)?;
        Ok(home.join(".claude").join(CACHE_DIR).join(INDEX_FILE))
    }

    // On WASM, --index or PSS_INDEX_PATH is required
    #[cfg(target_arch = "wasm32")]
    {
        Err(SuggesterError::NoHomeDir)
    }
}

/// Load and parse the skill index
fn load_index(path: &PathBuf) -> Result<SkillIndex, SuggesterError> {
    if !path.exists() {
        return Err(SuggesterError::IndexNotFound(path.clone()));
    }

    let content = fs::read_to_string(path).map_err(|e| SuggesterError::IndexRead {
        path: path.clone(),
        source: e,
    })?;

    let index: SkillIndex =
        serde_json::from_str(&content).map_err(|e| SuggesterError::IndexParse(e.to_string()))?;

    Ok(index)
}

// ============================================================================
// Domain Registry Loading
// ============================================================================

/// Get the path to the domain registry file.
/// Resolution order: --registry CLI flag > PSS_REGISTRY_PATH env var > ~/.claude/cache/domain-registry.json
fn get_registry_path(cli_registry: Option<&str>) -> Option<PathBuf> {
    // 1. CLI flag takes priority
    if let Some(path) = cli_registry {
        return Some(PathBuf::from(path));
    }

    // 2. Environment variable fallback
    if let Ok(path) = std::env::var("PSS_REGISTRY_PATH") {
        if !path.is_empty() {
            return Some(PathBuf::from(path));
        }
    }

    // 3. Default: ~/.claude/cache/domain-registry.json (native targets only)
    #[cfg(not(target_arch = "wasm32"))]
    {
        let home = dirs::home_dir()?;
        Some(home.join(".claude").join(CACHE_DIR).join(REGISTRY_FILE))
    }

    // On WASM, registry is not available unless explicitly set
    #[cfg(target_arch = "wasm32")]
    {
        None
    }
}

/// Load and parse the domain registry. Returns None if registry doesn't exist
/// (domain gates will not be enforced). Returns Err only on parse failure.
fn load_domain_registry(path: &PathBuf) -> Result<Option<DomainRegistry>, SuggesterError> {
    if !path.exists() {
        debug!("Domain registry not found at {:?}, domain gates will not be enforced", path);
        return Ok(None);
    }

    let content = fs::read_to_string(path).map_err(|e| SuggesterError::IndexRead {
        path: path.clone(),
        source: e,
    })?;

    let registry: DomainRegistry =
        serde_json::from_str(&content).map_err(|e| SuggesterError::IndexParse(
            format!("Failed to parse domain registry: {}", e)
        ))?;

    info!(
        "Loaded domain registry: {} domains from {:?}",
        registry.domains.len(),
        path
    );

    Ok(Some(registry))
}

// ============================================================================
// PSS File Loading
// ============================================================================

/// Load a single PSS file and merge it into the skill index
fn load_pss_file(pss_path: &PathBuf, index: &mut SkillIndex) -> Result<(), io::Error> {
    let content = fs::read_to_string(pss_path)?;
    let pss: PssFile = match serde_json::from_str(&content) {
        Ok(p) => p,
        Err(e) => {
            warn!("Failed to parse PSS file {:?}: {}", pss_path, e);
            return Ok(()); // Non-fatal, continue with other files
        }
    };

    // Check version
    if pss.version != "1.0" {
        warn!("Unsupported PSS version {} in {:?}", pss.version, pss_path);
        return Ok(());
    }

    let skill_name = &pss.skill.name;

    // If skill exists in index, merge PSS data
    if let Some(entry) = index.skills.get_mut(skill_name) {
        // Merge keywords (add any not already present)
        for kw in &pss.matchers.keywords {
            if !entry.keywords.contains(kw) {
                entry.keywords.push(kw.clone());
            }
        }

        // Merge intents
        for intent in &pss.matchers.intents {
            if !entry.intents.contains(intent) {
                entry.intents.push(intent.clone());
            }
        }

        // Merge patterns
        for pattern in &pss.matchers.patterns {
            if !entry.patterns.contains(pattern) {
                entry.patterns.push(pattern.clone());
            }
        }

        // Merge directories
        for dir in &pss.matchers.directories {
            if !entry.directories.contains(dir) {
                entry.directories.push(dir.clone());
            }
        }

        // Set negative keywords (PSS takes precedence)
        if !pss.matchers.negative_keywords.is_empty() {
            entry.negative_keywords = pss.matchers.negative_keywords.clone();
        }

        // Set scoring hints (PSS takes precedence)
        if !pss.scoring.tier.is_empty() {
            entry.tier = pss.scoring.tier.clone();
        }
        if pss.scoring.boost != 0 {
            entry.boost = pss.scoring.boost;
        }
        if !pss.scoring.category.is_empty() {
            entry.category = pss.scoring.category.clone();
        }

        debug!(
            "Merged PSS data for skill '{}': {} keywords, tier={}, boost={}",
            skill_name,
            entry.keywords.len(),
            entry.tier,
            entry.boost
        );
    } else {
        // Skill not in index - create new entry from PSS
        let skill_md_path = pss_path.with_file_name("SKILL.md");
        let path = if skill_md_path.exists() {
            skill_md_path.to_string_lossy().to_string()
        } else if !pss.skill.path.is_empty() {
            pss.skill.path.clone()
        } else {
            pss_path.parent().unwrap_or(pss_path).to_string_lossy().to_string()
        };

        let entry = SkillEntry {
            source: pss.skill.source.clone(),
            path,
            skill_type: pss.skill.skill_type.clone(),
            keywords: pss.matchers.keywords.clone(),
            intents: pss.matchers.intents.clone(),
            patterns: pss.matchers.patterns.clone(),
            directories: pss.matchers.directories.clone(),
            path_patterns: vec![],
            description: String::new(),
            negative_keywords: pss.matchers.negative_keywords.clone(),
            tier: pss.scoring.tier.clone(),
            boost: pss.scoring.boost,
            category: pss.scoring.category.clone(),
            // Platform/Framework/Language metadata (empty for PSS files - populated by reindex)
            platforms: vec![],
            frameworks: vec![],
            languages: vec![],
            domains: vec![],
            tools: vec![],
            file_types: vec![],
            // Domain gates (empty for PSS files - populated by reindex)
            domain_gates: HashMap::new(),
            // MCP server metadata (empty for PSS files - populated by reindex)
            server_type: String::new(),
            server_command: String::new(),
            server_args: vec![],
            // LSP server metadata (empty for PSS files - populated by reindex)
            language_ids: vec![],
            // Co-usage fields (empty for PSS files - populated by reindex)
            usually_with: vec![],
            precedes: vec![],
            follows: vec![],
            alternatives: vec![],
        };

        info!("Added skill '{}' from PSS file: {:?}", skill_name, pss_path);
        index.skills.insert(skill_name.clone(), entry);
    }

    Ok(())
}

/// Discover and load all PSS files from skill directories.
/// On WASM targets this is a no-op since there is no home directory.
#[cfg(not(target_arch = "wasm32"))]
fn load_pss_files(index: &mut SkillIndex) {
    let home = match dirs::home_dir() {
        Some(h) => h,
        None => {
            warn!("Could not get home directory for PSS file discovery");
            return;
        }
    };

    // Search locations for PSS files
    let search_paths = vec![
        home.join(".claude/skills"),
        home.join(".claude/agents"),
        home.join(".claude/commands"),
        PathBuf::from(".claude/skills"),
        PathBuf::from(".claude/agents"),
        PathBuf::from(".claude/commands"),
    ];

    let mut pss_count = 0;

    for search_path in search_paths {
        if !search_path.exists() {
            continue;
        }

        // Recursively find .pss files
        if let Ok(entries) = fs::read_dir(&search_path) {
            for entry in entries.flatten() {
                let path = entry.path();

                if path.is_dir() {
                    // Check for .pss file in skill directory
                    if let Ok(subentries) = fs::read_dir(&path) {
                        for subentry in subentries.flatten() {
                            let subpath = subentry.path();
                            // Load .pss files found in subdirectories
                            if subpath.extension().is_some_and(|e| e == "pss")
                                && load_pss_file(&subpath, index).is_ok()
                            {
                                pss_count += 1;
                            }
                        }
                    }
                } else if path.extension().is_some_and(|e| e == "pss")
                    && load_pss_file(&path, index).is_ok()
                {
                    pss_count += 1;
                }
            }
        }
    }

    if pss_count > 0 {
        info!("Loaded {} PSS files", pss_count);
    }
}

/// WASM stub: PSS file loading is not available (no home directory)
#[cfg(target_arch = "wasm32")]
fn load_pss_files(_index: &mut SkillIndex) {
    debug!("PSS file loading not available on WASM targets");
}

// ============================================================================
// Activation Logging
// ============================================================================

/// Get the path to the activation log file.
/// On WASM targets, returns None (no home directory for log storage).
#[cfg(not(target_arch = "wasm32"))]
fn get_log_path() -> Option<PathBuf> {
    let home = dirs::home_dir()?;
    let log_dir = home.join(".claude").join(LOG_DIR);

    // Create log directory if it doesn't exist
    if !log_dir.exists() {
        if let Err(e) = fs::create_dir_all(&log_dir) {
            warn!("Failed to create log directory {:?}: {}", log_dir, e);
            return None;
        }
    }

    Some(log_dir.join(ACTIVATION_LOG_FILE))
}

/// WASM stub: activation logging is not available (no home directory)
#[cfg(target_arch = "wasm32")]
fn get_log_path() -> Option<PathBuf> {
    None
}

/// Calculate a simple hash of the prompt for deduplication
fn hash_prompt(prompt: &str) -> String {
    // FNV-1a 64-bit — deterministic across runs unlike DefaultHasher
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in prompt.bytes() {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{:016x}", hash)
}

/// Truncate prompt for privacy while preserving meaning
fn truncate_prompt(prompt: &str, max_len: usize) -> String {
    if prompt.len() <= max_len {
        prompt.to_string()
    } else {
        // Find a word boundary near max_len
        let truncated = &prompt[..max_len];
        if let Some(last_space) = truncated.rfind(' ') {
            format!("{}...", &truncated[..last_space])
        } else {
            format!("{}...", truncated)
        }
    }
}

/// Log an activation event to the JSONL log file
fn log_activation(
    prompt: &str,
    session_id: Option<&str>,
    cwd: Option<&str>,
    subtask_count: usize,
    matches: &[MatchedSkill],
    processing_ms: Option<u64>,
) {
    // Get log path, skip logging if unavailable
    let log_path = match get_log_path() {
        Some(p) => p,
        None => {
            debug!("Activation logging disabled (no log path)");
            return;
        }
    };

    // Check if logging is disabled via environment variable
    if std::env::var("PSS_NO_LOGGING").is_ok() {
        debug!("Activation logging disabled via PSS_NO_LOGGING");
        return;
    }

    // Build log entry
    let entry = ActivationLogEntry {
        timestamp: Utc::now().to_rfc3339(),
        session_id: session_id.filter(|s| !s.is_empty()).map(String::from),
        prompt_preview: truncate_prompt(prompt, MAX_LOG_PROMPT_LENGTH),
        prompt_hash: hash_prompt(prompt),
        subtask_count,
        cwd: cwd.filter(|s| !s.is_empty()).map(String::from),
        matches: matches
            .iter()
            .map(|m| ActivationMatch {
                name: m.name.clone(),
                skill_type: m.skill_type.clone(),
                score: m.score,
                confidence: m.confidence.as_str().to_string(),
                evidence: m.evidence.clone(),
            })
            .collect(),
        processing_ms,
    };

    // Serialize to JSON line
    let json_line = match serde_json::to_string(&entry) {
        Ok(j) => j,
        Err(e) => {
            warn!("Failed to serialize activation log: {}", e);
            return;
        }
    };

    // Append to log file
    let result = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .and_then(|mut file| writeln!(file, "{}", json_line));

    match result {
        Ok(_) => debug!("Logged activation to {:?}", log_path),
        Err(e) => warn!("Failed to write activation log: {}", e),
    }

    // Check for log rotation (non-blocking, best effort)
    rotate_log_if_needed(&log_path);
}

/// Rotate log file if it exceeds MAX_LOG_ENTRIES
fn rotate_log_if_needed(log_path: &PathBuf) {
    // Count lines (fast approximation using file size)
    let metadata = match fs::metadata(log_path) {
        Ok(m) => m,
        Err(_) => return,
    };

    // Approximate: assume ~500 bytes per entry on average
    let estimated_entries = metadata.len() / 500;

    if estimated_entries < MAX_LOG_ENTRIES as u64 {
        return;
    }

    info!("Rotating activation log (estimated {} entries)", estimated_entries);

    // Create backup filename with timestamp
    let backup_name = format!(
        "pss-activations-{}.jsonl",
        Utc::now().format("%Y%m%d-%H%M%S")
    );
    let backup_path = log_path.with_file_name(&backup_name);

    // Rename current log to backup
    if let Err(e) = fs::rename(log_path, &backup_path) {
        warn!("Failed to rotate log file: {}", e);
        return;
    }

    info!("Rotated log to {:?}", backup_path);

    // Clean up old backups (keep last 5)
    if let Some(log_dir) = log_path.parent() {
        let mut backups: Vec<_> = fs::read_dir(log_dir)
            .into_iter()
            .flatten()
            .flatten()
            .filter(|e| {
                e.path()
                    .file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with("pss-activations-") && n.ends_with(".jsonl"))
                    .unwrap_or(false)
            })
            .collect();

        if backups.len() > 5 {
            // Sort by name (which includes timestamp) and remove oldest
            backups.sort_by_key(|e| e.path());
            for old_backup in backups.iter().take(backups.len() - 5) {
                if let Err(e) = fs::remove_file(old_backup.path()) {
                    warn!("Failed to remove old backup {:?}: {}", old_backup.path(), e);
                } else {
                    debug!("Removed old backup {:?}", old_backup.path());
                }
            }
        }
    }
}

// ============================================================================
// Main Entry Point
// ============================================================================

/// Run in agent-profile mode: score all skills against an agent descriptor,
/// synthesizing multiple queries from the agent's description, duties, and requirements.
/// Returns tiered recommendations as JSON.
fn run_agent_profile(cli: &Cli, profile_path: &str) -> Result<(), SuggesterError> {
    // Read and parse the agent descriptor JSON file
    let profile_json = fs::read_to_string(profile_path)
        .map_err(|e| SuggesterError::IndexRead { path: PathBuf::from(profile_path), source: e })?;
    let profile: AgentProfileInput = serde_json::from_str(&profile_json)?;

    info!("Agent profile mode: analyzing agent '{}'", profile.name);

    // Load skill index
    let index_path = get_index_path(cli.index.as_deref())?;
    let index = match load_index(&index_path) {
        Ok(idx) => idx,
        Err(SuggesterError::IndexNotFound(path)) => {
            error!("Skill index not found at {:?}", path);
            return Err(SuggesterError::IndexNotFound(path));
        }
        Err(e) => return Err(e),
    };
    info!("Loaded {} skills from index", index.skills.len());

    // Load domain registry (optional, graceful)
    let registry = match get_registry_path(cli.registry.as_deref()) {
        Some(reg_path) => match load_domain_registry(&reg_path) {
            Ok(Some(reg)) => {
                info!("Loaded domain registry: {} domains", reg.domains.len());
                Some(reg)
            }
            _ => None,
        },
        None => None,
    };

    // Build project context from the agent descriptor's cwd (if provided)
    let context = if !profile.cwd.is_empty() {
        let project_scan = scan_project_context(&profile.cwd);
        let mut ctx = ProjectContext::default();
        ctx.merge_scan(&project_scan);
        // Also inject the agent's declared domains/tools into context
        for d in &profile.domains {
            ctx.domains.push(d.to_lowercase());
        }
        for t in &profile.tools {
            ctx.tools.push(t.to_lowercase());
        }
        dedup_vec(&mut ctx.domains);
        dedup_vec(&mut ctx.tools);
        ctx
    } else {
        // No cwd: build context purely from agent descriptor fields
        ProjectContext {
            domains: profile.domains.iter().map(|d| d.to_lowercase()).collect(),
            tools: profile.tools.iter().map(|t| t.to_lowercase()).collect(),
            ..Default::default()
        }
    };

    // Synthesize multiple scoring queries from agent descriptor fields.
    // Each query is run through the full scoring pipeline independently,
    // and scores are aggregated per skill. This gives broad coverage:
    // the description catches general matches, duties catch action-oriented
    // matches, and requirements catch project-specific matches.
    let mut queries: Vec<String> = Vec::new();

    // Query 1: Full agent description (broadest match)
    if !profile.description.is_empty() {
        queries.push(profile.description.clone());
    }

    // Query 2: Role + domain as a phrase (matches category-level keywords)
    if !profile.role.is_empty() {
        let role_query = if profile.domains.is_empty() {
            profile.role.clone()
        } else {
            format!("{} {}", profile.role, profile.domains.join(" "))
        };
        queries.push(role_query);
    }

    // Query 3: Each duty as a separate query (matches action-oriented keywords)
    for duty in &profile.duties {
        if duty.len() > 5 {
            queries.push(duty.clone());
        }
    }

    // Query 4: Requirements summary (matches project-specific skills)
    if !profile.requirements_summary.is_empty() {
        queries.push(profile.requirements_summary.clone());
    }

    // Query 5: Tools as a query (matches tool-specific skills)
    if !profile.tools.is_empty() {
        queries.push(profile.tools.join(" "));
    }

    if queries.is_empty() {
        error!("Agent profile has no description, duties, or requirements to score against");
        let output = AgentProfileOutput {
            agent: profile.name,
            skills: AgentProfileSkills {
                primary: vec![],
                secondary: vec![],
                specialized: vec![],
            },
            complementary_agents: vec![],
            commands: vec![],
            rules: vec![],
            mcp: vec![],
            lsp: vec![],
        };
        println!("{}", serde_json::to_string_pretty(&output)?);
        return Ok(());
    }

    info!("Synthesized {} scoring queries from agent descriptor", queries.len());

    // Run each query through find_matches and aggregate scores per skill
    let mut skill_scores: HashMap<String, (i32, Vec<String>, String, String, String)> = HashMap::new();
    // Key: skill name, Value: (aggregated_score, merged_evidence, path, confidence_str, description)

    let empty_domains: DetectedDomains = HashMap::new();

    for (qi, query) in queries.iter().enumerate() {
        let corrected = correct_typos(query);
        let expanded = expand_synonyms(&corrected);

        // Detect domains for this query (uses registry if available)
        let detected_domains: DetectedDomains = match &registry {
            Some(reg) => {
                let mut context_signals: Vec<String> = Vec::new();
                context_signals.extend(context.domains.iter().cloned());
                context_signals.extend(context.tools.iter().cloned());
                context_signals.extend(context.frameworks.iter().cloned());
                context_signals.extend(context.languages.iter().cloned());
                detect_domains_from_prompt_with_context(&expanded, reg, &context_signals)
            }
            None => HashMap::new(),
        };

        let matches = find_matches(
            &corrected,
            &expanded,
            &index,
            &profile.cwd,
            &context,
            false, // not incomplete_mode — use full scoring including co_usage
            if detected_domains.is_empty() { &empty_domains } else { &detected_domains },
            registry.as_ref(),
        );

        debug!("Query {}/{}: '{}' → {} matches", qi + 1, queries.len(),
            &query[..query.len().min(60)], matches.len());

        for m in matches {
            let entry = skill_scores.entry(m.name.clone()).or_insert_with(|| {
                (0, Vec::new(), m.path.clone(), "LOW".to_string(), m.description.clone())
            });
            // Aggregate: add scores across queries
            entry.0 += m.score;
            // Merge evidence (deduplicated later)
            for ev in &m.evidence {
                if !entry.1.contains(ev) {
                    entry.1.push(ev.clone());
                }
            }
            // Keep highest confidence seen
            let conf_rank = |c: &str| -> u8 {
                match c { "HIGH" => 3, "MEDIUM" => 2, _ => 1 }
            };
            let new_conf = m.confidence.as_str().to_string();
            if conf_rank(&new_conf) > conf_rank(&entry.3) {
                entry.3 = new_conf;
            }
        }
    }

    // Sort skills by aggregated score descending
    let mut sorted_skills: Vec<(String, i32, Vec<String>, String, String, String)> = skill_scores
        .into_iter()
        .map(|(name, (score, evidence, path, confidence, description))| {
            (name, score, evidence, path, confidence, description)
        })
        .collect();
    sorted_skills.sort_by(|a, b| b.1.cmp(&a.1));

    // Find max score for relative scoring
    let max_score = sorted_skills.first().map(|s| s.1).unwrap_or(1).max(1);

    // Separate entries by type for multi-type output
    let mut skill_candidates: Vec<SkillCandidate> = Vec::new();
    let mut command_candidates: Vec<TypedCandidate> = Vec::new();
    let mut rule_candidates: Vec<TypedCandidate> = Vec::new();
    let mut mcp_candidates: Vec<TypedCandidate> = Vec::new();
    let mut lsp_candidates: Vec<TypedCandidate> = Vec::new();

    let top_n = cli.top;

    // Use a larger internal buffer so type-routing sees candidates across all types,
    // not just the top_n overall (which could all be one type, starving others).
    let internal_limit = (top_n * 5).max(20);

    for (name, score, evidence, path, confidence, description) in sorted_skills.into_iter().take(internal_limit) {
        // Look up the entry's type from the index
        let entry_type = index.skills.get(&name)
            .map(|e| e.skill_type.as_str())
            .unwrap_or("skill");

        match entry_type {
            "command" => command_candidates.push((name, score, evidence, path, confidence, description)),
            "rule" => rule_candidates.push((name, score, evidence, path, confidence, description)),
            "mcp" => mcp_candidates.push((name, score, evidence, path, confidence, description)),
            "lsp" => lsp_candidates.push((name, score, evidence, path, confidence, description)),
            // "skill" and "agent" go into the tiered skills output
            _ => skill_candidates.push((name, score, evidence, path, confidence, description, entry_type.to_string())),
        }
    }

    // Truncate non-skill type vectors to top_n (or 5, whichever is larger)
    // so each type gets fair representation after the expanded internal buffer.
    let per_type_limit = top_n.max(5);
    command_candidates.truncate(per_type_limit);
    rule_candidates.truncate(per_type_limit);
    mcp_candidates.truncate(per_type_limit);
    lsp_candidates.truncate(per_type_limit);

    // Classify skills+agents into tiers based on relative score
    let mut primary: Vec<AgentProfileCandidate> = Vec::new();
    let mut secondary: Vec<AgentProfileCandidate> = Vec::new();
    let mut specialized: Vec<AgentProfileCandidate> = Vec::new();

    for (name, score, evidence, path, confidence, description, _etype) in skill_candidates {
        let relative = (score as f64) / (max_score as f64);
        let candidate = AgentProfileCandidate {
            name,
            path,
            score: relative,
            confidence,
            evidence,
            description,
        };

        if relative >= 0.60 && primary.len() < 7 {
            primary.push(candidate);
        } else if relative >= 0.30 && secondary.len() < 12 {
            secondary.push(candidate);
        } else if relative >= 0.15 && specialized.len() < 8 {
            specialized.push(candidate);
        }
    }

    // Convert other type candidates to AgentProfileCandidate
    let to_candidates = |items: Vec<(String, i32, Vec<String>, String, String, String)>| -> Vec<AgentProfileCandidate> {
        items.into_iter().map(|(name, score, evidence, path, confidence, description)| {
            AgentProfileCandidate {
                name,
                path,
                score: (score as f64) / (max_score as f64),
                confidence,
                evidence,
                description,
            }
        }).collect()
    };

    // Find complementary agents from co_usage data of primary skills
    let mut complementary: HashSet<String> = HashSet::new();
    for p in &primary {
        if let Some(entry) = index.skills.get(&p.name) {
            for uw in &entry.usually_with {
                if let Some(uw_entry) = index.skills.get(uw.as_str()) {
                    if uw_entry.skill_type == "agent" {
                        complementary.insert(uw.clone());
                    }
                }
            }
        }
    }
    let complementary_agents: Vec<String> = complementary.into_iter().collect();

    info!(
        "Agent profile result: {} primary, {} secondary, {} specialized, {} complementary agents, {} commands, {} rules, {} mcp, {} lsp",
        primary.len(), secondary.len(), specialized.len(), complementary_agents.len(),
        command_candidates.len(), rule_candidates.len(), mcp_candidates.len(), lsp_candidates.len()
    );

    let output = AgentProfileOutput {
        agent: profile.name,
        skills: AgentProfileSkills {
            primary,
            secondary,
            specialized,
        },
        complementary_agents,
        commands: to_candidates(command_candidates),
        rules: to_candidates(rule_candidates),
        mcp: to_candidates(mcp_candidates),
        lsp: to_candidates(lsp_candidates),
    };

    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}

fn main() {
    // Initialize tracing if RUST_LOG is set
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_writer(std::io::stderr)
        .init();

    // Parse CLI arguments
    let cli = Cli::parse();

    if cli.incomplete_mode {
        info!("Running in INCOMPLETE MODE - co_usage data will be ignored");
    }

    // Dispatch: agent-profile mode vs normal hook mode
    let result = if let Some(ref profile_path) = cli.agent_profile {
        info!("Running in AGENT PROFILE mode: {}", profile_path);
        run_agent_profile(&cli, profile_path)
    } else {
        run(&cli)
    };

    if let Err(e) = result {
        error!("Error: {}", e);
        // Output empty response on error (non-blocking)
        let output = HookOutput::empty();
        println!("{}", serde_json::to_string(&output).unwrap_or_default());
        std::process::exit(0); // Exit 0 to not block Claude
    }
}

fn run(cli: &Cli) -> Result<(), SuggesterError> {
    // Read input from stdin
    let mut input_json = String::new();
    io::stdin().read_to_string(&mut input_json)?;

    debug!("Received input: {}", input_json);

    // Parse input
    let input: HookInput = serde_json::from_str(&input_json)?;

    // Skip processing for certain prompts
    let prompt_lower = input.prompt.to_lowercase();
    if is_skip_prompt(&prompt_lower) {
        debug!("Skipping prompt: {}", &input.prompt[..input.prompt.len().min(50)]);
        let output = HookOutput::empty();
        println!("{}", serde_json::to_string(&output)?);
        return Ok(());
    }

    info!(
        "Processing prompt: {}",
        &input.prompt[..input.prompt.len().min(50)]
    );

    // Start timing for activation logging
    let start_time = Instant::now();

    // Load skill index (--index flag > PSS_INDEX_PATH env > ~/.claude/cache/)
    let index_path = get_index_path(cli.index.as_deref())?;
    debug!("Loading index from: {:?}", index_path);

    let mut index = match load_index(&index_path) {
        Ok(idx) => idx,
        Err(SuggesterError::IndexNotFound(path)) => {
            warn!("Skill index not found at {:?}, returning empty", path);
            let output = HookOutput::empty();
            println!("{}", serde_json::to_string(&output)?);
            return Ok(());
        }
        Err(e) => return Err(e),
    };

    info!("Loaded {} skills from index", index.skills.len());

    // Load and merge PSS files only if --load-pss flag is passed
    // By default, only use skill-index.json (PSS files are now transient)
    if cli.load_pss {
        load_pss_files(&mut index);
    }

    // Load domain registry for domain gate filtering (graceful: no registry = no gate filtering)
    let registry = match get_registry_path(cli.registry.as_deref()) {
        Some(reg_path) => {
            debug!("Loading domain registry from: {:?}", reg_path);
            match load_domain_registry(&reg_path) {
                Ok(Some(reg)) => {
                    info!("Loaded domain registry: {} domains", reg.domains.len());
                    Some(reg)
                }
                Ok(None) => {
                    debug!("Domain registry not found at {:?}, gate filtering disabled", reg_path);
                    None
                }
                Err(e) => {
                    warn!("Failed to load domain registry: {}, gate filtering disabled", e);
                    None
                }
            }
        }
        None => {
            debug!("No domain registry path configured, gate filtering disabled");
            None
        }
    };

    // ========================================================================
    // STEP 1: Prepare full context BEFORE any domain checking.
    // Typo correction, synonym expansion, project metadata, and conversation
    // context must all be assembled first so the domain check runs against
    // the complete picture — not the raw prompt alone.
    // ========================================================================

    // 1a. Scan project directory for languages/frameworks/tools from config files.
    // This runs in Rust (not in the Python hook) because project contents can
    // change at any time and must be detected fresh on every invocation.
    let project_scan = scan_project_context(&input.cwd);
    if !project_scan.languages.is_empty() || !project_scan.tools.is_empty() {
        debug!(
            "Project scan: languages={:?}, frameworks={:?}, platforms={:?}, tools={:?}, file_types={:?}",
            project_scan.languages, project_scan.frameworks,
            project_scan.platforms, project_scan.tools, project_scan.file_types
        );
    }

    // Create project context by merging hook input with fresh disk scan results.
    // The hook may provide conversation-derived context (e.g., domains mentioned in chat)
    // that the Rust scan cannot detect, while the scan provides ground-truth project data.
    let mut context = ProjectContext::from_hook_input(&input);
    context.merge_scan(&project_scan);
    if !context.is_empty() {
        debug!(
            "Merged project context: platforms={:?}, frameworks={:?}, languages={:?}",
            context.platforms, context.frameworks, context.languages
        );
    }

    // 1b. Apply typo corrections (e.g., "pyhton" → "python") so domain keywords match
    let corrected_prompt = correct_typos(&input.prompt);
    if corrected_prompt != input.prompt.to_lowercase() {
        debug!("Typo-corrected prompt: {}", corrected_prompt);
    }

    // 1c. Expand synonyms (e.g., "k8s" → "kubernetes") so domain keywords match
    let expanded_prompt = expand_synonyms(&corrected_prompt);
    if expanded_prompt != corrected_prompt {
        debug!("Synonym-expanded prompt: {}", expanded_prompt);
    }

    // 1d. Build context signals by merging:
    //   - Rust project scan results (fresh, from config files on disk — computed in 1a)
    //   - Python hook context (may include conversation history, session metadata)
    // Both sources are merged because the hook may provide context the Rust scan
    // cannot detect (e.g., domains from recent conversation messages, tools mentioned
    // in chat). The Rust scan provides ground-truth project structure context.
    let mut context_signals: Vec<String> = Vec::new();
    // Rust scan results first (ground truth from disk, computed in step 1a)
    context_signals.extend(project_scan.languages.iter().cloned());
    context_signals.extend(project_scan.frameworks.iter().cloned());
    context_signals.extend(project_scan.platforms.iter().cloned());
    context_signals.extend(project_scan.tools.iter().cloned());
    context_signals.extend(project_scan.file_types.iter().cloned());
    // Hook-provided context (may overlap with scan — dedup handles this)
    context_signals.extend(input.context_languages.iter().cloned());
    context_signals.extend(input.context_frameworks.iter().cloned());
    context_signals.extend(input.context_platforms.iter().cloned());
    context_signals.extend(input.context_tools.iter().cloned());
    context_signals.extend(input.context_domains.iter().cloned());
    context_signals.extend(input.context_file_types.iter().cloned());
    // Deduplicate context signals (Rust scan and hook may report the same items)
    dedup_vec(&mut context_signals);

    // The full_context_text combines the corrected+expanded prompt with all context
    // signals into a single lowercased string for domain keyword scanning.
    // This ensures the domain check considers everything: the user's words (corrected),
    // their synonyms (expanded), and the project/conversation metadata.
    let full_context_text = {
        let mut parts: Vec<String> = vec![expanded_prompt.clone()];
        for sig in &context_signals {
            parts.push(sig.to_lowercase());
        }
        parts.join(" ")
    };

    // ========================================================================
    // STEP 2: Global domain gate early-exit.
    // Build a flat set of ALL domain keywords from ALL skills' gates, scan the
    // full context once, short-circuit on first match. If 0 matches AND all
    // skills are gated → exit immediately, skip all scoring.
    // ========================================================================
    if let Some(reg) = registry.as_ref() {
        let all_skills_gated = !index.skills.is_empty()
            && index.skills.values().all(|e| !e.domain_gates.is_empty());

        if all_skills_gated {
            // Collect every keyword that could satisfy any gate in any skill.
            // For "generic" gates: add the registry's example_keywords for that domain
            // (because generic passes when the domain is detected via any registry keyword).
            let mut all_gate_keywords: HashSet<String> = HashSet::new();

            for entry in index.skills.values() {
                for (gate_name, gate_keywords) in &entry.domain_gates {
                    let has_generic = gate_keywords.iter().any(|kw| kw.eq_ignore_ascii_case("generic"));

                    if has_generic {
                        let canonical = find_canonical_domain(gate_name, reg);
                        if let Some(domain_entry) = reg.domains.get(&canonical) {
                            for kw in &domain_entry.example_keywords {
                                if !kw.eq_ignore_ascii_case("generic") {
                                    all_gate_keywords.insert(kw.to_lowercase());
                                }
                            }
                        }
                    }

                    for kw in gate_keywords {
                        if !kw.eq_ignore_ascii_case("generic") {
                            all_gate_keywords.insert(kw.to_lowercase());
                        }
                    }
                }
            }

            // Single scan of full context: does ANY keyword appear?
            // Short-circuits on first match — O(1) best case, O(K) worst case.
            let any_match = all_gate_keywords.iter().any(|kw| {
                full_context_text.contains(kw.as_str())
            });

            if !any_match {
                info!(
                    "Domain gate early-exit: 0/{} gate keywords matched in prompt+context. \
                     All {} skills are gated. Skipping scoring entirely.",
                    all_gate_keywords.len(),
                    index.skills.len()
                );

                let processing_ms = start_time.elapsed().as_millis() as u64;
                let session_id = if input.session_id.is_empty() { None } else { Some(input.session_id.as_str()) };
                log_activation(
                    &input.prompt,
                    session_id,
                    Some(&input.cwd),
                    1,
                    &[],
                    Some(processing_ms),
                );

                let output = HookOutput::empty();
                println!("{}", serde_json::to_string(&output)?);
                return Ok(());
            }

            debug!(
                "Domain gate pre-check passed: at least one keyword matched from {} total gate keywords",
                all_gate_keywords.len()
            );
        }
    }

    // ========================================================================
    // STEP 3: Domain detection (uses corrected+expanded prompt + context).
    // Runs once and is shared across all sub-tasks.
    // ========================================================================
    let detected_domains: DetectedDomains = match &registry {
        Some(reg) => {
            let detected = detect_domains_from_prompt_with_context(
                &expanded_prompt,
                reg,
                &context_signals,
            );
            if !detected.is_empty() {
                info!(
                    "Detected {} domains in prompt: {:?}",
                    detected.len(),
                    detected.keys().collect::<Vec<_>>()
                );
            }
            detected
        }
        None => HashMap::new(),
    };

    // ========================================================================
    // STEP 4: Task decomposition and scoring.
    // ========================================================================
    let sub_tasks = decompose_tasks(&corrected_prompt);
    let is_multi_task = sub_tasks.len() > 1;

    if is_multi_task {
        info!("Decomposed prompt into {} sub-tasks", sub_tasks.len());
        for (i, task) in sub_tasks.iter().enumerate() {
            debug!("  Sub-task {}: {}", i + 1, &task[..task.len().min(50)]);
        }
    }

    let matches = if is_multi_task {
        let all_matches: Vec<Vec<MatchedSkill>> = sub_tasks
            .iter()
            .map(|task| {
                let task_expanded = expand_synonyms(task);
                find_matches(task, &task_expanded, &index, &input.cwd, &context, cli.incomplete_mode, &detected_domains, registry.as_ref())
            })
            .collect();

        aggregate_subtask_matches(all_matches)
    } else {
        find_matches(&corrected_prompt, &expanded_prompt, &index, &input.cwd, &context, cli.incomplete_mode, &detected_domains, registry.as_ref())
    };

    if matches.is_empty() {
        debug!("No matches found");

        // Log activation even for no matches (helps with analysis)
        let processing_ms = start_time.elapsed().as_millis() as u64;
        let session_id = if input.session_id.is_empty() { None } else { Some(input.session_id.as_str()) };
        log_activation(
            &input.prompt,
            session_id,
            Some(&input.cwd),
            sub_tasks.len(),
            &[],  // Empty matches
            Some(processing_ms),
        );

        let output = HookOutput::empty();
        println!("{}", serde_json::to_string(&output)?);
        return Ok(());
    }

    // Get max score for relative scoring
    let max_score = matches.iter().map(|m| m.score).max().unwrap_or(1);

    // Build output with confidence-based formatting (from reliable)
    let context_items: Vec<ContextItem> = matches
        .iter()
        .map(|m| {
            // Add commitment reminder for HIGH confidence (from reliable)
            let commitment = if m.confidence == Confidence::High {
                Some("Before implementing: Evaluate YES/NO - Will this skill solve the user's actual problem?".to_string())
            } else {
                None
            };

            ContextItem {
                item_type: m.skill_type.clone(),
                name: m.name.clone(),
                path: m.path.clone(),
                description: m.description.clone(),
                score: calculate_relative_score(m.score, max_score),
                confidence: m.confidence.as_str().to_string(),
                match_count: m.evidence.len(),
                evidence: m.evidence.clone(),
                commitment,
            }
        })
        .collect();

    // Log suggestions to stderr for debugging
    for item in &context_items {
        let conf_color = match item.confidence.as_str() {
            "HIGH" => item.confidence.green(),
            "MEDIUM" => item.confidence.yellow(),
            _ => item.confidence.red(),
        };
        info!(
            "{} {} [{}] - {} matches (score: {:.2}, confidence: {})",
            match item.item_type.as_str() {
                "skill" => "📚".green(),
                "agent" => "🤖".blue(),
                "command" => "⚡".yellow(),
                "rule" => "📏".cyan(),
                "mcp" => "🔌".magenta(),
                "lsp" => "🔤".white(),
                _ => "❓".white(),
            },
            item.name.bold(),
            item.item_type,
            item.match_count,
            item.score,
            conf_color
        );
    }

    // In hook mode, only suggest skills and agents (not rules/mcp/lsp which are configuration elements)
    let filtered_items: Vec<_> = context_items
        .into_iter()
        .filter(|item| {
            let t = item.item_type.as_str();
            t == "skill" || t == "agent" || t.is_empty()
        })
        .collect();

    // Apply filters: require evidence, min-score, then --top limit
    let limited_items: Vec<_> = filtered_items
        .into_iter()
        .filter(|item| !item.evidence.is_empty())  // Must have at least 1 keyword match
        .filter(|item| item.score >= cli.min_score)
        .take(cli.top)
        .collect();

    // Log activation with matches and timing
    let processing_ms = start_time.elapsed().as_millis() as u64;
    let session_id = if input.session_id.is_empty() { None } else { Some(input.session_id.as_str()) };
    log_activation(
        &input.prompt,
        session_id,
        Some(&input.cwd),
        sub_tasks.len(),
        &matches,
        Some(processing_ms),
    );

    // Output based on --format option
    match cli.format.as_str() {
        "json" => {
            // Raw JSON format for Pass 2 agents - just skill metadata
            #[derive(Serialize)]
            struct CandidateSkill {
                name: String,
                path: String,
                pss_path: String,  // Path to .pss file for reading
                score: f64,
                confidence: String,
                keywords_matched: Vec<String>,
            }

            let candidates: Vec<CandidateSkill> = limited_items
                .iter()
                .map(|item| {
                    // PSS files are transient, not persisted next to SKILL.md
                    let pss_path = String::new();

                    CandidateSkill {
                        name: item.name.clone(),
                        path: item.path.clone(),
                        pss_path,
                        score: item.score,
                        confidence: item.confidence.clone(),
                        keywords_matched: item.evidence.clone(),
                    }
                })
                .collect();

            println!("{}", serde_json::to_string_pretty(&candidates)?);
        }
        _ => {
            // Default hook format for Claude Code integration
            let output = HookOutput::with_suggestions(limited_items);
            println!("{}", serde_json::to_string(&output)?);
        }
    }

    Ok(())
}

/// Check if prompt should be skipped (simple words, task notifications)
fn is_skip_prompt(prompt: &str) -> bool {
    // Skip task notifications
    if prompt.contains("<task-notification>") {
        return true;
    }

    // Skip simple words
    let simple_words = [
        "continue", "yes", "no", "ok", "okay", "thanks", "sure", "done", "stop", "got it",
        "y", "n", "yep", "nope", "thank you", "thx", "ty", "next", "go", "proceed",
    ];

    let trimmed = prompt.trim().to_lowercase();
    simple_words.contains(&trimmed.as_str())
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_index() -> SkillIndex {
        let mut skills = HashMap::new();

        skills.insert(
            "devops-expert".to_string(),
            SkillEntry {
                source: "plugin".to_string(),
                path: "/path/to/devops-expert/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec![
                    "github".to_string(),
                    "actions".to_string(),
                    "ci".to_string(),
                    "cd".to_string(),
                    "pipeline".to_string(),
                    "deploy".to_string(),
                ],
                intents: vec!["deploy".to_string(), "build".to_string(), "release".to_string()],
                patterns: vec![],
                directories: vec!["workflows".to_string(), ".github".to_string()],
                path_patterns: vec![],
                description: "CI/CD pipeline configuration".to_string(),
                negative_keywords: vec![],
                tier: "primary".to_string(),
                boost: 0,
                category: "devops".to_string(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        skills.insert(
            "docker-expert".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/docker-expert/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec![
                    "docker".to_string(),
                    "container".to_string(),
                    "dockerfile".to_string(),
                    "compose".to_string(),
                ],
                intents: vec!["containerize".to_string(), "build".to_string()],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Docker containerization".to_string(),
                negative_keywords: vec!["kubernetes".to_string()],  // Test negative keywords
                tier: "secondary".to_string(),
                boost: 0,
                category: "containerization".to_string(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "ai-analyzed".to_string(),
            skills_count: 2,
            skills,
        }
    }

    #[test]
    fn test_synonym_expansion() {
        let expanded = expand_synonyms("help me set up a pr for deployment");
        assert!(expanded.contains("github"));
        assert!(expanded.contains("pull request"));
        assert!(expanded.contains("deployment"));
    }

    #[test]
    fn test_find_matches_with_synonyms() {
        let index = create_test_index();
        let original = "help me set up github actions";
        let expanded = expand_synonyms(original);
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);

        assert!(!matches.is_empty());
        assert_eq!(matches[0].name, "devops-expert");
        assert!(matches[0].score >= 10); // Should have first match bonus
    }

    #[test]
    fn test_confidence_levels() {
        let index = create_test_index();

        // HIGH confidence - many keyword matches
        let original = "help me deploy github actions ci cd pipeline";
        let expanded = expand_synonyms(original);
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);
        assert!(!matches.is_empty());
        assert_eq!(matches[0].confidence, Confidence::High);

        // LOW confidence - single keyword
        let original2 = "help me with docker";
        let expanded2 = expand_synonyms(original2);
        let matches2 = find_matches(original2, &expanded2, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);
        assert!(!matches2.is_empty());
        // Score should be lower
    }

    #[test]
    fn test_directory_boost() {
        let index = create_test_index();
        let original = "help me with this file";
        let expanded = expand_synonyms(original);

        // With matching directory
        let matches_with_dir = find_matches(original, &expanded, &index, "/project/.github/workflows", &ProjectContext::default(), false, &HashMap::new(), None);

        // Without matching directory
        let matches_no_dir = find_matches(original, &expanded, &index, "/project/src", &ProjectContext::default(), false, &HashMap::new(), None);

        // Directory match should boost score
        if !matches_with_dir.is_empty() && !matches_no_dir.is_empty() {
            let devops_with = matches_with_dir.iter().find(|m| m.name == "devops-expert");
            let devops_without = matches_no_dir.iter().find(|m| m.name == "devops-expert");

            if let (Some(w), Some(wo)) = (devops_with, devops_without) {
                assert!(w.score > wo.score);
            }
        }
    }

    #[test]
    fn test_skip_prompts() {
        assert!(is_skip_prompt("yes"));
        assert!(is_skip_prompt("no"));
        assert!(is_skip_prompt("continue"));
        assert!(is_skip_prompt("<task-notification>something</task-notification>"));
        assert!(!is_skip_prompt("help me deploy"));
    }

    #[test]
    fn test_calculate_relative_score() {
        assert_eq!(calculate_relative_score(5, 10), 0.5);
        assert_eq!(calculate_relative_score(10, 10), 1.0);
        assert_eq!(calculate_relative_score(0, 10), 0.0);
        assert_eq!(calculate_relative_score(5, 0), 0.0);
    }

    #[test]
    fn test_negative_keywords() {
        let index = create_test_index();

        // Docker prompt with kubernetes mention should NOT match docker-expert
        // because kubernetes is a negative keyword for docker-expert
        let original = "help me with docker and kubernetes";
        let expanded = expand_synonyms(original);
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);

        // Docker-expert should be filtered out due to "kubernetes" negative keyword
        let docker_match = matches.iter().find(|m| m.name == "docker-expert");
        assert!(docker_match.is_none(), "docker-expert should be filtered due to negative keyword 'kubernetes'");
    }

    #[test]
    fn test_tier_boost() {
        let index = create_test_index();

        // devops-expert has tier=primary, which gives +5 boost
        // Test that primary tier skills rank higher
        let original = "help me deploy to ci";
        let expanded = expand_synonyms(original);
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);

        if !matches.is_empty() {
            let devops_match = matches.iter().find(|m| m.name == "devops-expert");
            assert!(devops_match.is_some());
            // Primary tier skill should have higher score due to +5 tier boost
        }
    }

    #[test]
    fn test_skills_first_ordering() {
        // Create index with same-scoring skill and agent
        let mut skills = HashMap::new();

        skills.insert(
            "test-skill".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/test-skill/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec!["test".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Test skill".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        skills.insert(
            "test-agent".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/test-agent.md".to_string(),
                skill_type: "agent".to_string(),
                keywords: vec!["test".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Test agent".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 2,
            skills,
        };

        let matches = find_matches("run test", "run test", &index, "", &ProjectContext::default(), false, &HashMap::new(), None);

        // With same scores, skill should come before agent
        if matches.len() >= 2 {
            let first_type = &matches[0].skill_type;
            let second_type = &matches[1].skill_type;
            if first_type == "skill" || second_type == "skill" {
                // If there's a skill in results, it should be first
                if matches.iter().any(|m| m.skill_type == "skill") && matches.iter().any(|m| m.skill_type == "agent") {
                    assert_eq!(matches[0].skill_type, "skill", "Skill should come before agent when scores are equal");
                }
            }
        }
    }

    // ========================================================================
    // Typo Tolerance Tests
    // ========================================================================

    #[test]
    fn test_correct_typos() {
        // Test common programming language typos
        assert_eq!(correct_typos("help with typscript"), "help with typescript");
        assert_eq!(correct_typos("help with pyhton"), "help with python");
        assert_eq!(correct_typos("help with javscript"), "help with javascript");

        // Test DevOps/Cloud typos
        assert_eq!(correct_typos("deploy to kuberntes"), "deploy to kubernetes");
        assert_eq!(correct_typos("build dokcer image"), "build docker image");

        // Test Git typos
        assert_eq!(correct_typos("push to githb"), "push to github");
        assert_eq!(correct_typos("create new brach"), "create new branch");

        // Test multiple typos in one string
        assert_eq!(
            correct_typos("deploy pyhton app to kuberntes"),
            "deploy python app to kubernetes"
        );

        // Test non-typos are preserved
        assert_eq!(correct_typos("help me with docker"), "help me with docker");
    }

    #[test]
    fn test_damerau_levenshtein_distance() {
        // Same strings = 0
        assert_eq!(damerau_levenshtein_distance("docker", "docker"), 0);

        // One character difference = 1
        assert_eq!(damerau_levenshtein_distance("docker", "doker"), 1);   // missing 'c'
        assert_eq!(damerau_levenshtein_distance("test", "tset"), 1);      // transposition = 1 in Damerau

        // Missing character and transposition
        assert_eq!(damerau_levenshtein_distance("typescript", "typscript"), 1); // missing 'e'
        assert_eq!(damerau_levenshtein_distance("kubernetes", "kuberntes"), 1); // transposition = 1

        // Transposition examples
        assert_eq!(damerau_levenshtein_distance("git", "gti"), 1);     // transposition 'i' and 't'
        assert_eq!(damerau_levenshtein_distance("abc", "bac"), 1);     // transposition 'a' and 'b'

        // Empty strings
        assert_eq!(damerau_levenshtein_distance("", "abc"), 3);
        assert_eq!(damerau_levenshtein_distance("abc", ""), 3);
        assert_eq!(damerau_levenshtein_distance("", ""), 0);
    }

    #[test]
    fn test_is_fuzzy_match() {
        // Short words rejected (< 6 chars) to prevent false positives like lint→link, fix→fax
        assert!(!is_fuzzy_match("git", "gti")); // Too short for fuzzy matching
        assert!(!is_fuzzy_match("ab", "cd")); // Too short

        // Medium words
        assert!(is_fuzzy_match("docker", "dokcer")); // 1 edit distance
        assert!(is_fuzzy_match("github", "githb")); // 1 edit distance
        assert!(is_fuzzy_match("pipeline", "pipline")); // 1 edit distance
        assert!(is_fuzzy_match("kubernetes", "kuberntes")); // 2 edit distance

        // Length difference threshold
        assert!(!is_fuzzy_match("typescript", "ts")); // Too different in length

        // No match when completely different
        assert!(!is_fuzzy_match("docker", "python")); // Completely different
    }

    #[test]
    fn test_fuzzy_matching_in_find_matches() {
        // Create index with typescript skill
        let mut skills = HashMap::new();

        skills.insert(
            "typescript-expert".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/typescript-expert/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec![
                    "typescript".to_string(),
                    "ts".to_string(),
                    "interface".to_string(),
                ],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "TypeScript development".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 1,
            skills,
        };

        // Test with typo "typscript" - should still match "typescript" via fuzzy matching
        let original = "help me with typscript code";
        let corrected = correct_typos(original);
        let expanded = expand_synonyms(&corrected);
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None);

        assert!(!matches.is_empty(), "Should match typescript-expert even with typo");
        assert_eq!(matches[0].name, "typescript-expert");
    }

    #[test]
    fn test_typo_correction_preserves_unknown_words() {
        // Unknown words should pass through unchanged
        assert_eq!(
            correct_typos("help me with verylongunknownword"),
            "help me with verylongunknownword"
        );

        // Mix of known typos and unknown words
        assert_eq!(
            correct_typos("deploy pyhton to mysteriousserver"),
            "deploy python to mysteriousserver"
        );
    }

    // ========================================================================
    // Task Decomposition Tests
    // ========================================================================

    #[test]
    fn test_decompose_simple_prompt() {
        // Simple prompt should not be decomposed
        let result = decompose_tasks("help me with docker");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "help me with docker");
    }

    #[test]
    fn test_decompose_and_then_pattern() {
        // "X and then Y" pattern
        let result = decompose_tasks("help me deploy the app and then run the tests");
        assert_eq!(result.len(), 2);
        assert!(result[0].contains("deploy"));
        assert!(result[1].contains("tests"));
    }

    #[test]
    fn test_decompose_semicolon_pattern() {
        // "X; Y" pattern
        let result = decompose_tasks("create the dockerfile; deploy to kubernetes; run tests");
        assert_eq!(result.len(), 3);
        assert!(result[0].contains("dockerfile"));
        assert!(result[1].contains("kubernetes"));
        assert!(result[2].contains("tests"));
    }

    #[test]
    fn test_decompose_also_pattern() {
        // "X also Y" pattern
        let result = decompose_tasks("help me with docker also configure the ci pipeline");
        assert_eq!(result.len(), 2);
        assert!(result[0].contains("docker"));
        assert!(result[1].contains("pipeline"));
    }

    #[test]
    fn test_decompose_numbered_list() {
        // "1. X 2. Y 3. Z" pattern
        let result = decompose_tasks("1. create docker image 2. deploy to cloud 3. run tests");
        assert!(result.len() >= 2, "Should decompose numbered list");
    }

    #[test]
    fn test_decompose_short_prompt_unchanged() {
        // Very short prompts should not be decomposed
        let result = decompose_tasks("fix bug");
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_decompose_no_action_verbs() {
        // Prompts without action verbs should not be decomposed
        let result = decompose_tasks("the docker container and the kubernetes cluster are related");
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_aggregate_subtask_matches() {
        // Create mock matches from two sub-tasks
        let match1 = MatchedSkill {
            name: "docker-expert".to_string(),
            path: "/path/to/docker".to_string(),
            skill_type: "skill".to_string(),
            description: "Docker help".to_string(),
            score: 15,
            confidence: Confidence::High,
            evidence: vec!["keyword:docker".to_string()],
        };

        let match2_same = MatchedSkill {
            name: "docker-expert".to_string(),
            path: "/path/to/docker".to_string(),
            skill_type: "skill".to_string(),
            description: "Docker help".to_string(),
            score: 12,
            confidence: Confidence::Medium,
            evidence: vec!["keyword:container".to_string()],
        };

        let match3 = MatchedSkill {
            name: "kubernetes-expert".to_string(),
            path: "/path/to/k8s".to_string(),
            skill_type: "skill".to_string(),
            description: "K8s help".to_string(),
            score: 10,
            confidence: Confidence::Medium,
            evidence: vec!["keyword:kubernetes".to_string()],
        };

        let all_matches = vec![
            vec![match1],
            vec![match2_same, match3],
        ];

        let aggregated = aggregate_subtask_matches(all_matches);

        // Should have 2 unique skills
        assert_eq!(aggregated.len(), 2);

        // Docker should be first (higher score + multi-task bonus)
        let docker = aggregated.iter().find(|m| m.name == "docker-expert");
        assert!(docker.is_some());
        let docker = docker.unwrap();
        // Score should be max(15, 12) + 2 (multi-task bonus) = 17
        assert_eq!(docker.score, 17);
        // Evidence should be merged
        assert!(docker.evidence.len() >= 2);
    }

    #[test]
    fn test_multi_task_matching() {
        let index = create_test_index();

        // Multi-task prompt: docker + ci/cd
        let original = "help me build docker image and then deploy to github actions";
        let corrected = correct_typos(original);
        let sub_tasks = decompose_tasks(&corrected);

        // Should decompose
        assert!(sub_tasks.len() >= 2, "Should decompose into at least 2 sub-tasks");

        // Process each sub-task
        let all_matches: Vec<Vec<MatchedSkill>> = sub_tasks
            .iter()
            .map(|task| {
                let expanded = expand_synonyms(task);
                find_matches(task, &expanded, &index, "", &ProjectContext::default(), false, &HashMap::new(), None)
            })
            .collect();

        // Aggregate
        let aggregated = aggregate_subtask_matches(all_matches);

        // Should find both docker-expert and devops-expert
        let _skill_names: Vec<&str> = aggregated.iter().map(|m| m.name.as_str()).collect();
        // At least one of the skills should be found
        assert!(!aggregated.is_empty(), "Should find at least one matching skill");
    }

    // ========================================================================
    // Activation Logging Tests
    // ========================================================================

    #[test]
    fn test_hash_prompt() {
        // Same prompt should produce same hash
        let hash1 = hash_prompt("help me with docker");
        let hash2 = hash_prompt("help me with docker");
        assert_eq!(hash1, hash2);

        // Different prompts should produce different hashes
        let hash3 = hash_prompt("help me with kubernetes");
        assert_ne!(hash1, hash3);

        // Hash should be 16 hex characters
        assert_eq!(hash1.len(), 16);
        assert!(hash1.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_truncate_prompt() {
        // Short prompt unchanged
        let short = "help me with docker";
        assert_eq!(truncate_prompt(short, 100), short);

        // Long prompt truncated at word boundary
        let long = "help me with a very long prompt that exceeds the maximum length and should be truncated at a word boundary";
        let truncated = truncate_prompt(long, 50);
        assert!(truncated.len() <= 53); // 50 + "..."
        assert!(truncated.ends_with("..."));
        assert!(!truncated.contains("boundary")); // Should be cut before this

        // Exact boundary case
        let exact = "1234567890";
        assert_eq!(truncate_prompt(exact, 10), exact);
    }

    #[test]
    fn test_get_log_path() {
        // Should return a valid path
        let path = get_log_path();
        assert!(path.is_some());

        let path = path.unwrap();
        assert!(path.to_string_lossy().contains(".claude"));
        assert!(path.to_string_lossy().contains("logs"));
        assert!(path.to_string_lossy().ends_with("pss-activations.jsonl"));
    }

    #[test]
    fn test_activation_log_entry_serialization() {
        let entry = ActivationLogEntry {
            timestamp: "2026-01-18T00:00:00Z".to_string(),
            session_id: Some("test-session".to_string()),
            prompt_preview: "help me with docker...".to_string(),
            prompt_hash: "0123456789abcdef".to_string(),
            subtask_count: 1,
            cwd: Some("/project".to_string()),
            matches: vec![
                ActivationMatch {
                    name: "docker-expert".to_string(),
                    skill_type: "skill".to_string(),
                    score: 15,
                    confidence: "HIGH".to_string(),
                    evidence: vec!["keyword:docker".to_string()],
                },
            ],
            processing_ms: Some(5),
        };

        // Serialize to JSON
        let json = serde_json::to_string(&entry).unwrap();

        // Verify required fields are present
        assert!(json.contains("\"timestamp\""));
        assert!(json.contains("\"prompt_preview\""));
        assert!(json.contains("\"prompt_hash\""));
        assert!(json.contains("\"matches\""));
        assert!(json.contains("\"docker-expert\""));

        // Verify type field is renamed
        assert!(json.contains("\"type\":\"skill\""));

        // Deserialize back and verify
        let parsed: ActivationLogEntry = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.timestamp, entry.timestamp);
        assert_eq!(parsed.session_id, entry.session_id);
        assert_eq!(parsed.matches.len(), 1);
        assert_eq!(parsed.matches[0].name, "docker-expert");
    }

    #[test]
    fn test_activation_log_entry_optional_fields() {
        // Entry with None values - should skip serialization
        let entry = ActivationLogEntry {
            timestamp: "2026-01-18T00:00:00Z".to_string(),
            session_id: None,
            prompt_preview: "test".to_string(),
            prompt_hash: "abc123".to_string(),
            subtask_count: 1,
            cwd: None,
            matches: vec![],
            processing_ms: None,
        };

        let json = serde_json::to_string(&entry).unwrap();

        // Optional None fields should NOT be present
        assert!(!json.contains("session_id"));
        assert!(!json.contains("cwd"));
        assert!(!json.contains("processing_ms"));
    }

    // ========================================================================
    // Domain Gate Tests
    // ========================================================================

    /// Build a minimal DomainRegistry for testing domain gate filtering
    fn create_test_registry() -> DomainRegistry {
        let mut domains = HashMap::new();

        domains.insert(
            "target_language".to_string(),
            DomainRegistryEntry {
                canonical_name: "target_language".to_string(),
                aliases: vec!["target_language".to_string(), "programming_language".to_string(), "lang_target".to_string()],
                example_keywords: vec![
                    "python".to_string(), "rust".to_string(), "javascript".to_string(),
                    "typescript".to_string(), "go".to_string(), "swift".to_string(),
                    "objective-c".to_string(), "java".to_string(), "c++".to_string(),
                ],
                has_generic: false,
                skill_count: 5,
                skills: vec![],
            },
        );

        domains.insert(
            "cloud_provider".to_string(),
            DomainRegistryEntry {
                canonical_name: "cloud_provider".to_string(),
                aliases: vec!["cloud_provider".to_string()],
                example_keywords: vec![
                    "aws".to_string(), "gcp".to_string(), "azure".to_string(),
                    "heroku".to_string(), "vercel".to_string(),
                ],
                has_generic: false,
                skill_count: 2,
                skills: vec![],
            },
        );

        domains.insert(
            "output_format".to_string(),
            DomainRegistryEntry {
                canonical_name: "output_format".to_string(),
                aliases: vec!["output_format".to_string()],
                example_keywords: vec![
                    "generic".to_string(), "json".to_string(), "csv".to_string(),
                    "xml".to_string(), "yaml".to_string(),
                ],
                has_generic: true,
                skill_count: 3,
                skills: vec![],
            },
        );

        DomainRegistry {
            version: "1.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            source_index: "test".to_string(),
            domain_count: 3,
            domains,
        }
    }

    #[test]
    fn test_domain_gate_no_gates_always_passes() {
        // A skill with no domain_gates should always pass the gate check
        let registry = create_test_registry();
        let detected: DetectedDomains = HashMap::new();
        let empty_gates: HashMap<String, Vec<String>> = HashMap::new();

        let (passes, failed) = check_domain_gates("test-skill", &empty_gates, &detected, "any prompt", &registry);
        assert!(passes, "Skills with no gates should always pass");
        assert!(failed.is_none());
    }

    #[test]
    fn test_domain_gate_filters_out_unmatched_skill() {
        // A skill gated on target_language=["python", "rust"] should be filtered
        // when the prompt mentions "objective-c" (a different language)
        let registry = create_test_registry();

        // Prompt mentions objective-c → target_language domain detected
        let detected = detect_domains_from_prompt("help me debug this objective-c code", &registry);
        assert!(detected.contains_key("target_language"), "target_language domain should be detected");

        // Skill requires python or rust
        let mut gates = HashMap::new();
        gates.insert("target_language".to_string(), vec!["python".to_string(), "rust".to_string()]);

        let (passes, failed) = check_domain_gates(
            "python-debug-skill",
            &gates,
            &detected,
            "help me debug this objective-c code",
            &registry,
        );
        // Gate should fail: domain detected but keywords don't match
        assert!(!passes, "Gate should fail — prompt mentions objective-c, not python/rust");
        assert_eq!(failed, Some("target_language".to_string()));
    }

    #[test]
    fn test_domain_gate_passes_matching_skill() {
        // A skill gated on target_language=["python", "rust"] should pass
        // when the prompt mentions "python"
        let registry = create_test_registry();

        let detected = detect_domains_from_prompt("help me write python tests", &registry);
        assert!(detected.contains_key("target_language"));

        let mut gates = HashMap::new();
        gates.insert("target_language".to_string(), vec!["python".to_string(), "rust".to_string()]);

        let (passes, failed) = check_domain_gates(
            "python-test-skill",
            &gates,
            &detected,
            "help me write python tests",
            &registry,
        );
        assert!(passes, "Gate should pass — prompt mentions python which is in the gate keywords");
        assert!(failed.is_none());
    }

    #[test]
    fn test_domain_gate_generic_wildcard() {
        // A skill with "generic" in its gate keywords should pass whenever
        // the domain is detected, regardless of which specific keyword matched
        let registry = create_test_registry();

        // Prompt mentions "json" → output_format domain detected
        let detected = detect_domains_from_prompt("convert this data to json format", &registry);
        assert!(detected.contains_key("output_format"));

        // Skill uses generic wildcard for output_format
        let mut gates = HashMap::new();
        gates.insert("output_format".to_string(), vec!["generic".to_string()]);

        let (passes, failed) = check_domain_gates(
            "data-converter",
            &gates,
            &detected,
            "convert this data to json format",
            &registry,
        );
        assert!(passes, "Gate should pass — generic wildcard + domain detected");
        assert!(failed.is_none());
    }

    #[test]
    fn test_domain_gate_generic_fails_when_domain_not_detected() {
        // Even with "generic" wildcard, the gate should fail if the domain
        // itself is not detected at all in the prompt
        let registry = create_test_registry();

        // Prompt mentions nothing about output formats
        let detected = detect_domains_from_prompt("help me deploy to aws", &registry);
        assert!(!detected.contains_key("output_format"), "output_format should NOT be detected");

        // Skill uses generic wildcard for output_format
        let mut gates = HashMap::new();
        gates.insert("output_format".to_string(), vec!["generic".to_string()]);

        let (passes, failed) = check_domain_gates(
            "data-converter",
            &gates,
            &detected,
            "help me deploy to aws",
            &registry,
        );
        assert!(!passes, "Gate should fail — domain not detected even with generic wildcard");
        assert_eq!(failed, Some("output_format".to_string()));
    }

    #[test]
    fn test_domain_gate_multiple_gates_all_must_pass() {
        // A skill with two gates should only pass if BOTH pass
        let registry = create_test_registry();

        // Prompt mentions "python" AND "aws"
        let detected = detect_domains_from_prompt("deploy my python app to aws lambda", &registry);
        assert!(detected.contains_key("target_language"));
        assert!(detected.contains_key("cloud_provider"));

        let mut gates = HashMap::new();
        gates.insert("target_language".to_string(), vec!["python".to_string()]);
        gates.insert("cloud_provider".to_string(), vec!["aws".to_string()]);

        let (passes, _) = check_domain_gates(
            "aws-python-deploy",
            &gates,
            &detected,
            "deploy my python app to aws lambda",
            &registry,
        );
        assert!(passes, "Both gates should pass");
    }

    #[test]
    fn test_domain_gate_multiple_gates_one_fails() {
        // A skill with two gates where one fails should be filtered out
        let registry = create_test_registry();

        // Prompt mentions "python" but "gcp" (not "aws")
        let detected = detect_domains_from_prompt("deploy my python app to gcp cloud run", &registry);
        assert!(detected.contains_key("target_language"));
        assert!(detected.contains_key("cloud_provider"));

        let mut gates = HashMap::new();
        gates.insert("target_language".to_string(), vec!["python".to_string()]);
        gates.insert("cloud_provider".to_string(), vec!["aws".to_string()]); // requires AWS but prompt says GCP

        let (passes, failed) = check_domain_gates(
            "aws-python-deploy",
            &gates,
            &detected,
            "deploy my python app to gcp cloud run",
            &registry,
        );
        assert!(!passes, "cloud_provider gate should fail — requires aws but prompt has gcp");
        assert_eq!(failed, Some("cloud_provider".to_string()));
    }

    #[test]
    fn test_domain_gate_in_find_matches_integration() {
        // Integration test: verify that find_matches actually filters skills via domain gates
        let registry = create_test_registry();
        let detected = detect_domains_from_prompt("help me write python unit tests", &registry);

        // Create an index with two skills: one gated on python, one gated on rust
        let mut skills = HashMap::new();

        skills.insert(
            "python-test-writer".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/python-test-writer/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec!["test".to_string(), "unit test".to_string(), "pytest".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Python test writing".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: {
                    let mut g = HashMap::new();
                    g.insert("target_language".to_string(), vec!["python".to_string()]);
                    g
                },
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        skills.insert(
            "rust-test-writer".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/rust-test-writer/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec!["test".to_string(), "unit test".to_string(), "cargo test".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Rust test writing".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: {
                    let mut g = HashMap::new();
                    g.insert("target_language".to_string(), vec!["rust".to_string()]);
                    g
                },
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 2,
            skills,
        };

        // Prompt: "help me write python unit tests" → should match python-test-writer only
        let matches = find_matches(
            "help me write python unit tests",
            "help me write python unit tests",
            &index,
            "",
            &ProjectContext::default(),
            false,
            &detected,
            Some(&registry),
        );

        // python-test-writer should be found
        let python_match = matches.iter().find(|m| m.name == "python-test-writer");
        assert!(python_match.is_some(), "python-test-writer should match (gate passes)");

        // rust-test-writer should be filtered out by domain gate
        let rust_match = matches.iter().find(|m| m.name == "rust-test-writer");
        assert!(rust_match.is_none(), "rust-test-writer should be filtered out (gate fails: needs rust, prompt has python)");
    }

    #[test]
    fn test_domain_detection_with_project_context() {
        // Context signals from the project should trigger domain detection
        // even when the prompt doesn't mention the language
        let registry = create_test_registry();

        // Prompt doesn't mention any language
        let context_signals = vec!["objective-c".to_string(), "ios".to_string()];
        let detected = detect_domains_from_prompt_with_context(
            "help me fix this memory leak bug",
            &registry,
            &context_signals,
        );

        // target_language should be detected via context signal "objective-c"
        assert!(
            detected.contains_key("target_language"),
            "target_language should be detected from project context signal 'objective-c'"
        );
    }

    #[test]
    fn test_find_canonical_domain_alias_resolution() {
        let registry = create_test_registry();

        // Direct canonical name
        assert_eq!(find_canonical_domain("target_language", &registry), "target_language");

        // Alias resolution
        assert_eq!(find_canonical_domain("programming_language", &registry), "target_language");
        assert_eq!(find_canonical_domain("lang_target", &registry), "target_language");

        // Unknown gate name falls through
        assert_eq!(find_canonical_domain("unknown_gate", &registry), "unknown_gate");
    }

    // ========================================================================
    // Project Context Scanning Tests
    // ========================================================================

    #[test]
    fn test_scan_project_context_empty_dir() {
        // Empty cwd string should return empty result
        let result = scan_project_context("");
        assert!(result.languages.is_empty());
        assert!(result.frameworks.is_empty());
        assert!(result.tools.is_empty());
    }

    #[test]
    fn test_scan_project_context_nonexistent_dir() {
        let result = scan_project_context("/tmp/pss_nonexistent_dir_99999");
        assert!(result.languages.is_empty());
    }

    #[test]
    fn test_scan_project_context_rust_project() {
        // Create a temp dir with Cargo.toml to simulate a Rust project
        let tmp = std::env::temp_dir().join("pss_test_rust_project");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::write(tmp.join("Cargo.toml"), "[package]\nname = \"test\"");

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"rust".to_string()));
        assert!(result.tools.contains(&"cargo".to_string()));

        // Cleanup
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_python_project() {
        let tmp = std::env::temp_dir().join("pss_test_python_project");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::write(
            tmp.join("requirements.txt"),
            "django>=4.0\nflask>=3.0\ntorch>=2.0\n",
        );
        let _ = fs::write(tmp.join("uv.lock"), "");

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"python".to_string()));
        assert!(result.frameworks.contains(&"django".to_string()));
        assert!(result.frameworks.contains(&"flask".to_string()));
        assert!(result.tools.contains(&"pytorch".to_string()));
        assert!(result.tools.contains(&"uv".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_js_project() {
        let tmp = std::env::temp_dir().join("pss_test_js_project");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::write(
            tmp.join("package.json"),
            r#"{"dependencies":{"react":"^18","next":"^14"},"devDependencies":{"typescript":"^5","vite":"^5"}}"#,
        );
        let _ = fs::write(tmp.join("bun.lockb"), "");
        let _ = fs::write(tmp.join("tsconfig.json"), "{}");

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"javascript".to_string()));
        assert!(result.languages.contains(&"typescript".to_string()));
        assert!(result.frameworks.contains(&"react".to_string()));
        assert!(result.frameworks.contains(&"nextjs".to_string()));
        assert!(result.tools.contains(&"bun".to_string()));
        assert!(result.tools.contains(&"vite".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_swift_ios_project() {
        let tmp = std::env::temp_dir().join("pss_test_swift_project");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::create_dir_all(tmp.join("MyApp.xcodeproj"));
        let _ = fs::write(tmp.join("Podfile"), "");
        // Simulate Objective-C source file
        let _ = fs::write(tmp.join("bridge.m"), "");

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"swift".to_string()));
        assert!(result.languages.contains(&"objective-c".to_string()));
        assert!(result.platforms.contains(&"ios".to_string()));
        assert!(result.platforms.contains(&"macos".to_string()));
        assert!(result.tools.contains(&"xcode".to_string()));
        assert!(result.tools.contains(&"cocoapods".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_deduplication() {
        // If both Cargo.toml and .rs files exist, "rust" should appear only once
        let tmp = std::env::temp_dir().join("pss_test_dedup_project");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::write(tmp.join("Cargo.toml"), "");
        let _ = fs::write(tmp.join("Makefile"), "");

        let result = scan_project_context(tmp.to_str().unwrap());
        // "rust" should not be duplicated
        let rust_count = result.languages.iter().filter(|l| *l == "rust").count();
        assert_eq!(rust_count, 1, "rust should appear exactly once");

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_multi_language() {
        // Simulate a monorepo with multiple languages
        let tmp = std::env::temp_dir().join("pss_test_multi_lang");
        let _ = fs::create_dir_all(&tmp);
        let _ = fs::write(tmp.join("Cargo.toml"), "");
        let _ = fs::write(tmp.join("go.mod"), "");
        let _ = fs::write(
            tmp.join("package.json"),
            r#"{"dependencies":{"express":"^4"}}"#,
        );
        let _ = fs::write(tmp.join("Dockerfile"), "");

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"rust".to_string()));
        assert!(result.languages.contains(&"go".to_string()));
        assert!(result.languages.contains(&"javascript".to_string()));
        assert!(result.tools.contains(&"docker".to_string()));
        assert!(result.frameworks.contains(&"express".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_root_file_types() {
        let entries = vec![
            "README.md".to_string(),
            "logo.svg".to_string(),
            "data.csv".to_string(),
            "main.rs".to_string(),  // Source file - should NOT be added
            "config.json".to_string(),
            "another.json".to_string(),  // Duplicate extension - deduped
        ];
        let mut result = ProjectScanResult::default();
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"md".to_string()));
        assert!(result.file_types.contains(&"svg".to_string()));
        assert!(result.file_types.contains(&"csv".to_string()));
        assert!(result.file_types.contains(&"json".to_string()));
        // "json" should appear only once even though 2 .json files exist
        let json_count = result.file_types.iter().filter(|ft| *ft == "json").count();
        assert_eq!(json_count, 1);
    }

    #[test]
    fn test_scan_python_deps_detection() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[project]
dependencies = [
    "fastapi>=0.100",
    "torch>=2.0",
    "langchain>=0.1",
]
"#;
        scan_python_deps(content, &mut result);
        assert!(result.frameworks.contains(&"fastapi".to_string()));
        assert!(result.tools.contains(&"pytorch".to_string()));
        assert!(result.tools.contains(&"langchain".to_string()));
    }

    #[test]
    fn test_scan_package_json_detection() {
        let mut result = ProjectScanResult::default();
        let content = r#"{"dependencies":{"vue":"^3","prisma":"^5"},"devDependencies":{"vitest":"^1"}}"#;
        let root_entries = vec!["package.json".to_string(), "yarn.lock".to_string()];
        scan_package_json(content, &root_entries, &mut result);

        assert!(result.languages.contains(&"javascript".to_string()));
        assert!(result.frameworks.contains(&"vue".to_string()));
        assert!(result.tools.contains(&"yarn".to_string()));
        assert!(result.tools.contains(&"prisma".to_string()));
        assert!(result.tools.contains(&"vitest".to_string()));
    }

    #[test]
    fn test_dedup_vec() {
        let mut v = vec![
            "rust".to_string(),
            "python".to_string(),
            "rust".to_string(),
            "go".to_string(),
            "python".to_string(),
        ];
        dedup_vec(&mut v);
        assert_eq!(v, vec!["rust", "python", "go"]);
    }

    #[test]
    fn test_project_context_merge_scan() {
        let mut ctx = ProjectContext {
            languages: vec!["swift".to_string()],
            frameworks: vec![],
            platforms: vec!["ios".to_string()],
            domains: vec![],
            tools: vec![],
            file_types: vec![],
        };
        let scan = ProjectScanResult {
            languages: vec!["swift".to_string(), "objective-c".to_string()],
            frameworks: vec!["swiftui".to_string()],
            platforms: vec!["ios".to_string(), "macos".to_string()],
            tools: vec!["xcode".to_string()],
            file_types: vec!["svg".to_string()],
        };
        ctx.merge_scan(&scan);

        // "swift" should not be duplicated (case-insensitive)
        let swift_count = ctx.languages.iter().filter(|l| l.eq_ignore_ascii_case("swift")).count();
        assert_eq!(swift_count, 1);
        // "objective-c" should be added
        assert!(ctx.languages.contains(&"objective-c".to_string()));
        // "macos" should be added
        assert!(ctx.platforms.contains(&"macos".to_string()));
        // "ios" should not be duplicated
        let ios_count = ctx.platforms.iter().filter(|p| p.eq_ignore_ascii_case("ios")).count();
        assert_eq!(ios_count, 1);
        // New items should be present
        assert!(ctx.frameworks.contains(&"swiftui".to_string()));
        assert!(ctx.tools.contains(&"xcode".to_string()));
        assert!(ctx.file_types.contains(&"svg".to_string()));
    }

    // ====================================================================
    // New tests for expanded scanning (embedded, industrial, IoT, etc.)
    // ====================================================================

    #[test]
    fn test_scan_platformio_ini_basic() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
"#;
        scan_platformio_ini(content, &mut result);
        assert!(result.frameworks.contains(&"arduino".to_string()));
        assert!(result.platforms.contains(&"esp32".to_string()));
    }

    #[test]
    fn test_scan_platformio_ini_espidf() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[env:esp32s3]
platform = espressif32
board = esp32-s3-devkitc-1
framework = espidf
lib_deps = freertos
"#;
        scan_platformio_ini(content, &mut result);
        assert!(result.frameworks.contains(&"esp-idf".to_string()));
        assert!(result.frameworks.contains(&"freertos".to_string()));
        assert!(result.platforms.contains(&"esp32".to_string()));
    }

    #[test]
    fn test_scan_platformio_ini_stm32() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[env:nucleo_f446re]
platform = ststm32
board = nucleo_f446re
framework = stm32cube
"#;
        scan_platformio_ini(content, &mut result);
        assert!(result.frameworks.contains(&"stm32cube".to_string()));
        assert!(result.platforms.contains(&"stm32".to_string()));
    }

    #[test]
    fn test_scan_platformio_ini_nrf52() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[env:nrf52840_dk]
platform = nordicnrf52
board = nrf52840_dk
framework = zephyr
"#;
        scan_platformio_ini(content, &mut result);
        assert!(result.frameworks.contains(&"zephyr".to_string()));
        assert!(result.platforms.contains(&"nrf52".to_string()));
    }

    #[test]
    fn test_scan_gradle_project_android() {
        let tmp = std::env::temp_dir().join("pss_test_gradle_android");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        // Create a build.gradle with Android plugin
        fs::write(
            tmp.join("build.gradle"),
            r#"
plugins {
    id 'com.android.application'
}
android {
    compileSdk 34
}
"#,
        )
        .unwrap();

        let root_entries = vec!["build.gradle".to_string()];
        let mut result = ProjectScanResult::default();
        scan_gradle_project(&tmp, &root_entries, &mut result);

        assert!(result.platforms.contains(&"android".to_string()));
        assert!(result.frameworks.contains(&"android-sdk".to_string()));
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_gradle_project_spring_boot() {
        let tmp = std::env::temp_dir().join("pss_test_gradle_spring");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        fs::write(
            tmp.join("build.gradle.kts"),
            r#"
plugins {
    id("org.springframework.boot") version "3.2.0"
}
"#,
        )
        .unwrap();

        let root_entries = vec!["build.gradle.kts".to_string()];
        let mut result = ProjectScanResult::default();
        scan_gradle_project(&tmp, &root_entries, &mut result);

        assert!(result.frameworks.contains(&"spring-boot".to_string()));
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_python_deps_embedded() {
        let mut result = ProjectScanResult::default();
        let content = r#"
[project]
dependencies = [
    "micropython-stubs",
    "esptool",
    "pyserial",
]
"#;
        scan_python_deps(content, &mut result);
        assert!(result.frameworks.contains(&"micropython".to_string()));
        assert!(result.platforms.contains(&"esp32".to_string()));
        assert!(result.tools.contains(&"serial".to_string()));
    }

    #[test]
    fn test_scan_python_deps_robotics() {
        let mut result = ProjectScanResult::default();
        let content = r#"
rclpy>=1.0
geometry_msgs
sensor_msgs
nav2_msgs
"#;
        scan_python_deps(content, &mut result);
        assert!(result.frameworks.contains(&"ros2".to_string()));
        assert!(result.platforms.contains(&"robotics".to_string()));
    }

    #[test]
    fn test_scan_python_deps_industrial() {
        let mut result = ProjectScanResult::default();
        let content = r#"
pymodbus>=3.0
asyncua>=1.0
paho-mqtt>=1.6
"#;
        scan_python_deps(content, &mut result);
        assert!(result.tools.contains(&"modbus".to_string()));
        assert!(result.tools.contains(&"opcua".to_string()));
        assert!(result.tools.contains(&"mqtt".to_string()));
        assert!(result.platforms.contains(&"industrial".to_string()));
    }

    #[test]
    fn test_scan_python_deps_ml_expanded() {
        let mut result = ProjectScanResult::default();
        let content = r#"
numpy>=1.24
pandas>=2.0
polars>=0.20
matplotlib>=3.8
plotly>=5.18
mlflow>=2.10
wandb>=0.16
"#;
        scan_python_deps(content, &mut result);
        assert!(result.tools.contains(&"numpy".to_string()));
        assert!(result.tools.contains(&"pandas".to_string()));
        assert!(result.tools.contains(&"polars".to_string()));
        assert!(result.tools.contains(&"matplotlib".to_string()));
        assert!(result.tools.contains(&"plotly".to_string()));
        assert!(result.tools.contains(&"mlflow".to_string()));
        assert!(result.tools.contains(&"wandb".to_string()));
    }

    #[test]
    fn test_scan_python_deps_cv() {
        let mut result = ProjectScanResult::default();
        let content = r#"
opencv-python>=4.8
ultralytics>=8.0
mediapipe>=0.10
"#;
        scan_python_deps(content, &mut result);
        assert!(result.tools.contains(&"opencv".to_string()));
        assert!(result.tools.contains(&"yolo".to_string()));
        assert!(result.tools.contains(&"mediapipe".to_string()));
    }

    #[test]
    fn test_scan_package_json_mobile_hybrid() {
        let mut result = ProjectScanResult::default();
        let content = r#"{"dependencies":{"@capacitor/core":"^5","@ionic/core":"^7"}}"#;
        let root_entries = vec!["package.json".to_string()];
        scan_package_json(content, &root_entries, &mut result);

        assert!(result.frameworks.contains(&"capacitor".to_string()));
        assert!(result.frameworks.contains(&"ionic".to_string()));
        assert!(result.platforms.contains(&"mobile".to_string()));
    }

    #[test]
    fn test_scan_package_json_iot_hardware() {
        let mut result = ProjectScanResult::default();
        let content = r#"{"dependencies":{"johnny-five":"^2","mqtt":"^5","serialport":"^12"}}"#;
        let root_entries = vec!["package.json".to_string()];
        scan_package_json(content, &root_entries, &mut result);

        assert!(result.frameworks.contains(&"johnny-five".to_string()));
        assert!(result.frameworks.contains(&"mqtt".to_string()));
        assert!(result.frameworks.contains(&"serialport".to_string()));
        assert!(result.platforms.contains(&"embedded".to_string()));
    }

    #[test]
    fn test_scan_package_json_3d_graphics() {
        let mut result = ProjectScanResult::default();
        let content = r#"{"dependencies":{"three":"^0.160","@react-three/fiber":"^8"}}"#;
        let root_entries = vec!["package.json".to_string()];
        scan_package_json(content, &root_entries, &mut result);

        assert!(result.frameworks.contains(&"threejs".to_string()));
        assert!(result.frameworks.contains(&"react-three-fiber".to_string()));
    }

    #[test]
    fn test_scan_package_json_expanded_tools() {
        let mut result = ProjectScanResult::default();
        let content = r#"{"dependencies":{"zustand":"^4","zod":"^3"},"devDependencies":{"biome":"^1","storybook":"^8","puppeteer":"^22"}}"#;
        let root_entries = vec!["package.json".to_string(), "bun.lockb".to_string()];
        scan_package_json(content, &root_entries, &mut result);

        assert!(result.tools.contains(&"bun".to_string()));
        assert!(result.tools.contains(&"zustand".to_string()));
        assert!(result.tools.contains(&"zod".to_string()));
        assert!(result.tools.contains(&"biome".to_string()));
        assert!(result.tools.contains(&"storybook".to_string()));
        assert!(result.tools.contains(&"puppeteer".to_string()));
    }

    #[test]
    fn test_scan_root_file_types_embedded_hardware() {
        let mut result = ProjectScanResult::default();
        let entries = vec![
            "firmware.hex".to_string(),
            "boot.elf".to_string(),
            "flash.uf2".to_string(),
            "device.svd".to_string(),
            "board.dts".to_string(),
            "signal.grc".to_string(),
        ];
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"hex".to_string()));
        assert!(result.file_types.contains(&"elf".to_string()));
        assert!(result.file_types.contains(&"uf2".to_string()));
        assert!(result.file_types.contains(&"svd".to_string()));
        assert!(result.file_types.contains(&"dts".to_string()));
        assert!(result.file_types.contains(&"grc".to_string()));
    }

    #[test]
    fn test_scan_root_file_types_automotive_industrial() {
        let mut result = ProjectScanResult::default();
        let entries = vec![
            "system.arxml".to_string(),
            "can_bus.dbc".to_string(),
            "shader.glsl".to_string(),
            "shader.hlsl".to_string(),
            "model.gltf".to_string(),
            "print.gcode".to_string(),
        ];
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"arxml".to_string()));
        assert!(result.file_types.contains(&"dbc".to_string()));
        assert!(result.file_types.contains(&"glsl".to_string()));
        assert!(result.file_types.contains(&"hlsl".to_string()));
        assert!(result.file_types.contains(&"gltf".to_string()));
        assert!(result.file_types.contains(&"gcode".to_string()));
    }

    #[test]
    fn test_scan_root_file_types_lab_instrumentation() {
        let mut result = ProjectScanResult::default();
        let entries = vec![
            "experiment.vi".to_string(),
            "project.lvproj".to_string(),
            "sim.slx".to_string(),
            "data.mat".to_string(),
            "notebook.ipynb".to_string(),
        ];
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"vi".to_string()));
        assert!(result.file_types.contains(&"lvproj".to_string()));
        assert!(result.file_types.contains(&"slx".to_string()));
        assert!(result.file_types.contains(&"mat".to_string()));
        assert!(result.file_types.contains(&"ipynb".to_string()));
    }

    #[test]
    fn test_scan_root_file_types_3d_cad() {
        let mut result = ProjectScanResult::default();
        let entries = vec![
            "model.stl".to_string(),
            "scene.gltf".to_string(),
            "part.step".to_string(),
            "anim.fbx".to_string(),
            "scene.usdz".to_string(),
        ];
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"stl".to_string()));
        assert!(result.file_types.contains(&"gltf".to_string()));
        assert!(result.file_types.contains(&"step".to_string()));
        assert!(result.file_types.contains(&"fbx".to_string()));
        assert!(result.file_types.contains(&"usdz".to_string()));
    }

    #[test]
    fn test_scan_root_file_types_security_certs() {
        let mut result = ProjectScanResult::default();
        let entries = vec![
            "server.pem".to_string(),
            "ca.crt".to_string(),
            "private.key".to_string(),
            "re_project.gpr".to_string(),
            "binary.idb".to_string(),
        ];
        scan_root_file_types(&entries, &mut result);

        assert!(result.file_types.contains(&"pem".to_string()));
        assert!(result.file_types.contains(&"crt".to_string()));
        assert!(result.file_types.contains(&"key".to_string()));
        assert!(result.file_types.contains(&"gpr".to_string()));
        assert!(result.file_types.contains(&"idb".to_string()));
    }

    #[test]
    fn test_scan_project_context_embedded_project() {
        // Simulate a directory with PlatformIO + Arduino files
        let tmp = std::env::temp_dir().join("pss_test_embedded");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        fs::write(
            tmp.join("platformio.ini"),
            "[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n",
        )
        .unwrap();
        fs::write(tmp.join("main.ino"), "void setup() {} void loop() {}").unwrap();

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.tools.contains(&"platformio".to_string()));
        assert!(result.platforms.contains(&"embedded".to_string()));
        assert!(result.frameworks.contains(&"arduino".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_cuda_project() {
        let tmp = std::env::temp_dir().join("pss_test_cuda");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        fs::write(tmp.join("kernel.cu"), "__global__ void add() {}").unwrap();
        fs::write(tmp.join("CMakeLists.txt"), "project(cuda_test)").unwrap();

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.languages.contains(&"cuda".to_string()));
        assert!(result.platforms.contains(&"gpu".to_string()));
        assert!(result.tools.contains(&"cmake".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_scan_project_context_ros2_project() {
        let tmp = std::env::temp_dir().join("pss_test_ros2");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        // ROS 2 uses package.xml with ament build type
        fs::write(
            tmp.join("package.xml"),
            r#"<?xml version="1.0"?>
<package format="3">
  <buildtool_depend>ament_cmake</buildtool_depend>
</package>"#,
        )
        .unwrap();
        fs::write(tmp.join("CMakeLists.txt"), "project(my_ros2_pkg)").unwrap();

        let result = scan_project_context(tmp.to_str().unwrap());
        assert!(result.frameworks.contains(&"ros2".to_string()));
        assert!(result.platforms.contains(&"robotics".to_string()));

        let _ = fs::remove_dir_all(&tmp);
    }

    // ====================================================================
    // Tests for normalize_separators() and stem_word()
    // ====================================================================

    #[test]
    fn test_normalize_separators() {
        // Hyphens, underscores, spaces all collapse
        assert_eq!(normalize_separators("geo-json"), "geojson");
        assert_eq!(normalize_separators("geo_json"), "geojson");
        assert_eq!(normalize_separators("geo json"), "geojson");
        assert_eq!(normalize_separators("geojson"), "geojson");

        // camelCase flattened
        assert_eq!(normalize_separators("geoJson"), "geojson");
        assert_eq!(normalize_separators("GeoJSON"), "geojson");
        assert_eq!(normalize_separators("nextJs"), "nextjs");

        // Mixed separators
        assert_eq!(normalize_separators("react-native"), "reactnative");
        assert_eq!(normalize_separators("react_native"), "reactnative");
        assert_eq!(normalize_separators("reactNative"), "reactnative");

        // Already normalized
        assert_eq!(normalize_separators("docker"), "docker");
        assert_eq!(normalize_separators("kubernetes"), "kubernetes");
    }

    #[test]
    fn test_stem_word_plurals() {
        assert_eq!(stem_word("tests"), "test");
        assert_eq!(stem_word("deploys"), "deploy");
        assert_eq!(stem_word("configs"), "config");
        assert_eq!(stem_word("libraries"), "library");
        assert_eq!(stem_word("dependencies"), "dependency");
        assert_eq!(stem_word("patches"), "patch");
        assert_eq!(stem_word("fixes"), "fix");
    }

    #[test]
    fn test_stem_word_verb_forms() {
        // -ing forms
        assert_eq!(stem_word("testing"), "test");
        assert_eq!(stem_word("building"), "build");
        assert_eq!(stem_word("deploying"), "deploy");
        assert_eq!(stem_word("configuring"), "configur"); // acceptable stem for matching
        assert_eq!(stem_word("generating"), "generat"); // -ting→-te→"generate"→strip trailing e→"generat"
        assert_eq!(stem_word("running"), "run");      // doubled consonant: nn→n
        assert_eq!(stem_word("mapping"), "map");       // doubled consonant: pp→p
        assert_eq!(stem_word("debugging"), "debug");   // doubled consonant: gg→g
        assert_eq!(stem_word("setting"), "set");       // doubled consonant: tt→t
        assert_eq!(stem_word("bundling"), "bundl");    // -ling→"bundle"→strip trailing e→"bundl"
        assert_eq!(stem_word("copying"), "copy");

        // -ed forms
        assert_eq!(stem_word("tested"), "test");
        assert_eq!(stem_word("deployed"), "deploy");
        assert_eq!(stem_word("configured"), "configur"); // -ed→"configur", matches stem_word("configure")→"configur"
        assert_eq!(stem_word("mapped"), "map");        // doubled consonant: pp→p
        assert_eq!(stem_word("optimized"), "optimiz"); // -ized→"optimize"→strip trailing e→"optimiz"
    }

    #[test]
    fn test_stem_word_other_suffixes() {
        // -ment
        assert_eq!(stem_word("deployment"), "deploy");
        assert_eq!(stem_word("management"), "manag"); // -ment→"manage"→strip trailing e→"manag"

        // -ation (strips "ation" to produce consistent stems)
        assert_eq!(stem_word("validation"), "valid");
        assert_eq!(stem_word("generation"), "gener");
        assert_eq!(stem_word("configuration"), "configur");

        // -ly (strips 2 chars)
        assert_eq!(stem_word("automatically"), "automatical");

        // -er
        assert_eq!(stem_word("compiler"), "compil");
        assert_eq!(stem_word("bundler"), "bundl");
    }

    #[test]
    fn test_stem_word_short_words_unchanged() {
        // Words too short to stem should pass through unchanged
        assert_eq!(stem_word("git"), "git");
        assert_eq!(stem_word("npm"), "npm");
        assert_eq!(stem_word("go"), "go");
        assert_eq!(stem_word("db"), "db");
    }

    #[test]
    fn test_stem_word_already_stemmed() {
        // Words that don't end in known suffixes pass through
        assert_eq!(stem_word("docker"), "dock"); // -er strip is ok
        assert_eq!(stem_word("react"), "react");
        assert_eq!(stem_word("python"), "python");
        assert_eq!(stem_word("rust"), "rust");
    }

    #[test]
    fn test_normalized_stemmed_matching_in_phase_2_5() {
        // Verify that Phase 2.5 allows matching across separator variants
        // and morphological forms by testing find_matches with crafted skills.
        let mut skills = HashMap::new();
        skills.insert(
            "geojson-expert".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/geojson-expert/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec!["geojson".to_string(), "mapping".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "GeoJSON expert".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-01T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 1,
            skills,
        };

        let ctx = ProjectContext::default();
        let detected: DetectedDomains = HashMap::new();

        // "geo-json" should match "geojson" via separator normalization
        let results = find_matches("geo-json", "geo-json", &index, "/tmp", &ctx, false, &detected, None);
        assert!(!results.is_empty(), "geo-json should match geojson via normalization");

        // "geo_json" should match "geojson" via separator normalization
        let results = find_matches("geo_json", "geo_json", &index, "/tmp", &ctx, false, &detected, None);
        assert!(!results.is_empty(), "geo_json should match geojson via normalization");

        // "maps" should match "mapping" via stemming (both stem to "map")
        let results = find_matches("maps", "maps", &index, "/tmp", &ctx, false, &detected, None);
        assert!(!results.is_empty(), "maps should match mapping via stemming");
    }

    #[test]
    fn test_trailing_e_consistency() {
        // Trailing-e stripping ensures consistent stems across all forms.
        // "configure", "configured", "configuring", "configuration" all stem consistently.
        assert_eq!(stem_word("configure"), "configur");
        assert_eq!(stem_word("configured"), "configur");
        assert_eq!(stem_word("configuring"), "configur");
        assert_eq!(stem_word("configuration"), "configur");

        // "generate", "generated", "generating", "generation" all stem consistently.
        assert_eq!(stem_word("generate"), "generat");
        assert_eq!(stem_word("generated"), "generat"); // -ed→"generat"→no trailing e
        assert_eq!(stem_word("generating"), "generat"); // -ting→"generate"→strip e→"generat"
        assert_eq!(stem_word("generation"), "gener"); // -ation→"gener"

        // "manage", "managed", "managing", "management" all stem consistently.
        assert_eq!(stem_word("manage"), "manag");
        assert_eq!(stem_word("managed"), "manag"); // -ed→"manag"
        assert_eq!(stem_word("managing"), "manag"); // -ing→"manag"
        assert_eq!(stem_word("management"), "manag"); // -ment→"manage"→strip e→"manag"

        // "cache", "cached", "caching"
        assert_eq!(stem_word("cache"), "cach");
        assert_eq!(stem_word("cached"), "cach"); // -ed→"cach"
        assert_eq!(stem_word("caching"), "cach"); // -ing→"cach"

        // "optimize", "optimized", "optimizing", "optimization"
        assert_eq!(stem_word("optimize"), "optimiz");
        assert_eq!(stem_word("optimized"), "optimiz"); // -ized→"optimize"→strip e→"optimiz"
        assert_eq!(stem_word("optimizing"), "optimiz"); // -ing→"optimiz"
    }

    #[test]
    fn test_abbreviation_match() {
        // Direct abbreviation lookups
        assert!(is_abbreviation_match("config", "configuration"));
        assert!(is_abbreviation_match("configuration", "config")); // bidirectional
        assert!(is_abbreviation_match("repo", "repository"));
        assert!(is_abbreviation_match("env", "environment"));
        assert!(is_abbreviation_match("auth", "authentication"));
        assert!(is_abbreviation_match("db", "database"));
        assert!(is_abbreviation_match("cfg", "configuration"));
        assert!(is_abbreviation_match("docs", "documentation"));
        assert!(is_abbreviation_match("deps", "dependencies"));

        // Non-matches
        assert!(!is_abbreviation_match("config", "repository"));
        assert!(!is_abbreviation_match("foo", "bar"));
        assert!(!is_abbreviation_match("test", "testing")); // not an abbreviation pair
    }

    #[test]
    fn test_abbreviation_matching_in_phase_2_5() {
        // Verify that abbreviations work in find_matches via Phase 2.5.
        let mut skills = HashMap::new();
        skills.insert(
            "config-manager".to_string(),
            SkillEntry {
                source: "user".to_string(),
                path: "/path/to/config-manager/SKILL.md".to_string(),
                skill_type: "skill".to_string(),
                keywords: vec!["configuration".to_string(), "settings".to_string()],
                intents: vec![],
                patterns: vec![],
                directories: vec![],
                path_patterns: vec![],
                description: "Configuration manager".to_string(),
                negative_keywords: vec![],
                tier: String::new(),
                boost: 0,
                category: String::new(),
                platforms: vec![],
                frameworks: vec![],
                languages: vec![],
                domains: vec![],
                tools: vec![],
                file_types: vec![],
                domain_gates: HashMap::new(),
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
                server_type: String::new(),
                server_command: String::new(),
                server_args: vec![],
                language_ids: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-01T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 1,
            skills,
        };

        let ctx = ProjectContext::default();
        let detected: DetectedDomains = HashMap::new();

        // "config" should match "configuration" via abbreviation
        let results = find_matches("config", "config", &index, "/tmp", &ctx, false, &detected, None);
        assert!(!results.is_empty(), "config should match configuration via abbreviation");

        // "cfg" should also match "configuration" via abbreviation
        let results = find_matches("cfg", "cfg", &index, "/tmp", &ctx, false, &detected, None);
        assert!(!results.is_empty(), "cfg should match configuration via abbreviation");

        // "repo" should NOT match "configuration" (wrong abbreviation)
        let results = find_matches("repo", "repo", &index, "/tmp", &ctx, false, &detected, None);
        assert!(results.is_empty(), "repo should not match configuration");
    }

    // ========================================================================
    // Multi-Type Functionality Tests
    // ========================================================================

    #[test]
    fn test_hook_filter_blocks_non_skill_types() {
        // Verify that the hook-mode filter keeps only skill/agent/empty types,
        // blocking command, rule, mcp, and lsp entries.
        let mut skills = HashMap::new();

        // Create entries of each type, all sharing the keyword "automation"
        for (name, stype) in &[
            ("auto-skill", "skill"),
            ("auto-agent", "agent"),
            ("auto-command", "command"),
            ("auto-rule", "rule"),
            ("auto-mcp", "mcp"),
            ("auto-lsp", "lsp"),
        ] {
            skills.insert(
                name.to_string(),
                SkillEntry {
                    source: "user".to_string(),
                    path: format!("/path/to/{}/SKILL.md", name),
                    skill_type: stype.to_string(),
                    keywords: vec!["automation".to_string()],
                    intents: vec![],
                    patterns: vec![],
                    directories: vec![],
                    path_patterns: vec![],
                    description: format!("{} entry", stype),
                    negative_keywords: vec![],
                    tier: String::new(),
                    boost: 0,
                    category: String::new(),
                    platforms: vec![],
                    frameworks: vec![],
                    languages: vec![],
                    domains: vec![],
                    tools: vec![],
                    file_types: vec![],
                    domain_gates: HashMap::new(),
                    usually_with: vec![],
                    precedes: vec![],
                    follows: vec![],
                    alternatives: vec![],
                    server_type: String::new(),
                    server_command: String::new(),
                    server_args: vec![],
                    language_ids: vec![],
                },
            );
        }

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 6,
            skills,
        };

        // find_matches returns all types
        let matches = find_matches(
            "automation",
            "automation",
            &index,
            "",
            &ProjectContext::default(),
            false,
            &HashMap::new(),
            None,
        );

        // Apply the same hook-mode filter as production code (line 5582-5584):
        // keep only entries where item_type is "skill", "agent", or empty
        let filtered: Vec<_> = matches
            .iter()
            .filter(|m| {
                let t = m.skill_type.as_str();
                t == "skill" || t == "agent" || t.is_empty()
            })
            .collect();

        // skill and agent should survive the filter
        assert!(
            filtered.iter().any(|m| m.name == "auto-skill"),
            "skill type should pass hook filter"
        );
        assert!(
            filtered.iter().any(|m| m.name == "auto-agent"),
            "agent type should pass hook filter"
        );

        // command, rule, mcp, lsp should be blocked
        assert!(
            !filtered.iter().any(|m| m.name == "auto-command"),
            "command type should be blocked by hook filter"
        );
        assert!(
            !filtered.iter().any(|m| m.name == "auto-rule"),
            "rule type should be blocked by hook filter"
        );
        assert!(
            !filtered.iter().any(|m| m.name == "auto-mcp"),
            "mcp type should be blocked by hook filter"
        );
        assert!(
            !filtered.iter().any(|m| m.name == "auto-lsp"),
            "lsp type should be blocked by hook filter"
        );
    }

    #[test]
    fn test_skill_entry_mcp_fields_deserialize() {
        // MCP-specific fields should deserialize correctly from JSON
        let json = r#"{
            "source": "user",
            "path": "/test",
            "type": "mcp",
            "keywords": ["chrome", "devtools"],
            "server_type": "stdio",
            "server_command": "npx",
            "server_args": ["-y", "chrome-devtools-mcp"]
        }"#;

        let entry: SkillEntry = serde_json::from_str(json).unwrap();
        assert_eq!(entry.server_type, "stdio");
        assert_eq!(entry.server_command, "npx");
        assert_eq!(entry.server_args, vec!["-y", "chrome-devtools-mcp"]);
        assert_eq!(entry.skill_type, "mcp");
    }

    #[test]
    fn test_skill_entry_lsp_fields_deserialize() {
        // LSP-specific fields should deserialize correctly from JSON
        let json = r#"{
            "source": "built-in",
            "path": "/test",
            "type": "lsp",
            "keywords": ["python", "pyright"],
            "language_ids": ["python"]
        }"#;

        let entry: SkillEntry = serde_json::from_str(json).unwrap();
        assert_eq!(entry.language_ids, vec!["python"]);
        assert_eq!(entry.server_type, "", "server_type should default to empty for LSP");
        assert!(entry.server_args.is_empty(), "server_args should default to empty vec for LSP");
        assert_eq!(entry.skill_type, "lsp");
    }

    #[test]
    fn test_skill_entry_backward_compat_missing_new_fields() {
        // Simulating an old index entry without MCP/LSP fields; all new fields
        // should default to empty values for backward compatibility.
        let json = r#"{
            "source": "user",
            "path": "/test",
            "type": "skill",
            "keywords": ["docker"]
        }"#;

        let entry: SkillEntry = serde_json::from_str(json).unwrap();
        assert_eq!(entry.server_type, "", "server_type should default to empty");
        assert_eq!(entry.server_command, "", "server_command should default to empty");
        assert!(entry.server_args.is_empty(), "server_args should default to empty vec");
        assert!(entry.language_ids.is_empty(), "language_ids should default to empty vec");
        assert_eq!(entry.skill_type, "skill");
    }

    #[test]
    fn test_type_based_ordering_in_find_matches() {
        // Verify that find_matches orders results: skill first, agent second,
        // command third, matching the type_order tiebreaker logic.
        let mut skills = HashMap::new();

        // All three entries share the same keyword so they get similar scores
        for (name, stype) in &[
            ("order-skill", "skill"),
            ("order-agent", "agent"),
            ("order-command", "command"),
        ] {
            skills.insert(
                name.to_string(),
                SkillEntry {
                    source: "user".to_string(),
                    path: format!("/path/to/{}/SKILL.md", name),
                    skill_type: stype.to_string(),
                    keywords: vec!["sorting".to_string()],
                    intents: vec![],
                    patterns: vec![],
                    directories: vec![],
                    path_patterns: vec![],
                    description: format!("{} for sorting test", stype),
                    negative_keywords: vec![],
                    tier: String::new(),
                    boost: 0,
                    category: String::new(),
                    platforms: vec![],
                    frameworks: vec![],
                    languages: vec![],
                    domains: vec![],
                    tools: vec![],
                    file_types: vec![],
                    domain_gates: HashMap::new(),
                    usually_with: vec![],
                    precedes: vec![],
                    follows: vec![],
                    alternatives: vec![],
                    server_type: String::new(),
                    server_command: String::new(),
                    server_args: vec![],
                    language_ids: vec![],
                },
            );
        }

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 3,
            skills,
        };

        let matches = find_matches(
            "sorting",
            "sorting",
            &index,
            "",
            &ProjectContext::default(),
            false,
            &HashMap::new(),
            None,
        );

        // All three should match
        assert_eq!(matches.len(), 3, "All three entries should match 'sorting'");

        // Verify type ordering: skill < agent < command
        let skill_pos = matches.iter().position(|m| m.skill_type == "skill");
        let agent_pos = matches.iter().position(|m| m.skill_type == "agent");
        let command_pos = matches.iter().position(|m| m.skill_type == "command");

        assert!(skill_pos.is_some(), "skill entry should be in results");
        assert!(agent_pos.is_some(), "agent entry should be in results");
        assert!(command_pos.is_some(), "command entry should be in results");

        assert!(
            skill_pos.unwrap() < agent_pos.unwrap(),
            "skill (pos {}) should come before agent (pos {})",
            skill_pos.unwrap(),
            agent_pos.unwrap()
        );
        assert!(
            agent_pos.unwrap() < command_pos.unwrap(),
            "agent (pos {}) should come before command (pos {})",
            agent_pos.unwrap(),
            command_pos.unwrap()
        );
    }
}
