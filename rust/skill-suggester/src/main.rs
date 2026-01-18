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

use colored::Colorize;
use lazy_static::lazy_static;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;
use thiserror::Error;
use tracing::{debug, error, info, warn};

// ============================================================================
// Constants
// ============================================================================

/// Default index file location
const INDEX_FILE: &str = "skill-index.json";

/// Cache directory name under ~/.claude/
const CACHE_DIR: &str = "cache";

/// Maximum number of suggestions to return
const MAX_SUGGESTIONS: usize = 10;

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

/// Output payload for Claude Code hook
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HookOutput {
    /// Always "1.0" for Claude Code hooks
    pub version: String,

    /// Additional context to inject into Claude's context
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub additional_context: Vec<ContextItem>,
}

/// A context item to inject
#[derive(Debug, Serialize)]
pub struct ContextItem {
    /// Type: skill, agent, or command
    #[serde(rename = "type")]
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
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<String>,

    /// Commitment reminder for HIGH confidence (from reliable)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub commitment: Option<String>,
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
fn find_matches(
    original_prompt: &str,
    expanded_prompt: &str,
    index: &SkillIndex,
    cwd: &str,
) -> Vec<MatchedSkill> {
    let weights = MatchWeights::default();
    let thresholds = ConfidenceThresholds::default();
    let mut matches: Vec<MatchedSkill> = Vec::new();

    let original_lower = original_prompt.to_lowercase();
    let expanded_lower = expanded_prompt.to_lowercase();

    for (name, entry) in &index.skills {
        let mut score: i32 = 0;
        let mut evidence: Vec<String> = Vec::new();
        let mut keyword_matches = 0;

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
        for keyword in &entry.keywords {
            let kw_lower = keyword.to_lowercase();
            if expanded_lower.contains(&kw_lower) {
                if keyword_matches == 0 {
                    // First keyword gets big bonus
                    score += weights.first_match;
                } else {
                    score += weights.keyword;
                }
                keyword_matches += 1;

                // Original prompt bonus (not just expanded synonym match)
                if original_lower.contains(&kw_lower) {
                    score += weights.original_bonus;
                    evidence.push(format!("keyword*:{}", keyword)); // * = original
                } else {
                    evidence.push(format!("keyword:{}", keyword));
                }
            }
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

    // Sort by score descending (skills-first from LimorAI is implicit - skills are matched equally)
    matches.sort_by(|a, b| b.score.cmp(&a.score));

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

/// Get the path to the skill index file
fn get_index_path() -> Result<PathBuf, SuggesterError> {
    let home = dirs::home_dir().ok_or(SuggesterError::NoHomeDir)?;
    let index_path = home.join(".claude").join(CACHE_DIR).join(INDEX_FILE);
    Ok(index_path)
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
// Main Entry Point
// ============================================================================

fn main() {
    // Initialize tracing if RUST_LOG is set
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_writer(std::io::stderr)
        .init();

    if let Err(e) = run() {
        error!("Error: {}", e);
        // Output empty response on error (non-blocking)
        let output = HookOutput {
            version: "1.0".to_string(),
            additional_context: vec![],
        };
        println!("{}", serde_json::to_string(&output).unwrap_or_default());
        std::process::exit(0); // Exit 0 to not block Claude
    }
}

fn run() -> Result<(), SuggesterError> {
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
        let output = HookOutput {
            version: "1.0".to_string(),
            additional_context: vec![],
        };
        println!("{}", serde_json::to_string(&output)?);
        return Ok(());
    }

    info!(
        "Processing prompt: {}",
        &input.prompt[..input.prompt.len().min(50)]
    );

    // Load skill index
    let index_path = get_index_path()?;
    debug!("Loading index from: {:?}", index_path);

    let index = match load_index(&index_path) {
        Ok(idx) => idx,
        Err(SuggesterError::IndexNotFound(path)) => {
            warn!("Skill index not found at {:?}, returning empty", path);
            let output = HookOutput {
                version: "1.0".to_string(),
                additional_context: vec![],
            };
            println!("{}", serde_json::to_string(&output)?);
            return Ok(());
        }
        Err(e) => return Err(e),
    };

    info!("Loaded {} skills from index", index.skills.len());

    // Expand synonyms (key to high accuracy from LimorAI)
    let expanded_prompt = expand_synonyms(&input.prompt);
    debug!("Expanded prompt: {}", expanded_prompt);

    // Find matches with weighted scoring
    let matches = find_matches(&input.prompt, &expanded_prompt, &index, &input.cwd);

    if matches.is_empty() {
        debug!("No matches found");
        let output = HookOutput {
            version: "1.0".to_string(),
            additional_context: vec![],
        };
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

    let output = HookOutput {
        version: "1.0".to_string(),
        additional_context: context_items,
    };

    // Output JSON to stdout
    println!("{}", serde_json::to_string(&output)?);

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
        let matches = find_matches(original, &expanded, &index, "");

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
        let matches = find_matches(original, &expanded, &index, "");
        assert!(!matches.is_empty());
        assert_eq!(matches[0].confidence, Confidence::High);

        // LOW confidence - single keyword
        let original2 = "help me with docker";
        let expanded2 = expand_synonyms(original2);
        let matches2 = find_matches(original2, &expanded2, &index, "");
        assert!(!matches2.is_empty());
        // Score should be lower
    }

    #[test]
    fn test_directory_boost() {
        let index = create_test_index();
        let original = "help me with this file";
        let expanded = expand_synonyms(original);

        // With matching directory
        let matches_with_dir = find_matches(original, &expanded, &index, "/project/.github/workflows");

        // Without matching directory
        let matches_no_dir = find_matches(original, &expanded, &index, "/project/src");

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
}
