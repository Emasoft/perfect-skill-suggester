use crate::models::{AnnotatedToken, AnnotatedSentence};
use anyhow::Result;
use nlprule::Tokenizer;

/// Wraps nlprule's Tokenizer to produce AnnotatedSentences with POS tags,
/// lemmas, chunks, and derived flags (is_negation, is_noun, starts_np).
pub struct NlpTokenizer {
    tokenizer: Tokenizer,
}

/// Avoidance verbs that signal negation of following content
pub const AVOIDANCE_VERBS: &[&str] = &[
    "avoid", "skip", "exclude", "omit", "ignore", "abandon",
    "reject", "dismiss", "discard", "bypass", "forbid", "prohibit",
    "prevent", "eliminate", "remove", "drop", "ditch",
];

/// Words that mark scope exclusion (preposition-like negation)
const SCOPE_EXCLUSION_WORDS: &[&str] = &[
    "outside", "beyond", "except", "excluding", "without",
];

/// Explicit negation adverbs and particles
const NEGATION_WORDS: &[&str] = &[
    "not", "never", "no", "neither", "nor", "none",
];

impl NlpTokenizer {
    /// Create a new NlpTokenizer from the embedded English model data
    pub fn new(tokenizer_bytes: &[u8]) -> Result<Self> {
        let tokenizer = Tokenizer::from_reader(&mut &*tokenizer_bytes)?;
        Ok(Self { tokenizer })
    }

    /// Tokenize and annotate text into sentences with POS, lemma, chunk info.
    /// Filters out SENT_START/SENT_END markers.
    /// Normalizes input text to ensure sentence-ending punctuation exists
    /// (nlprule requires proper sentence boundaries for accurate POS tagging).
    pub fn analyze(&self, text: &str) -> Vec<AnnotatedSentence> {
        // Normalize: ensure text ends with sentence-terminating punctuation.
        // nlprule depends on proper sentence boundaries for POS disambiguation.
        // Without a period, "React" in "I don't want to use React" gets wrong POS tags.
        let normalized = Self::normalize_text(text);
        let mut sentences = Vec::new();

        for sentence in self.tokenizer.pipe(&normalized) {
            let raw_text = sentence.text().to_string();
            let mut tokens = Vec::new();
            let mut token_index = 0;

            for token in sentence.tokens() {
                let word = token.word();
                let word_text = word.as_str().to_string();

                // Skip sentence boundary markers
                if word_text == "SENT_START" || word_text == "SENT_END" || word_text.is_empty() {
                    continue;
                }

                let text_lower = word_text.to_lowercase();

                // Extract all POS tags and lemmas
                let all_pos: Vec<String> = word.tags().iter()
                    .filter(|t| !t.pos().as_str().is_empty())
                    .map(|t| t.pos().as_str().to_string())
                    .collect();

                // Primary POS tag: first non-empty POS, or UNKNOWN
                let primary_pos = all_pos.first()
                    .cloned()
                    .unwrap_or_else(|| "UNKNOWN".to_string());

                // Primary lemma: first non-empty lemma
                let primary_lemma = word.tags().iter()
                    .filter(|t| !t.lemma().as_str().is_empty())
                    .map(|t| t.lemma().as_str().to_string())
                    .next()
                    .unwrap_or_else(|| text_lower.clone());

                // Extract chunk tags
                let chunks: Vec<String> = token.chunks().iter()
                    .map(|c| c.to_string())
                    .collect();

                // Determine if this token is a negation marker
                let is_negation = Self::is_negation_token(
                    &text_lower, &primary_lemma, &primary_pos, &all_pos
                );

                // Determine if this token is a noun/entity.
                // Uses BOTH POS tags AND chunk tags to disambiguate:
                // - POS: starts with NN (noun) or NNP (proper noun) or UNKNOWN
                // - Chunk: must be in NP chunk (noun phrase), NOT VP (verb phrase)
                // This prevents "use" (NN:UN+VB, chunk I-VP) from being misidentified
                // while correctly identifying "React" (NNP, chunk B-NP) as a noun.
                let has_noun_pos = all_pos.iter().any(|p| {
                    p.starts_with("NN") || p == "UNKNOWN"
                });
                let in_np_chunk = chunks.iter().any(|c| c.contains("NP"));
                let in_vp_chunk = chunks.iter().any(|c| c.contains("VP"));
                let is_noun = has_noun_pos && (in_np_chunk || (!in_vp_chunk && !chunks.iter().any(|c| c.contains("ADJP") || c.contains("ADVP"))));

                // Determine if this token starts a new noun phrase
                let starts_np = chunks.iter().any(|c| c.starts_with("B-NP"));

                tokens.push(AnnotatedToken {
                    text: word_text,
                    text_lower,
                    index: token_index,
                    pos: primary_pos,
                    lemma: primary_lemma,
                    all_pos,
                    chunks,
                    is_negation,
                    is_noun,
                    starts_np,
                });

                token_index += 1;
            }

            if !tokens.is_empty() {
                sentences.push(AnnotatedSentence {
                    text: raw_text,
                    tokens,
                });
            }
        }

        sentences
    }

    /// Normalize text to ensure proper sentence boundaries for nlprule.
    /// Also fixes common missing-apostrophe contractions (e.g., "dont" → "don't").
    /// nlprule splits "don't" into tokens [don, ', t] where t gets POS RB + lemma "not",
    /// so proper contractions are critical for negation detection.
    fn normalize_text(text: &str) -> String {
        let trimmed = text.trim();
        if trimmed.is_empty() {
            return String::new();
        }

        // Phase 1: Fix missing-apostrophe contractions (common in user prompts).
        // Word-boundary-safe replacement using regex-like manual matching.
        let mut result = trimmed.to_string();
        // Contraction pairs: (broken, fixed)
        const CONTRACTIONS: &[(&str, &str)] = &[
            ("dont", "don't"), ("doesnt", "doesn't"), ("didnt", "didn't"),
            ("cant", "can't"), ("couldnt", "couldn't"), ("shouldnt", "shouldn't"),
            ("wouldnt", "wouldn't"), ("wont", "won't"), ("isnt", "isn't"),
            ("arent", "aren't"), ("wasnt", "wasn't"), ("werent", "weren't"),
            ("hasnt", "hasn't"), ("havent", "haven't"), ("hadnt", "hadn't"),
        ];
        for &(broken, fixed) in CONTRACTIONS {
            // Case-insensitive word-boundary replacement
            let lower = result.to_lowercase();
            if let Some(pos) = lower.find(broken) {
                // Check word boundaries: char before must be non-alphanumeric or start
                let before_ok = pos == 0
                    || !lower.as_bytes()[pos - 1].is_ascii_alphanumeric();
                let after_pos = pos + broken.len();
                let after_ok = after_pos >= lower.len()
                    || !lower.as_bytes()[after_pos].is_ascii_alphanumeric();
                if before_ok && after_ok {
                    // Preserve original casing of first char
                    let replacement = if result.as_bytes()[pos].is_ascii_uppercase() {
                        let mut c = fixed.to_string();
                        // Capitalize first letter
                        if let Some(first) = c.get_mut(0..1) {
                            first.make_ascii_uppercase();
                        }
                        c
                    } else {
                        fixed.to_string()
                    };
                    result = format!("{}{}{}", &result[..pos], replacement, &result[after_pos..]);
                }
            }
        }

        // Phase 2: Ensure text ends with sentence-terminating punctuation.
        // nlprule depends on proper sentence boundaries for POS disambiguation.
        if !result.ends_with('.') && !result.ends_with('!') && !result.ends_with('?') {
            result.push('.');
        }
        result
    }

    /// Check if a token is a negation marker based on its POS tag, lemma, and text.
    /// Uses NLP analysis (POS tags) rather than simple string matching —
    /// this is why we need nlprule instead of just regex.
    fn is_negation_token(
        text_lower: &str,
        lemma: &str,
        _primary_pos: &str,
        all_pos: &[String],
    ) -> bool {
        // Case 1: POS tag indicates negation (RB with lemma "not")
        // nlprule splits "don't" into don + ' + t, where t gets POS RB with lemma "not"
        if lemma == "not" && all_pos.iter().any(|p| p == "RB") {
            return true;
        }

        // Case 2: Explicit negation words
        if NEGATION_WORDS.contains(&text_lower) {
            return true;
        }

        // Case 3: Avoidance verbs (only when used as verbs, not nouns)
        // POS helps distinguish: "avoid" as VB vs "the avoid" as NN
        if AVOIDANCE_VERBS.contains(&text_lower)
            && all_pos.iter().any(|p| p.starts_with("VB"))
        {
            return true;
        }

        // Case 4: Scope exclusion words (prepositions/adverbs indicating boundary)
        if SCOPE_EXCLUSION_WORDS.contains(&text_lower) {
            return true;
        }

        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_tokenizer() -> NlpTokenizer {
        let bytes = include_bytes!(concat!(
            env!("OUT_DIR"),
            "/",
            nlprule::tokenizer_filename!("en")
        ));
        NlpTokenizer::new(bytes).expect("Failed to load tokenizer")
    }

    #[test]
    fn test_dont_negation_detected() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("I don't want to use React.");
        assert_eq!(sentences.len(), 1);
        // "t" (from don't) should be marked as negation
        let has_negation = sentences[0].tokens.iter().any(|t| t.is_negation);
        assert!(has_negation, "Expected negation marker in 'I don't want to use React'");
    }

    #[test]
    fn test_avoid_negation_detected() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("Avoid frameworks like Vue.");
        let has_negation = sentences[0].tokens.iter().any(|t| t.is_negation && t.text_lower == "avoid");
        assert!(has_negation, "Expected 'Avoid' to be detected as negation");
    }

    #[test]
    fn test_react_is_noun() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("I want to use React.");
        let react = sentences[0].tokens.iter().find(|t| t.text_lower == "react");
        assert!(react.is_some(), "Expected 'React' token");
        assert!(react.unwrap().is_noun, "Expected 'React' to be identified as noun");
    }

    #[test]
    fn test_not_compatible_negation() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("This skill is not compatible with Python.");
        let not_token = sentences[0].tokens.iter().find(|t| t.text_lower == "not");
        assert!(not_token.is_some(), "Expected 'not' token");
        assert!(not_token.unwrap().is_negation, "Expected 'not' to be negation marker");
    }

    #[test]
    fn test_contraction_normalization_dont() {
        // "dont" (no apostrophe) is the most common user typo in prompts.
        // normalize_text should fix it to "don't" so nlprule can POS-tag correctly.
        let tok = make_tokenizer();
        let sentences = tok.analyze("I dont want to use React");
        assert_eq!(sentences.len(), 1);
        let has_negation = sentences[0].tokens.iter().any(|t| t.is_negation);
        assert!(has_negation, "Expected negation detected from 'dont' (without apostrophe)");
    }

    #[test]
    fn test_contraction_normalization_doesnt() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("It doesnt work with Angular");
        let has_negation = sentences[0].tokens.iter().any(|t| t.is_negation);
        assert!(has_negation, "Expected negation detected from 'doesnt' (without apostrophe)");
    }

    #[test]
    fn test_normalize_text_preserves_correct_text() {
        // Already-correct text with apostrophe should not be double-modified
        let normalized = NlpTokenizer::normalize_text("I don't want React");
        assert_eq!(normalized, "I don't want React.");
    }

    #[test]
    fn test_normalize_text_no_false_positive_on_substrings() {
        // "dont" inside a word like "dontown" should NOT be replaced
        let normalized = NlpTokenizer::normalize_text("the dontown area");
        assert!(!normalized.contains("don't"), "Should not replace 'dont' inside words");
    }
}
