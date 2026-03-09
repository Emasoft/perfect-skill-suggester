pub mod models;
pub mod tokenizer;
pub mod pattern_detector;

use models::{
    NlpRequest, PromptNegationResult, IndexExtractionResult,
    PatternMatchResult, NegationScope,
};
use pattern_detector::PatternDetector;
use tokenizer::NlpTokenizer;
use std::collections::HashSet;

/// Main entry point for negation analysis.
/// Processes an NlpRequest and returns the appropriate result.
pub fn analyze(tokenizer: &NlpTokenizer, request: &NlpRequest) -> serde_json::Value {
    match request.mode.as_str() {
        "prompt" => {
            let result = analyze_prompt(tokenizer, &request.text, &request.entities);
            serde_json::to_value(result).unwrap_or_default()
        }
        "index" => {
            let result = analyze_index(tokenizer, &request.text);
            serde_json::to_value(result).unwrap_or_default()
        }
        _ => {
            serde_json::json!({"error": format!("Unknown mode: '{}'. Use 'prompt' or 'index'.", request.mode)})
        }
    }
}

/// Prompt-mode: detect which terms in the prompt are negated.
/// Returns a list of negated terms that PSS should penalize/exclude.
fn analyze_prompt(
    tokenizer: &NlpTokenizer,
    text: &str,
    _entities: &[String],
) -> PromptNegationResult {
    let sentences = tokenizer.analyze(text);
    let mut all_negated: HashSet<String> = HashSet::new();
    let mut patterns: Vec<PatternMatchResult> = Vec::new();

    for sentence in &sentences {
        let scopes = PatternDetector::detect_all(sentence);
        for scope in &scopes {
            // Collect negated terms
            for term in &scope.negated_terms {
                all_negated.insert(term.clone());
            }
            // Remove non-negated terms (for "but for" patterns where some terms are scope)
            for term in &scope.non_negated_terms {
                all_negated.remove(term);
            }
            // Build pattern result
            patterns.push(scope_to_result(scope));
        }
    }

    // Filter out common function words that might have been collected
    let filtered: Vec<String> = all_negated.into_iter()
        .filter(|t| !is_function_word(t))
        .collect();

    PromptNegationResult {
        negated_terms: filtered,
        patterns,
    }
}

/// Index-mode: split text into positive and negative keywords.
/// Used during Pass 1 indexing to extract positive_keywords and negative_keywords
/// from skill descriptions.
fn analyze_index(
    tokenizer: &NlpTokenizer,
    text: &str,
) -> IndexExtractionResult {
    let sentences = tokenizer.analyze(text);
    let mut positive_set: HashSet<String> = HashSet::new();
    let mut negative_set: HashSet<String> = HashSet::new();
    let mut patterns: Vec<PatternMatchResult> = Vec::new();

    for sentence in &sentences {
        let scopes = PatternDetector::detect_all(sentence);

        // Collect all negated terms
        let mut sentence_negated: HashSet<String> = HashSet::new();
        let mut sentence_non_negated: HashSet<String> = HashSet::new();

        for scope in &scopes {
            for term in &scope.negated_terms {
                sentence_negated.insert(term.clone());
            }
            for term in &scope.non_negated_terms {
                sentence_non_negated.insert(term.clone());
            }
            patterns.push(scope_to_result(scope));
        }

        // All nouns in the sentence that are NOT negated go to positive
        for token in &sentence.tokens {
            if token.is_noun && !is_function_word(&token.text_lower) {
                if sentence_negated.contains(&token.text_lower) {
                    negative_set.insert(token.text_lower.clone());
                } else if sentence_non_negated.contains(&token.text_lower)
                    || !scopes.iter().any(|s| token_in_negation_scope(token, s))
                {
                    positive_set.insert(token.text_lower.clone());
                } else {
                    // Token is within a negation scope but not explicitly listed
                    negative_set.insert(token.text_lower.clone());
                }
            }
        }
    }

    // Remove overlap: if a term is in both sets, it goes to positive
    // (benefit of the doubt — it may appear positively in one sentence and negatively in another)
    for term in positive_set.iter() {
        negative_set.remove(term);
    }

    IndexExtractionResult {
        positive_keywords: positive_set.into_iter().collect(),
        negative_keywords: negative_set.into_iter().collect(),
        patterns,
    }
}

/// Check if a token falls within a negation scope
fn token_in_negation_scope(token: &models::AnnotatedToken, scope: &NegationScope) -> bool {
    token.index >= scope.scope_start && token.index <= scope.scope_end
}

/// Convert a NegationScope to a PatternMatchResult for JSON output
fn scope_to_result(scope: &NegationScope) -> PatternMatchResult {
    PatternMatchResult {
        pattern_type: scope.pattern_type.as_str().to_string(),
        negated: scope.negated_terms.clone(),
        non_negated: scope.non_negated_terms.clone(),
        reason: format!(
            "'{}' negates: [{}]{}",
            scope.marker_text,
            scope.negated_terms.join(", "),
            if scope.non_negated_terms.is_empty() {
                String::new()
            } else {
                format!("; scope: [{}]", scope.non_negated_terms.join(", "))
            }
        ),
    }
}

/// Filter out function words that shouldn't be treated as entities
fn is_function_word(word: &str) -> bool {
    matches!(
        word,
        "the" | "a" | "an" | "this" | "that" | "these" | "those"
            | "is" | "are" | "was" | "were" | "be" | "been" | "being"
            | "have" | "has" | "had" | "having"
            | "do" | "does" | "did" | "doing" | "done"
            | "will" | "would" | "could" | "should" | "may" | "might" | "shall" | "can"
            | "to" | "of" | "in" | "on" | "at" | "by" | "for" | "with" | "from"
            | "it" | "its" | "they" | "them" | "their" | "we" | "our" | "my" | "your"
            | "i" | "me" | "he" | "she" | "him" | "her" | "us" | "you"
            | "and" | "or" | "but" | "nor" | "so" | "yet"
            | "if" | "then" | "else" | "when" | "while" | "as" | "than"
            | "not" | "no" | "don" | "won" | "doesn" | "didn"
            | "very" | "also" | "just" | "only" | "even" | "still" | "too"
            | "all" | "each" | "every" | "some" | "any" | "many" | "much" | "few"
            | "what" | "which" | "who" | "whom" | "whose" | "where" | "how" | "why"
            | "there" | "here" | "now" | "up" | "out" | "about"
            // Punctuation
            | "." | "," | ";" | ":" | "!" | "?" | "'" | "\""
    )
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
    fn test_prompt_dont_use_react() {
        let tok = make_tokenizer();
        let result = analyze_prompt(&tok, "I don't want to use React.", &[]);
        assert!(
            result.negated_terms.contains(&"react".to_string()),
            "Expected 'react' negated, got: {:?}", result.negated_terms
        );
    }

    #[test]
    fn test_prompt_avoid_like() {
        let tok = make_tokenizer();
        let result = analyze_prompt(
            &tok,
            "Avoid frameworks like Vue and Angular.",
            &[]
        );
        assert!(result.negated_terms.contains(&"vue".to_string()), "Expected 'vue' negated");
        assert!(result.negated_terms.contains(&"angular".to_string()), "Expected 'angular' negated");
    }

    #[test]
    fn test_prompt_but_for() {
        let tok = make_tokenizer();
        let result = analyze_prompt(
            &tok,
            "Morphology and chemistry but for language purposes only.",
            &[]
        );
        // morphology and chemistry should be negated (contextual)
        assert!(
            result.negated_terms.iter().any(|t| t == "morphology" || t == "chemistry"),
            "Expected morphology/chemistry negated, got: {:?}", result.negated_terms
        );
        // language should NOT be negated (it's the actual scope)
        assert!(
            !result.negated_terms.contains(&"language".to_string()),
            "Expected 'language' NOT negated"
        );
    }

    #[test]
    fn test_prompt_outside_scope() {
        let tok = make_tokenizer();
        let result = analyze_prompt(
            &tok,
            "Protocols outside the scope of geography.",
            &[]
        );
        assert!(
            result.negated_terms.contains(&"geography".to_string()),
            "Expected 'geography' negated, got: {:?}", result.negated_terms
        );
    }

    #[test]
    fn test_prompt_not_relevant_for() {
        let tok = make_tokenizer();
        let result = analyze_prompt(
            &tok,
            "The data is not relevant for those who study medicine.",
            &[]
        );
        assert!(
            result.negated_terms.contains(&"medicine".to_string()),
            "Expected 'medicine' negated, got: {:?}", result.negated_terms
        );
    }

    #[test]
    fn test_index_incompatibility() {
        let tok = make_tokenizer();
        let result = analyze_index(
            &tok,
            "Not compatible with Python. Works great with JavaScript."
        );
        assert!(
            result.negative_keywords.contains(&"python".to_string()),
            "Expected 'python' in negative_keywords, got: {:?}", result.negative_keywords
        );
        assert!(
            result.positive_keywords.contains(&"javascript".to_string()),
            "Expected 'javascript' in positive_keywords, got: {:?}", result.positive_keywords
        );
    }
}
