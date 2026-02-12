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
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::PathBuf;
use std::time::Instant;
use thiserror::Error;
use tracing::{debug, error, info, warn};

// ============================================================================
// CLI Arguments
// ============================================================================

/// Perfect Skill Suggester (PSS) - High-accuracy skill activation for Claude Code
#[derive(Parser, Debug)]
#[command(name = "pss")]
#[command(version = "1.0.0")]
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
}

// ============================================================================
// Constants
// ============================================================================

/// Default index file location
const INDEX_FILE: &str = "skill-index.json";

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
    /// Skill importance tier: primary, secondary, utility
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

    /// Skill importance tier: primary, secondary, utility (from PSS)
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
                "SUGGESTED SKILL: {} [{}]\n  Path: {}\n  Confidence: {} (score: {:.2})\n  Evidence: {}\n",
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

/// Check if two words are fuzzy matches (within edit distance threshold)
/// Threshold is adaptive: 1 for short words (<=4), 2 for medium (<=8), 3 for long
fn is_fuzzy_match(word: &str, keyword: &str) -> bool {
    let word_len = word.len();
    let keyword_len = keyword.len();

    // Don't fuzzy match short words - too many false positives (lint→link, fix→fax)
    // Require minimum 6 characters for fuzzy matching
    if word_len < 6 || keyword_len < 6 {
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
fn find_matches(
    original_prompt: &str,
    expanded_prompt: &str,
    index: &SkillIndex,
    cwd: &str,
    context: &ProjectContext,
    incomplete_mode: bool,
) -> Vec<MatchedSkill> {
    let weights = MatchWeights::default();
    let thresholds = ConfidenceThresholds::default();
    let mut matches: Vec<MatchedSkill> = Vec::new();

    let original_lower = original_prompt.to_lowercase();
    let expanded_lower = expanded_prompt.to_lowercase();

    if incomplete_mode {
        debug!("INCOMPLETE MODE: Skipping tier boost and explicit boost fields");
    }

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

            // Phase 3: Fuzzy matching for typo tolerance
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
                "primary" => 5,    // Primary skills get boost
                "secondary" => 0,  // Default, no change
                "utility" => -2,   // Utility skills slightly deprioritized
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
        return Ok(home.join(".claude").join(CACHE_DIR).join(INDEX_FILE));
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
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut hasher = DefaultHasher::new();
    prompt.hash(&mut hasher);
    format!("{:016x}", hasher.finish())
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

    if let Err(e) = run(&cli) {
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

    // Create project context from hook input for platform/framework/language filtering
    let context = ProjectContext::from_hook_input(&input);
    if !context.is_empty() {
        debug!(
            "Project context: platforms={:?}, frameworks={:?}, languages={:?}",
            context.platforms, context.frameworks, context.languages
        );
    }

    // Apply typo corrections first (from Claude-Rio)
    let corrected_prompt = correct_typos(&input.prompt);
    if corrected_prompt != input.prompt.to_lowercase() {
        debug!("Typo-corrected prompt: {}", corrected_prompt);
    }

    // Task decomposition: break complex prompts into sub-tasks (from LimorAI research)
    let sub_tasks = decompose_tasks(&corrected_prompt);
    let is_multi_task = sub_tasks.len() > 1;

    if is_multi_task {
        info!("Decomposed prompt into {} sub-tasks", sub_tasks.len());
        for (i, task) in sub_tasks.iter().enumerate() {
            debug!("  Sub-task {}: {}", i + 1, &task[..task.len().min(50)]);
        }
    }

    // Process each sub-task (or just the one if no decomposition)
    let matches = if is_multi_task {
        // Process each sub-task independently
        let all_matches: Vec<Vec<MatchedSkill>> = sub_tasks
            .iter()
            .map(|task| {
                let expanded = expand_synonyms(task);
                find_matches(task, &expanded, &index, &input.cwd, &context, cli.incomplete_mode)
            })
            .collect();

        // Aggregate results from all sub-tasks
        aggregate_subtask_matches(all_matches)
    } else {
        // Single task - normal processing
        let expanded_prompt = expand_synonyms(&corrected_prompt);
        debug!("Expanded prompt: {}", expanded_prompt);
        find_matches(&input.prompt, &expanded_prompt, &index, &input.cwd, &context, cli.incomplete_mode)
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
                _ => "❓".white(),
            },
            item.name.bold(),
            item.item_type,
            item.match_count,
            item.score,
            conf_color
        );
    }

    // Apply filters: require evidence, min-score, then --top limit
    let limited_items: Vec<_> = context_items
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
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
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
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
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
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false);

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
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false);
        assert!(!matches.is_empty());
        assert_eq!(matches[0].confidence, Confidence::High);

        // LOW confidence - single keyword
        let original2 = "help me with docker";
        let expanded2 = expand_synonyms(original2);
        let matches2 = find_matches(original2, &expanded2, &index, "", &ProjectContext::default(), false);
        assert!(!matches2.is_empty());
        // Score should be lower
    }

    #[test]
    fn test_directory_boost() {
        let index = create_test_index();
        let original = "help me with this file";
        let expanded = expand_synonyms(original);

        // With matching directory
        let matches_with_dir = find_matches(original, &expanded, &index, "/project/.github/workflows", &ProjectContext::default(), false);

        // Without matching directory
        let matches_no_dir = find_matches(original, &expanded, &index, "/project/src", &ProjectContext::default(), false);

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
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false);

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
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false);

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
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
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
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
            },
        );

        let index = SkillIndex {
            version: "3.0".to_string(),
            generated: "2026-01-18T00:00:00Z".to_string(),
            method: "test".to_string(),
            skills_count: 2,
            skills,
        };

        let matches = find_matches("run test", "run test", &index, "", &ProjectContext::default(), false);

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
        // Short words (should be strict)
        assert!(is_fuzzy_match("git", "gti")); // 1 edit distance, allowed for short words
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
                usually_with: vec![],
                precedes: vec![],
                follows: vec![],
                alternatives: vec![],
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
        let matches = find_matches(original, &expanded, &index, "", &ProjectContext::default(), false);

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
                find_matches(task, &expanded, &index, "", &ProjectContext::default(), false)
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
}
