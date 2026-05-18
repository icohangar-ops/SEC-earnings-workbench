//! # Financial Sentiment Analysis
//!
//! Provides financial sentiment scoring with forward-looking statement detection,
//! management tone analysis, risk disclosure intensity scoring, and sector-relative
//! sentiment comparison using curated financial lexicons.

use crate::types::{ManagementTone, SentimentScore};
use regex::Regex;

/// Financial sentiment analyzer for SEC filings and earnings transcripts.
#[derive(Debug)]
pub struct EarningsSentimentAnalyzer {
    positive_lexicon: Vec<String>,
    negative_lexicon: Vec<String>,
    risk_lexicon: Vec<String>,
    forward_looking_pattern: Regex,
    negation_pattern: Regex,
    intensifier_pattern: Regex,
}

impl Default for EarningsSentimentAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl EarningsSentimentAnalyzer {
    /// Create a new analyzer with curated financial lexicons.
    pub fn new() -> Self {
        let positive = vec![
            "record".into(),
            "growth".into(),
            "exceeded".into(),
            "outperformed".into(),
            "innovation".into(),
            "margin expansion".into(),
            "strong".into(),
            "solid".into(),
            "robust".into(),
            "increased".into(),
            "improved".into(),
            "efficient".into(),
            "optimistic".into(),
            "momentum".into(),
            "accelerated".into(),
            "exceeding".into(),
            "opportunity".into(),
            "successful".into(),
            "dividend".into(),
            "profitable".into(),
            "upside".into(),
            "resilient".into(),
            "sustainable".into(),
            "leading".into(),
            "breakthrough".into(),
        ];

        let negative = vec![
            "decline".into(),
            "impairment".into(),
            "uncertainty".into(),
            "headwinds".into(),
            "challenging".into(),
            "restructuring".into(),
            "decreased".into(),
            "weakened".into(),
            "loss".into(),
            "downside".into(),
            "volatile".into(),
            "pressure".into(),
            "difficult".into(),
            "deteriorating".into(),
            "reduction".into(),
            "write-down".into(),
            "litigation".into(),
            "deficit".into(),
            "cautious".into(),
            "recession".into(),
            "inflation".into(),
            "contraction".into(),
            "obsolescence".into(),
            "distress".into(),
            "impacted".into(),
        ];

        let risk = vec![
            "may".into(),
            "could".into(),
            "risk".into(),
            "uncertain".into(),
            "adversely affect".into(),
            "material".into(),
            "potential".into(),
            "exposure".into(),
            "contingent".into(),
            "liability".into(),
            "adverse".into(),
            "fluctuation".into(),
            "disruption".into(),
            "depend".into(),
            "subject to".into(),
            "if".into(),
            "volatile".into(),
            "unpredictable".into(),
            "uncertainty".into(),
            "threat".into(),
        ];

        Self {
            positive_lexicon: positive,
            negative_lexicon: negative,
            risk_lexicon: risk,
            forward_looking_pattern: Regex::new(
                r"(?i)(?:we (?:expect|anticipate|believe|intend|plan|project|estimate|forecast|are confident)|forward[- ]?looking|outlook|guidance|going forward|future|anticipated)",
            )
            .unwrap(),
            negation_pattern: Regex::new(
                r"(?i)\b(?:not|no|never|neither|nor|cannot|n't)\b",
            )
            .unwrap(),
            intensifier_pattern: Regex::new(
                r"(?i)\b(?:very|extremely|highly|significantly|substantially|remarkably|particularly)\b",
            )
            .unwrap(),
        }
    }

    /// Analyze full text and return a comprehensive sentiment score.
    pub fn analyze(&self, text: &str) -> SentimentScore {
        let overall = self.overall_sentiment(text);
        let forward = self.forward_looking_sentiment(text);
        let risk = self.risk_disclosure_score(text);
        let tone = self.management_tone_score(text);
        SentimentScore {
            overall,
            forward_looking: forward,
            risk_disclosures: risk,
            management_tone: tone,
            sector_context: None,
        }
    }

    /// Compute overall sentiment score (0.0 = negative, 1.0 = positive).
    pub fn overall_sentiment(&self, text: &str) -> f64 {
        let lower = text.to_lowercase();
        let pos_count = self.count_matches(&lower, &self.positive_lexicon);
        let neg_count = self.count_matches(&lower, &self.negative_lexicon);
        let total = pos_count + neg_count;
        if total == 0 {
            return 0.5; // neutral
        }
        let raw = (pos_count as f64) / (total as f64);
        raw.clamp(0.0, 1.0)
    }

    /// Score forward-looking statements (sentiment of future-oriented language).
    pub fn forward_looking_sentiment(&self, text: &str) -> f64 {
        let sentences = self.extract_forward_looking(text);
        if sentences.is_empty() {
            return 0.5;
        }
        let total_sentiment: f64 = sentences
            .iter()
            .map(|s| self.overall_sentiment(s))
            .sum();
        (total_sentiment / sentences.len() as f64).clamp(0.0, 1.0)
    }

    /// Score risk disclosure intensity (0.0 = low risk, 1.0 = high risk).
    pub fn risk_disclosure_score(&self, text: &str) -> f64 {
        let lower = text.to_lowercase();
        let word_count = lower.split_whitespace().count();
        if word_count == 0 {
            return 0.0;
        }
        let risk_count = self.count_matches(&lower, &self.risk_lexicon);
        let risk_density = risk_count as f64 / word_count as f64;
        // Normalize: 0-2% risk density maps to 0-1
        (risk_density / 0.02).clamp(0.0, 1.0)
    }

    /// Compute management tone score (0.0 = cautious, 1.0 = optimistic).
    pub fn management_tone_score(&self, text: &str) -> f64 {
        let lower = text.to_lowercase();
        let pos_count = self.count_matches(&lower, &self.positive_lexicon);
        let neg_count = self.count_matches(&lower, &self.negative_lexicon);
        let total = pos_count + neg_count;
        if total == 0 {
            return 0.5;
        }
        let raw = (pos_count as f64) / (total as f64);
        // Apply intensifier weighting
        let intensifiers = self.intensifier_pattern.find_iter(&lower).count();
        let modifier = if intensifiers > 0 {
            1.0 + (intensifiers as f64 * 0.05).min(0.2)
        } else {
            1.0
        };
        (raw * modifier).clamp(0.0, 1.0)
    }

    /// Classify management tone into categories.
    pub fn classify_tone(&self, text: &str) -> ManagementTone {
        let score = self.management_tone_score(text);
        ManagementTone::from_score(score)
    }

    /// Extract forward-looking sentences from text.
    pub fn extract_forward_looking(&self, text: &str) -> Vec<String> {
        let mut results = Vec::new();
        for sentence in text.split(&['.', '!', '?'][..]) {
            let trimmed = sentence.trim();
            if self.forward_looking_pattern.is_match(trimmed) {
                results.push(trimmed.to_string());
            }
        }
        results
    }

    /// Detect forward-looking statements and return count.
    pub fn count_forward_looking(&self, text: &str) -> usize {
        self.extract_forward_looking(text).len()
    }

    /// Compute sector-relative sentiment (compares to a sector benchmark).
    pub fn sector_relative_sentiment(&self, text: &str, sector_benchmark: f64) -> f64 {
        let score = self.overall_sentiment(text);
        // Difference from benchmark, mapped to 0-1 range
        let diff = score - sector_benchmark;
        (0.5 + diff * 2.0).clamp(0.0, 1.0)
    }

    /// Analyze earnings call transcript patterns.
    pub fn analyze_transcript(&self, text: &str) -> TranscriptSentiment {
        let overall = self.overall_sentiment(text);
        let tone = self.classify_tone(text);
        let forward_count = self.count_forward_looking(text);
        let risk_score = self.risk_disclosure_score(text);

        // Confidence score: high when tone is clear (far from 0.5)
        let confidence = (0.5 - (overall - 0.5).abs()).abs() * 2.0;

        TranscriptSentiment {
            overall_sentiment: overall,
            management_tone: tone,
            forward_statement_count: forward_count,
            risk_intensity: risk_score,
            confidence,
        }
    }

    /// Compare sentiment between two texts (e.g., current vs prior quarter).
    pub fn compare_sentiment(&self, text_a: &str, text_b: &str) -> SentimentComparison {
        let score_a = self.overall_sentiment(text_a);
        let score_b = self.overall_sentiment(text_b);
        let tone_a = self.classify_tone(text_a);
        let tone_b = self.classify_tone(text_b);
        let change = score_b - score_a;

        SentimentComparison {
            score_before: score_a,
            score_after: score_b,
            change,
            tone_before: tone_a,
            tone_after: tone_b,
            tone_changed: tone_a != tone_b,
        }
    }

    /// Sentiment breakdown by text sections.
    pub fn section_sentiment(&self, sections: &[(&str, &str)]) -> Vec<SectionSentiment> {
        sections
            .iter()
            .map(|(name, text)| SectionSentiment {
                section_name: name.to_string(),
                sentiment: self.overall_sentiment(text),
                risk_score: self.risk_disclosure_score(text),
                tone: self.classify_tone(text),
            })
            .collect()
    }

    /// Keyword hit counts for debugging / transparency.
    pub fn keyword_counts(&self, text: &str) -> KeywordCounts {
        let lower = text.to_lowercase();
        KeywordCounts {
            positive: self.count_matches(&lower, &self.positive_lexicon),
            negative: self.count_matches(&lower, &self.negative_lexicon),
            risk: self.count_matches(&lower, &self.risk_lexicon),
            negations: self.negation_pattern.find_iter(&lower).count(),
            intensifiers: self.intensifier_pattern.find_iter(&lower).count(),
        }
    }

    /// Count how many lexicon terms appear in text (word-level matching).
    fn count_matches(&self, text: &str, lexicon: &[String]) -> usize {
        let mut count = 0;
        for term in lexicon {
            // Multi-word terms need special handling
            if term.contains(' ') {
                if text.contains(term.as_str()) {
                    count += 1;
                }
            } else {
                // Single word: use word boundary matching
                let pattern = format!(r"\b{}\b", regex::escape(term));
                if let Ok(re) = Regex::new(&pattern) {
                    count += re.find_iter(text).count();
                }
            }
        }
        count
    }
}

/// Sentiment analysis result for an earnings call transcript.
#[derive(Debug, Clone)]
pub struct TranscriptSentiment {
    pub overall_sentiment: f64,
    pub management_tone: ManagementTone,
    pub forward_statement_count: usize,
    pub risk_intensity: f64,
    pub confidence: f64,
}

/// Comparison of sentiment between two texts.
#[derive(Debug, Clone)]
pub struct SentimentComparison {
    pub score_before: f64,
    pub score_after: f64,
    pub change: f64,
    pub tone_before: ManagementTone,
    pub tone_after: ManagementTone,
    pub tone_changed: bool,
}

/// Per-section sentiment breakdown.
#[derive(Debug, Clone)]
pub struct SectionSentiment {
    pub section_name: String,
    pub sentiment: f64,
    pub risk_score: f64,
    pub tone: ManagementTone,
}

/// Raw keyword hit counts for transparency.
#[derive(Debug, Clone)]
pub struct KeywordCounts {
    pub positive: usize,
    pub negative: usize,
    pub risk: usize,
    pub negations: usize,
    pub intensifiers: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_analyzer_new() {
        let analyzer = EarningsSentimentAnalyzer::new();
        assert!(!analyzer.positive_lexicon.is_empty());
        assert!(!analyzer.negative_lexicon.is_empty());
        assert!(!analyzer.risk_lexicon.is_empty());
    }

    #[test]
    fn test_overall_sentiment_positive() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We had record growth and exceeded expectations with strong innovation.";
        let score = analyzer.overall_sentiment(text);
        assert!(score > 0.5, "Expected positive sentiment, got {}", score);
    }

    #[test]
    fn test_overall_sentiment_negative() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We faced challenging headwinds and a decline in revenue due to restructuring.";
        let score = analyzer.overall_sentiment(text);
        assert!(score < 0.5, "Expected negative sentiment, got {}", score);
    }

    #[test]
    fn test_overall_sentiment_neutral() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "The company reported its quarterly results on Tuesday.";
        let score = analyzer.overall_sentiment(text);
        assert!(
            (score - 0.5).abs() < 0.01,
            "Expected neutral sentiment, got {}",
            score
        );
    }

    #[test]
    fn test_overall_sentiment_mixed() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We had record growth but also faced uncertainty and headwinds.";
        let score = analyzer.overall_sentiment(text);
        // Should be somewhere in the middle
        assert!(score > 0.2 && score < 0.8);
    }

    #[test]
    fn test_forward_looking_extraction() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We expect strong growth next quarter. The guidance is positive. Going forward, we plan to innovate.";
        let fwd = analyzer.extract_forward_looking(text);
        assert!(fwd.len() >= 2);
    }

    #[test]
    fn test_forward_looking_sentiment() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We expect record growth. We anticipate increased margin expansion.";
        let score = analyzer.forward_looking_sentiment(text);
        assert!(score > 0.5);
    }

    #[test]
    fn test_risk_disclosure_score_high() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "Risk factors may could adversely affect our material uncertain potential exposure. Risk: volatile unpredictable threat contingent liability.";
        let score = analyzer.risk_disclosure_score(text);
        assert!(score > 0.0, "Expected some risk score, got {}", score);
    }

    #[test]
    fn test_risk_disclosure_score_low() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "The company reported solid results.";
        let score = analyzer.risk_disclosure_score(text);
        assert!(score < 0.5, "Expected low risk score, got {}", score);
    }

    #[test]
    fn test_management_tone_optimistic() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We are very optimistic about our record growth and strong outperformance.";
        let tone = analyzer.classify_tone(text);
        assert_eq!(tone, ManagementTone::Optimistic);
    }

    #[test]
    fn test_management_tone_cautious() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We face challenging headwinds, decline, and uncertainty in difficult markets.";
        let tone = analyzer.classify_tone(text);
        assert_eq!(tone, ManagementTone::Cautious);
    }

    #[test]
    fn test_management_tone_neutral() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We reported quarterly revenue of $50 billion.";
        let tone = analyzer.classify_tone(text);
        assert_eq!(tone, ManagementTone::Neutral);
    }

    #[test]
    fn test_management_tone_score() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let score = analyzer.management_tone_score("record growth exceeded outperformed");
        assert!(score > 0.5);
    }

    #[test]
    fn test_sector_relative_sentiment_above() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "record growth exceeded outperformed strong";
        let relative = analyzer.sector_relative_sentiment(text, 0.5);
        assert!(relative > 0.5, "Expected above benchmark, got {}", relative);
    }

    #[test]
    fn test_sector_relative_sentiment_below() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "decline impairment challenging headwinds";
        let relative = analyzer.sector_relative_sentiment(text, 0.5);
        assert!(relative < 0.5, "Expected below benchmark, got {}", relative);
    }

    #[test]
    fn test_analyze_full() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We expect record growth. We anticipate margin expansion. We may face uncertainty. We are confident in our strong innovation.";
        let score = analyzer.analyze(text);
        assert!(score.overall > 0.0 && score.overall < 1.0);
        assert!(score.forward_looking > 0.0);
        assert!(score.risk_disclosures >= 0.0);
        assert!(score.management_tone > 0.0);
    }

    #[test]
    fn test_analyze_transcript() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We expect strong growth. We plan to innovate. Risk factors may affect us.";
        let result = analyzer.analyze_transcript(text);
        assert!(result.overall_sentiment > 0.0);
        assert!(result.forward_statement_count >= 1);
        assert!(result.confidence >= 0.0 && result.confidence <= 1.0);
    }

    #[test]
    fn test_compare_sentiment() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let positive = "record growth exceeded outperformed innovation";
        let negative = "decline impairment challenging headwinds restructuring";
        let comp = analyzer.compare_sentiment(positive, negative);
        assert!(comp.change < 0.0, "Expected negative change, got {}", comp.change);
        assert!(comp.tone_changed);
    }

    #[test]
    fn test_compare_sentiment_same() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "The company reported results.";
        let comp = analyzer.compare_sentiment(text, text);
        assert!((comp.change).abs() < 1e-10);
        assert!(!comp.tone_changed);
    }

    #[test]
    fn test_section_sentiment() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let sections = vec![
            ("Business", "We had record growth and strong innovation."),
            ("Risks", "We face uncertainty, headwinds, and risk of decline."),
        ];
        let results = analyzer.section_sentiment(&sections);
        assert_eq!(results.len(), 2);
        assert!(results[0].sentiment > results[1].sentiment);
    }

    #[test]
    fn test_keyword_counts() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "record growth and challenging decline with significantly high risk";
        let counts = analyzer.keyword_counts(text);
        assert!(counts.positive >= 2); // record, growth
        assert!(counts.negative >= 2); // challenging, decline
        assert!(counts.risk >= 1);
        assert!(counts.intensifiers >= 1); // significantly
    }

    #[test]
    fn test_count_forward_looking() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "We expect growth. We anticipate revenue. Normal sentence. We plan to invest.";
        let count = analyzer.count_forward_looking(text);
        assert_eq!(count, 3);
    }

    #[test]
    fn test_xbrl_sentiment_clean() {
        let analyzer = EarningsSentimentAnalyzer::new();
        let text = "record growth exceeded <us-gaap:Revenue>394328</us-gaap:Revenue> strong innovation";
        let score = analyzer.overall_sentiment(text);
        assert!(score > 0.5);
    }

    #[test]
    fn test_empty_text() {
        let analyzer = EarningsSentimentAnalyzer::new();
        assert!((analyzer.overall_sentiment("") - 0.5).abs() < 1e-10);
        assert!((analyzer.risk_disclosure_score("") - 0.0).abs() < 1e-10);
        assert_eq!(analyzer.count_forward_looking(""), 0);
    }
}
