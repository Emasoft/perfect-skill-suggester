//! pss-nlp: NLP-based negation detection binary for Perfect Skill Suggester.
//!
//! Reads JSON requests from stdin, one per line (JSONL).
//! Each request specifies a mode ("prompt" or "index") and text to analyze.
//! Returns JSON results to stdout, one per line.
//!
//! Usage:
//!   echo '{"mode":"prompt","text":"I don'\''t want React"}' | pss-nlp
//!   echo '{"mode":"index","text":"Not compatible with Python. Works with JS."}' | pss-nlp
//!   cat requests.jsonl | pss-nlp          # Batch mode (JSONL)
//!   pss-nlp --version                     # Print version
//!   pss-nlp --test                        # Run self-test with the 5 critical patterns

use pss_nlp::models::NlpRequest;
use pss_nlp::tokenizer::NlpTokenizer;
use std::io::{self, BufRead, Write};

/// Load the embedded English tokenizer model (downloaded at build time by nlprule-build)
fn load_tokenizer() -> NlpTokenizer {
    let tokenizer_bytes = include_bytes!(concat!(
        env!("OUT_DIR"),
        "/",
        nlprule::tokenizer_filename!("en")
    ));
    NlpTokenizer::new(tokenizer_bytes)
        .expect("Failed to load embedded nlprule English tokenizer")
}

/// Run the 5 critical negation pattern tests from the implementation plan
fn run_self_test(tokenizer: &NlpTokenizer) {
    let test_cases: &[(&str, &[&str], &[&str])] = &[
        // (text, expected_negated, expected_not_negated)
        (
            "will avoid entering in the fields most difficult, like electromagnetism and geography",
            &["electromagnetism", "geography"],
            &[],
        ),
        (
            "like morphology and chemistry but for language",
            &["morphology", "chemistry"],
            &["language"],
        ),
        (
            "protocols to use in fields that are outside the scope of geography",
            &["geography"],
            &[],
        ),
        (
            "the data is not relevant for those who study geography",
            &["geography"],
            &[],
        ),
        (
            "I don't want to use React",
            &["react"],
            &[],
        ),
        (
            "This skill is not compatible with Python",
            &["python"],
            &[],
        ),
        (
            "Use Vue instead of React and Angular",
            &["react", "angular"],
            &["vue"],
        ),
        (
            "Avoid frameworks like Redux. Just use context API.",
            &["redux"],
            &[],
        ),
    ];

    let mut passed = 0;
    let mut failed = 0;

    for (text, expected_negated, expected_not_negated) in test_cases {
        let request = NlpRequest {
            mode: "prompt".to_string(),
            text: text.to_string(),
            entities: vec![],
        };
        let result = pss_nlp::analyze(tokenizer, &request);
        let negated: Vec<String> = result["negated_terms"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();

        let mut test_passed = true;

        // Check expected negated terms are present
        for expected in *expected_negated {
            if !negated.contains(&expected.to_string()) {
                eprintln!(
                    "  FAIL: '{}' should be negated in: \"{}\"",
                    expected, text
                );
                eprintln!("    Got negated: {:?}", negated);
                test_passed = false;
            }
        }

        // Check expected non-negated terms are NOT in negated list
        for not_expected in *expected_not_negated {
            if negated.contains(&not_expected.to_string()) {
                eprintln!(
                    "  FAIL: '{}' should NOT be negated in: \"{}\"",
                    not_expected, text
                );
                eprintln!("    Got negated: {:?}", negated);
                test_passed = false;
            }
        }

        if test_passed {
            eprintln!("  PASS: \"{}\"", text);
            passed += 1;
        } else {
            failed += 1;
        }
    }

    eprintln!("\nResults: {} passed, {} failed", passed, failed);
    if failed > 0 {
        std::process::exit(1);
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    // Handle --version flag
    if args.iter().any(|a| a == "--version") {
        println!("pss-nlp 0.1.0");
        return;
    }

    // Load tokenizer once (model data is embedded in the binary)
    let tokenizer = load_tokenizer();

    // Handle --test flag
    if args.iter().any(|a| a == "--test") {
        run_self_test(&tokenizer);
        return;
    }

    // Main mode: read JSONL from stdin, process each line, write results to stdout
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(e) => {
                eprintln!("pss-nlp: read error: {}", e);
                continue;
            }
        };

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Parse the JSON request
        let request: NlpRequest = match serde_json::from_str(trimmed) {
            Ok(r) => r,
            Err(e) => {
                let error = serde_json::json!({"error": format!("Invalid JSON: {}", e)});
                writeln!(out, "{}", error).ok();
                continue;
            }
        };

        // Analyze and output result
        let result = pss_nlp::analyze(&tokenizer, &request);
        writeln!(out, "{}", result).ok();
    }
}
