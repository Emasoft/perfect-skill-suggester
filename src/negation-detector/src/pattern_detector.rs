use crate::models::{AnnotatedSentence, NegationScope, NegationPatternType};
use regex::Regex;

/// Detects complex negation patterns that require more than simple regex:
/// - POS-aware scope tracking (how far does "not" extend?)
/// - Chunk-based noun phrase identification (what entities are in the negation scope?)
/// - Multi-pattern composition (overlapping patterns in one sentence)
pub struct PatternDetector;

impl PatternDetector {
    /// Run all pattern detectors on a sentence and return all detected negation scopes.
    /// Order matters: more specific patterns (AvoidanceLike, ButFor) are checked first,
    /// then general negation scope is computed for remaining negation markers.
    pub fn detect_all(sentence: &AnnotatedSentence) -> Vec<NegationScope> {
        let mut scopes = Vec::new();
        // Track which token indices are already covered by a specific pattern
        let mut covered_indices: Vec<bool> = vec![false; sentence.tokens.len()];

        // Phase 1: Detect specific complex patterns (these take priority)

        // 1. "avoid ... like X and Y"
        if let Some(scope) = Self::detect_avoidance_like(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 2. "X and Y but for Z"
        if let Some(scope) = Self::detect_but_for(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 3. "outside the scope of X"
        if let Some(scope) = Self::detect_outside_scope(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 4. "not relevant for those who study/work in X"
        if let Some(scope) = Self::detect_not_relevant_for(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 5. "not compatible with X" / "doesn't work with X"
        if let Some(scope) = Self::detect_incompatibility(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 6. "instead of X"
        if let Some(scope) = Self::detect_instead_of(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 7. "except X" / "excluding X"
        if let Some(scope) = Self::detect_exclusion(sentence) {
            for i in scope.scope_start..=scope.scope_end.min(sentence.tokens.len() - 1) {
                covered_indices[i] = true;
            }
            scopes.push(scope);
        }

        // 8. "only X" quantifier (handled specially — negates everything NOT X)
        if let Some(scope) = Self::detect_only_quantifier(sentence) {
            // Don't mark covered — only-quantifier is orthogonal
            scopes.push(scope);
        }

        // Phase 2: General negation scope for uncovered negation markers
        // For each negation marker not already covered by a specific pattern,
        // compute its scope using POS/chunk-based clause boundary detection.
        for (i, token) in sentence.tokens.iter().enumerate() {
            if token.is_negation && !covered_indices[i] {
                if let Some(scope) = Self::compute_general_negation_scope(sentence, i) {
                    scopes.push(scope);
                }
            }
        }

        scopes
    }

    /// Pattern 1: "avoid/skip/exclude ... like X and Y"
    /// Uses regex for pattern detection + POS for entity extraction.
    /// The regex alone can't reliably identify which words are entities (nouns)
    /// vs. function words — POS tags solve this.
    fn detect_avoidance_like(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        let re = Regex::new(
            r"(?i)\b(avoid|skip|exclude|omit|ignore)\b[^.!?]*\blike\s+(.+?)(?:\.|!|\?|$)"
        ).ok()?;

        let caps = re.captures(&text_lower)?;
        let marker_word = caps.get(1)?.as_str();
        let entities_text = caps.get(2)?.as_str();

        // Find the marker token index using POS to confirm it's a verb
        let marker_idx = sentence.tokens.iter().position(|t| {
            t.text_lower == marker_word && t.all_pos.iter().any(|p| p.starts_with("VB"))
        })?;

        // Find the "like" token index
        let like_idx = sentence.tokens.iter().position(|t| t.text_lower == "like" && t.index > marker_idx)?;

        // Extract nouns after "like" using POS tags — this is what regex can't do
        // reliably. "avoid frameworks like Vue and Angular" → only "Vue", "Angular"
        // are nouns (NNP), not "and" (CC) or "frameworks" (NNS, which is the object
        // being avoided, not the specific entities).
        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > like_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        if negated.is_empty() {
            // Fallback: parse the regex-captured entity list
            let fallback = Self::parse_entity_list(entities_text);
            if fallback.is_empty() {
                return None;
            }
            return Some(NegationScope {
                pattern_type: NegationPatternType::AvoidanceLike,
                marker_index: marker_idx,
                scope_start: marker_idx,
                scope_end: sentence.tokens.len() - 1,
                marker_text: format!("{} ... like", marker_word),
                negated_terms: fallback,
                non_negated_terms: vec![],
            });
        }

        Some(NegationScope {
            pattern_type: NegationPatternType::AvoidanceLike,
            marker_index: marker_idx,
            scope_start: marker_idx,
            scope_end: sentence.tokens.len() - 1,
            marker_text: format!("{} ... like", marker_word),
            negated_terms: negated,
            non_negated_terms: vec![],
        })
    }

    /// Pattern 2: "X and Y but for Z"
    /// X and Y are contextual/analogical mentions — they are NEGATED (not the actual topic).
    /// Z is the actual scope — NOT negated.
    /// This requires understanding the grammatical structure: "but for" reverses the
    /// subject/object relationship. POS tags help identify which words are nouns.
    fn detect_but_for(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        // Match: (noun-phrase) but for/only (noun-phrase)
        let re = Regex::new(
            r"(?i)(\w+(?:\s+and\s+\w+)*)\s+but\s+(?:for|only)\s+(\w+)"
        ).ok()?;

        let caps = re.captures(&text_lower)?;
        let context_part = caps.get(1)?.as_str();
        let scope_part = caps.get(2)?.as_str();

        // Find the "but" token
        let but_idx = sentence.tokens.iter().position(|t| t.text_lower == "but")?;

        // The nouns BEFORE "but" are the contextual (negated) terms
        // The nouns AFTER "but for" are the actual scope (not negated)
        // POS tags help: we only collect nouns, not conjunctions/prepositions
        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index < but_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        let non_negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > but_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        if negated.is_empty() {
            // Fallback to regex-parsed entities
            let neg_fallback = Self::parse_entity_list(context_part);
            if neg_fallback.is_empty() { return None; }
            return Some(NegationScope {
                pattern_type: NegationPatternType::ButForPattern,
                marker_index: but_idx,
                scope_start: 0,
                scope_end: but_idx.saturating_sub(1),
                marker_text: "but for".to_string(),
                negated_terms: neg_fallback,
                non_negated_terms: vec![scope_part.to_string()],
            });
        }

        Some(NegationScope {
            pattern_type: NegationPatternType::ButForPattern,
            marker_index: but_idx,
            scope_start: 0,
            scope_end: but_idx.saturating_sub(1),
            marker_text: "but for".to_string(),
            negated_terms: negated,
            non_negated_terms: non_negated,
        })
    }

    /// Pattern 3: "outside/beyond the scope of X"
    fn detect_outside_scope(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        let re = Regex::new(
            r"(?i)\b(outside|beyond)\b\s+(?:the\s+)?scope\s+of\s+(\w+)"
        ).ok()?;

        let caps = re.captures(&text_lower)?;
        let marker_word = caps.get(1)?.as_str();
        let entity = caps.get(2)?.as_str();

        let marker_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == marker_word)?;

        // "scope of X" — X is the excluded entity
        // POS confirms X is a noun
        let of_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == "of" && t.index > marker_idx)?;

        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > of_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        let final_negated = if negated.is_empty() {
            vec![entity.to_string()]
        } else {
            negated
        };

        Some(NegationScope {
            pattern_type: NegationPatternType::OutsideScope,
            marker_index: marker_idx,
            scope_start: marker_idx,
            scope_end: sentence.tokens.len() - 1,
            marker_text: format!("{} the scope of", marker_word),
            negated_terms: final_negated,
            non_negated_terms: vec![],
        })
    }

    /// Pattern 4: "not relevant for those who study/work in X"
    /// This is an INDIRECT negation chain: "not" → "relevant" → "for" → "study" → X
    /// Regex can match the pattern, but POS helps identify the actual entity X
    /// vs. function words in the chain.
    fn detect_not_relevant_for(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        let re = Regex::new(
            r"(?i)\bnot\s+relevant\s+(?:for|to)\s+(?:those\s+who\s+)?(?:study|work\s+(?:in|on|with)|use|practice)\s+(\w+)"
        ).ok()?;

        let caps = re.captures(&text_lower)?;
        let entity = caps.get(1)?.as_str();

        let not_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == "not" || t.lemma == "not")?;

        // The entity mentioned in the "study/work" clause is negated
        let negated: Vec<String> = vec![entity.to_lowercase()];

        Some(NegationScope {
            pattern_type: NegationPatternType::NotRelevantFor,
            marker_index: not_idx,
            scope_start: not_idx,
            scope_end: sentence.tokens.len() - 1,
            marker_text: "not relevant for".to_string(),
            negated_terms: negated,
            non_negated_terms: vec![],
        })
    }

    /// Pattern 5: "not compatible/supported with X" / "doesn't work with X"
    fn detect_incompatibility(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();

        // Multiple incompatibility patterns
        let patterns = [
            r"(?i)\bnot\s+(?:compatible|supported|designed|intended|suitable)\s+(?:for|with)\s+(.+?)(?:\.|!|\?|,|$)",
            r"(?i)\b(?:doesn|does\s*n|don|do\s*n|won|will\s*n|can\s*n)['\s]*t?\s+(?:work|function|run|compile)\s+(?:with|on|in|for)\s+(.+?)(?:\.|!|\?|,|$)",
            r"(?i)\b(?:incompatible|unsupported)\s+(?:with|for)\s+(.+?)(?:\.|!|\?|,|$)",
        ];

        for pattern in &patterns {
            if let Ok(re) = Regex::new(pattern) {
                if let Some(caps) = re.captures(&text_lower) {
                    if let Some(entity_match) = caps.get(1) {
                        let entity_text = entity_match.as_str();

                        // Find the negation marker
                        let marker_idx = sentence.tokens.iter()
                            .position(|t| t.is_negation)
                            .unwrap_or(0);

                        // Use POS to extract only nouns from the entity text
                        // e.g., "with Python and Ruby" → only "Python", "Ruby" (NNP)
                        let with_idx = sentence.tokens.iter()
                            .position(|t| t.text_lower == "with" || t.text_lower == "for")
                            .unwrap_or(marker_idx);

                        let negated: Vec<String> = sentence.tokens.iter()
                            .filter(|t| t.index > with_idx && t.is_noun)
                            .map(|t| t.text_lower.clone())
                            .collect();

                        let final_negated = if negated.is_empty() {
                            Self::parse_entity_list(entity_text)
                        } else {
                            negated
                        };

                        if !final_negated.is_empty() {
                            return Some(NegationScope {
                                pattern_type: NegationPatternType::IncompatibilityMarker,
                                marker_index: marker_idx,
                                scope_start: marker_idx,
                                scope_end: sentence.tokens.len() - 1,
                                marker_text: "not compatible with".to_string(),
                                negated_terms: final_negated,
                                non_negated_terms: vec![],
                            });
                        }
                    }
                }
            }
        }

        None
    }

    /// Pattern 6: "instead of X"
    fn detect_instead_of(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        let re = Regex::new(r"(?i)\binstead\s+of\s+(.+?)(?:\.|!|\?|,|$)").ok()?;

        let caps = re.captures(&text_lower)?;
        let entity_text = caps.get(1)?.as_str();

        let instead_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == "instead")?;
        let of_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == "of" && t.index > instead_idx)?;

        // Nouns after "of" are the rejected alternatives
        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > of_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        let final_negated = if negated.is_empty() {
            Self::parse_entity_list(entity_text)
        } else {
            negated
        };

        if final_negated.is_empty() { return None; }

        Some(NegationScope {
            pattern_type: NegationPatternType::InsteadOf,
            marker_index: instead_idx,
            scope_start: instead_idx,
            scope_end: sentence.tokens.len() - 1,
            marker_text: "instead of".to_string(),
            negated_terms: final_negated,
            non_negated_terms: vec![],
        })
    }

    /// Pattern 7: "except X" / "excluding X"
    fn detect_exclusion(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        let text_lower = sentence.text.to_lowercase();
        let re = Regex::new(
            r"(?i)\b(except|excluding|other\s+than)\s+(?:for\s+)?(.+?)(?:\.|!|\?|,|$)"
        ).ok()?;

        let caps = re.captures(&text_lower)?;
        let marker_word = caps.get(1)?.as_str().split_whitespace().next()?;
        let entity_text = caps.get(2)?.as_str();

        let marker_idx = sentence.tokens.iter()
            .position(|t| t.text_lower == marker_word)?;

        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > marker_idx && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        let final_negated = if negated.is_empty() {
            Self::parse_entity_list(entity_text)
        } else {
            negated
        };

        if final_negated.is_empty() { return None; }

        Some(NegationScope {
            pattern_type: NegationPatternType::ExclusionMarker,
            marker_index: marker_idx,
            scope_start: marker_idx,
            scope_end: sentence.tokens.len() - 1,
            marker_text: marker_word.to_string(),
            negated_terms: final_negated,
            non_negated_terms: vec![],
        })
    }

    /// Pattern 8: "only X" quantifier
    /// When "only" appears, everything that is NOT X is implicitly excluded.
    /// This is fundamentally different from other patterns — it doesn't negate
    /// specific terms, it restricts to a specific term.
    /// Returns the term that is NOT negated (the "only" target).
    fn detect_only_quantifier(sentence: &AnnotatedSentence) -> Option<NegationScope> {
        // Find "only" with POS RB (adverb) or JJ (adjective)
        let only_idx = sentence.tokens.iter().position(|t| {
            t.text_lower == "only"
                && t.all_pos.iter().any(|p| p == "RB" || p == "JJ")
        })?;

        // The "only" target is the nearest noun phrase
        // Case 1: "only X" — noun follows "only"
        // Case 2: "X only" — noun precedes "only"
        let target_noun = sentence.tokens.iter()
            .find(|t| {
                t.is_noun && (
                    // Noun after "only" (within 3 tokens)
                    (t.index > only_idx && t.index <= only_idx + 3) ||
                    // Noun before "only" (within 2 tokens)
                    (t.index < only_idx && only_idx - t.index <= 2)
                )
            });

        let target = target_noun?.text_lower.clone();

        // All OTHER nouns in the sentence are implicitly negated
        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.is_noun && t.text_lower != target)
            .map(|t| t.text_lower.clone())
            .collect();

        // If no other nouns, the "only" doesn't create exclusion
        if negated.is_empty() {
            return None;
        }

        Some(NegationScope {
            pattern_type: NegationPatternType::OnlyQuantifier,
            marker_index: only_idx,
            scope_start: 0,
            scope_end: sentence.tokens.len() - 1,
            marker_text: "only".to_string(),
            negated_terms: negated,
            non_negated_terms: vec![target],
        })
    }

    /// General negation scope computation for simple negation markers
    /// (not already handled by specific patterns).
    ///
    /// This is the core advantage over regex: we use POS tags and chunk boundaries
    /// to determine how far the negation extends.
    ///
    /// Scope rules:
    /// 1. Negation extends forward until a clause boundary (comma, semicolon,
    ///    coordinating conjunction "but", period)
    /// 2. Negation covers the nearest verb phrase and its object noun phrase
    /// 3. If the negation marker is an avoidance verb (avoid, skip),
    ///    scope extends to the end of the sentence
    fn compute_general_negation_scope(
        sentence: &AnnotatedSentence,
        negation_idx: usize,
    ) -> Option<NegationScope> {
        let marker = &sentence.tokens[negation_idx];

        // Determine scope end based on clause boundaries
        let scope_end = Self::find_clause_boundary(sentence, negation_idx);

        // Determine if this is an avoidance verb (broader scope) or particle (narrower)
        let is_avoidance = marker.all_pos.iter().any(|p| p.starts_with("VB"))
            && crate::tokenizer::AVOIDANCE_VERBS.contains(&marker.text_lower.as_str());

        // For avoidance verbs, scope extends to end of sentence
        let effective_end = if is_avoidance {
            sentence.tokens.len() - 1
        } else {
            scope_end
        };

        // Collect nouns within the negation scope
        let negated: Vec<String> = sentence.tokens.iter()
            .filter(|t| t.index > negation_idx && t.index <= effective_end && t.is_noun)
            .map(|t| t.text_lower.clone())
            .collect();

        if negated.is_empty() {
            return None;
        }

        Some(NegationScope {
            pattern_type: NegationPatternType::ExplicitNegation,
            marker_index: negation_idx,
            scope_start: negation_idx,
            scope_end: effective_end,
            marker_text: marker.text_lower.clone(),
            negated_terms: negated,
            non_negated_terms: vec![],
        })
    }

    /// Find the clause boundary after a given token index.
    /// Clause boundaries: comma, semicolon, "but" (CC), period, end of sentence.
    /// Returns the index of the last token before the boundary.
    fn find_clause_boundary(sentence: &AnnotatedSentence, start_idx: usize) -> usize {
        for token in sentence.tokens.iter() {
            if token.index <= start_idx {
                continue;
            }
            // Clause boundary markers
            if token.text_lower == "," || token.text_lower == ";" {
                return token.index.saturating_sub(1);
            }
            // "but" as coordinating conjunction signals a new clause
            if token.text_lower == "but" && token.all_pos.iter().any(|p| p == "CC") {
                return token.index.saturating_sub(1);
            }
            // Period/sentence end
            if token.text_lower == "." || token.all_pos.iter().any(|p| p == "SENT_END") {
                return token.index.saturating_sub(1);
            }
        }
        // No boundary found — scope extends to end of sentence
        sentence.tokens.len().saturating_sub(1)
    }

    /// Parse a comma/and-separated list of entities from regex-captured text.
    /// Used as fallback when POS-based entity extraction finds nothing.
    fn parse_entity_list(text: &str) -> Vec<String> {
        text.split(|c: char| c == ',' || c == '&')
            .flat_map(|s| s.split(" and "))
            .flat_map(|s| s.split(" or "))
            .map(|s| s.trim().to_lowercase())
            .filter(|s| !s.is_empty() && s.len() > 1)
            // Filter out function words
            .filter(|s| !matches!(
                s.as_str(),
                "the" | "a" | "an" | "this" | "that" | "these" | "those"
                    | "is" | "are" | "was" | "were" | "be" | "been"
                    | "to" | "of" | "in" | "on" | "at" | "by" | "for" | "with"
                    | "it" | "its" | "they" | "them" | "their" | "we" | "our"
            ))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tokenizer::NlpTokenizer;

    fn make_tokenizer() -> NlpTokenizer {
        let bytes = include_bytes!(concat!(
            env!("OUT_DIR"),
            "/",
            nlprule::tokenizer_filename!("en")
        ));
        NlpTokenizer::new(bytes).expect("Failed to load tokenizer")
    }

    #[test]
    fn test_avoidance_like_pattern() {
        let tok = make_tokenizer();
        let sentences = tok.analyze(
            "Avoid frameworks like Vue and Angular."
        );
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let avoidance = scopes.iter().find(|s| s.pattern_type == NegationPatternType::AvoidanceLike);
        assert!(avoidance.is_some(), "Expected AvoidanceLike pattern");
        let scope = avoidance.unwrap();
        assert!(scope.negated_terms.contains(&"vue".to_string()), "Expected 'vue' negated");
        assert!(scope.negated_terms.contains(&"angular".to_string()), "Expected 'angular' negated");
    }

    #[test]
    fn test_but_for_pattern() {
        let tok = make_tokenizer();
        let sentences = tok.analyze(
            "Morphology and chemistry but for language purposes only."
        );
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let but_for = scopes.iter().find(|s| s.pattern_type == NegationPatternType::ButForPattern);
        assert!(but_for.is_some(), "Expected ButForPattern");
        let scope = but_for.unwrap();
        assert!(
            scope.negated_terms.iter().any(|t| t == "morphology" || t == "chemistry"),
            "Expected morphology/chemistry negated, got: {:?}", scope.negated_terms
        );
        assert!(
            scope.non_negated_terms.iter().any(|t| t == "language" || t == "purposes"),
            "Expected language in non-negated, got: {:?}", scope.non_negated_terms
        );
    }

    #[test]
    fn test_outside_scope_pattern() {
        let tok = make_tokenizer();
        let sentences = tok.analyze(
            "Protocols to use in fields outside the scope of geography."
        );
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let outside = scopes.iter().find(|s| s.pattern_type == NegationPatternType::OutsideScope);
        assert!(outside.is_some(), "Expected OutsideScope pattern");
        assert!(
            outside.unwrap().negated_terms.contains(&"geography".to_string()),
            "Expected 'geography' negated"
        );
    }

    #[test]
    fn test_not_relevant_for_pattern() {
        let tok = make_tokenizer();
        let sentences = tok.analyze(
            "The data is not relevant for those who study geography."
        );
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let nrf = scopes.iter().find(|s| s.pattern_type == NegationPatternType::NotRelevantFor);
        assert!(nrf.is_some(), "Expected NotRelevantFor pattern");
        assert!(
            nrf.unwrap().negated_terms.contains(&"geography".to_string()),
            "Expected 'geography' negated"
        );
    }

    #[test]
    fn test_general_negation_scope() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("I don't want to use React.");
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let has_react_negated = scopes.iter().any(|s| {
            s.negated_terms.contains(&"react".to_string())
        });
        assert!(has_react_negated, "Expected 'react' negated by general scope. Scopes: {:?}",
            scopes.iter().map(|s| (&s.pattern_type, &s.negated_terms)).collect::<Vec<_>>()
        );
    }

    #[test]
    fn test_incompatibility_pattern() {
        let tok = make_tokenizer();
        let sentences = tok.analyze("This skill is not compatible with Python.");
        let scopes = PatternDetector::detect_all(&sentences[0]);
        let incompat = scopes.iter().find(|s| s.pattern_type == NegationPatternType::IncompatibilityMarker);
        assert!(incompat.is_some(), "Expected IncompatibilityMarker pattern");
        assert!(
            incompat.unwrap().negated_terms.contains(&"python".to_string()),
            "Expected 'python' negated"
        );
    }
}
