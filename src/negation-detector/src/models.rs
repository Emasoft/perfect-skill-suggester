use serde::{Deserialize, Serialize};

/// Input format for the pss-nlp binary
#[derive(Debug, Deserialize)]
pub struct NlpRequest {
    /// "prompt" for prompt-time negation, "index" for index-time keyword extraction
    pub mode: String,
    /// The text to analyze
    pub text: String,
    /// Optional: known entity names to check against (for prompt mode)
    #[serde(default)]
    pub entities: Vec<String>,
}

/// Output format for prompt-mode negation detection
#[derive(Debug, Serialize)]
pub struct PromptNegationResult {
    /// Terms that are negated in the prompt (lowercase)
    pub negated_terms: Vec<String>,
    /// Detailed pattern matches explaining each negation
    pub patterns: Vec<PatternMatchResult>,
}

/// Output format for index-mode keyword extraction
#[derive(Debug, Serialize)]
pub struct IndexExtractionResult {
    /// Keywords that are positively mentioned
    pub positive_keywords: Vec<String>,
    /// Keywords that are negated/excluded
    pub negative_keywords: Vec<String>,
    /// Detailed pattern matches
    pub patterns: Vec<PatternMatchResult>,
}

/// Detailed description of a detected negation pattern
#[derive(Debug, Clone, Serialize)]
pub struct PatternMatchResult {
    /// Pattern type identifier
    pub pattern_type: String,
    /// The negated term(s)
    pub negated: Vec<String>,
    /// The non-negated term(s) (for patterns like "but for" where some terms are scope)
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub non_negated: Vec<String>,
    /// Human-readable explanation of the negation
    pub reason: String,
}

/// Internal representation of a token with NLP annotations
#[derive(Debug, Clone)]
pub struct AnnotatedToken {
    /// The raw word text
    pub text: String,
    /// Lowercase text
    pub text_lower: String,
    /// Position index in the sentence
    pub index: usize,
    /// Primary POS tag (e.g., "NN", "VB", "RB", "NNP", "JJ")
    pub pos: String,
    /// Lemma (base form of the word)
    pub lemma: String,
    /// All POS tags (nlprule may assign multiple)
    pub all_pos: Vec<String>,
    /// Chunk tags (e.g., "B-NP-singular", "I-VP")
    pub chunks: Vec<String>,
    /// Whether this token is a negation marker (POS=RB with lemma "not", or avoidance verbs)
    pub is_negation: bool,
    /// Whether this token is a noun/entity (POS starts with NN or NNP)
    pub is_noun: bool,
    /// Whether this token starts a new noun phrase (chunk starts with B-NP)
    pub starts_np: bool,
}

/// A sentence with its annotated tokens
#[derive(Debug)]
pub struct AnnotatedSentence {
    /// The raw sentence text
    pub text: String,
    /// Annotated tokens (excludes SENT_START/SENT_END markers)
    pub tokens: Vec<AnnotatedToken>,
}

/// Types of negation patterns detected
#[derive(Debug, Clone, PartialEq)]
pub enum NegationPatternType {
    /// "not", "never", "n't" — direct negation marker
    ExplicitNegation,
    /// "avoid", "skip", "exclude" + optional "like X and Y"
    AvoidanceLike,
    /// "X and Y but for Z" — X,Y negated; Z is actual scope
    ButForPattern,
    /// "outside the scope of X" / "beyond the scope of X"
    OutsideScope,
    /// "not relevant for those who study/work in X"
    NotRelevantFor,
    /// "only X" — everything else is implicitly excluded
    OnlyQuantifier,
    /// "not compatible with X", "doesn't work with X"
    IncompatibilityMarker,
    /// "instead of X" — X is the replaced/rejected option
    InsteadOf,
    /// "except X", "excluding X" — explicit exclusion
    ExclusionMarker,
}

impl NegationPatternType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::ExplicitNegation => "explicit_negation",
            Self::AvoidanceLike => "avoidance_like",
            Self::ButForPattern => "but_for",
            Self::OutsideScope => "outside_scope",
            Self::NotRelevantFor => "not_relevant_for",
            Self::OnlyQuantifier => "only_quantifier",
            Self::IncompatibilityMarker => "incompatibility",
            Self::InsteadOf => "instead_of",
            Self::ExclusionMarker => "exclusion",
        }
    }
}

/// A detected negation with scope information
#[derive(Debug, Clone)]
pub struct NegationScope {
    /// The type of negation pattern
    pub pattern_type: NegationPatternType,
    /// Token index where the negation marker appears
    pub marker_index: usize,
    /// Token index where the negation scope starts (inclusive)
    pub scope_start: usize,
    /// Token index where the negation scope ends (inclusive)
    pub scope_end: usize,
    /// The negation marker word(s)
    pub marker_text: String,
    /// Terms that are negated by this scope
    pub negated_terms: Vec<String>,
    /// Terms that are explicitly NOT negated (e.g., the scope in "but for Z")
    pub non_negated_terms: Vec<String>,
}
