//! # Risk Factor Extraction and Analysis
//!
//! Extracts risk factors from SEC filings, categorizes them, scores severity,
//! detects novelty (new vs recurring risks), and supports cross-filing comparison.

use crate::types::{RiskCategory, RiskFactor, Severity};
use regex::Regex;

/// Extracts and analyzes risk factors from SEC filing text.
#[derive(Debug)]
pub struct RiskFactorExtractor {
    category_patterns: Vec<(RiskCategory, Regex)>,
    severity_intensifiers: Vec<String>,
    severity_diminishers: Vec<String>,
    risk_sentence_pattern: Regex,
    item_1a_pattern: Regex,
}

impl Default for RiskFactorExtractor {
    fn default() -> Self {
        Self::new()
    }
}

impl RiskFactorExtractor {
    /// Create a new extractor with compiled patterns.
    pub fn new() -> Self {
        let category_patterns = vec![
            (RiskCategory::Market, Regex::new(r"(?i)market\s+risk|interest\s+rate|currency|exchange\s+rate|equity\s+volatility|inflation|commodity").unwrap()),
            (RiskCategory::Operational, Regex::new(r"(?i)operat|cyber|security\s+breach|supply\s+chain|infrastructure|disaster|business\s+continuity|IT\s+system").unwrap()),
            (RiskCategory::Environmental, Regex::new(r"(?i)climate|environment|carbon|emission|sustainab|renewable|esg|greenhouse").unwrap()),
            (RiskCategory::Regulatory, Regex::new(r"(?i)regulat|compliance|govern|legislation|federal|sec|fda|epa|antitrust|sanction|export\s+control").unwrap()),
            (RiskCategory::Financial, Regex::new(r"(?i)debt|liquidity|credit|default|borrowing|capital|leverage|cash\s+flow|financing|solvency").unwrap()),
            (RiskCategory::Strategic, Regex::new(r"(?i)compet|market\s+share|innovation|disruption|technolog|growth\s+strat|acquisit|diversif").unwrap()),
            (RiskCategory::Legal, Regex::new(r"(?i)litigat|lawsuit|claim|indemnif|intellectual\s+property|patent|trademark|lawsui").unwrap()),
        ];

        let severity_intensifiers = vec![
            "significant".into(), "material".into(), "severe".into(),
            "critical".into(), "substantial".into(), "serious".into(),
            "major".into(), "extreme".into(), "severe".into(),
        ];

        let severity_diminishers = vec![
            "minor".into(), "small".into(), "limited".into(),
            "manageable".into(), "unlikely".into(), "mitigated".into(),
        ];

        Self {
            category_patterns,
            severity_intensifiers,
            severity_diminishers,
            risk_sentence_pattern: Regex::new(
                r"(?i)(?:the|a|our|we)\s+(?:risk|threat|challenge|concern|exposure|vulnerability)\s+(?:of|that|is|from|related to)\s+(.+?[.!?])",
            )
            .unwrap(),
            item_1a_pattern: Regex::new(
                r"(?si)item\s+1a[.:]\s*risk\s+factor[s]?(.+)",
            )
            .unwrap(),
        }
    }

    /// Extract risk factors from a full filing text.
    pub fn extract_risks(&self, text: &str) -> Vec<RiskFactor> {
        // First try to extract from Item 1A section
        let risk_section = if let Some(caps) = self.item_1a_pattern.captures(text) {
            caps.get(1).map(|m| m.as_str()).unwrap_or(text)
        } else {
            text
        };

        let sentences: Vec<&str> = risk_section
            .split(&['.', '!', '?'][..])
            .filter(|s| s.trim().len() > 20)
            .collect();

        let mut risks = Vec::new();
        for sentence in sentences {
            let trimmed = sentence.trim();
            if self.is_risk_sentence(trimmed) {
                let category = self.categorize_risk(trimmed);
                let severity = self.score_severity(trimmed);
                let probability = self.estimate_probability(trimmed);
                risks.push(RiskFactor {
                    category,
                    description: trimmed.to_string(),
                    severity,
                    probability,
                    financial_impact: None,
                });
            }
        }

        risks
    }

    /// Extract risk factors from a specific section text.
    pub fn extract_from_section(&self, section_text: &str) -> Vec<RiskFactor> {
        self.extract_risks(section_text)
    }

    /// Categorize a risk text into a risk category.
    pub fn categorize_risk(&self, text: &str) -> RiskCategory {
        for (category, pattern) in &self.category_patterns {
            if pattern.is_match(text) {
                return *category;
            }
        }
        RiskCategory::Other
    }

    /// Score severity based on language intensity (returns 0.0–1.0).
    pub fn score_severity(&self, text: &str) -> Severity {
        let lower = text.to_lowercase();
        let mut score: f64 = 0.3; // base severity

        for intensifier in &self.severity_intensifiers {
            if lower.contains(intensifier) {
                score += 0.12;
            }
        }
        for diminisher in &self.severity_diminishers {
            if lower.contains(diminisher) {
                score -= 0.15;
            }
        }

        // Check for multiple risk indicators
        let risk_indicator_count = lower
            .split_whitespace()
            .filter(|w| {
                matches!(
                    *w,
                    "risk" | "threat" | "loss" | "damage" | "failure" | "breach"
                )
            })
            .count();
        score += risk_indicator_count as f64 * 0.05;

        Severity::from_score(score.clamp(0.0, 1.0))
    }

    /// Estimate probability of risk materializing (0.0–1.0).
    pub fn estimate_probability(&self, text: &str) -> f64 {
        let lower = text.to_lowercase();
        let mut score: f64 = 0.5;

        // Low probability indicators (check "unlikely" before "likely" since "unlikely" contains "likely")
        if lower.contains("unlikely") || lower.contains("remote") {
            score -= 0.25;
        }
        if lower.contains("possible but not probable") {
            score -= 0.15;
        }

        // High probability indicators
        if !lower.contains("unlikely") && (lower.contains("likely") || lower.contains("expected")) {
            score += 0.25;
        }
        if lower.contains("may") || lower.contains("could") {
            score += 0.1;
        }
        if lower.contains("will") {
            score += 0.3;
        }

        score.clamp(0.0, 1.0)
    }

    /// Detect if a sentence is a risk statement.
    pub fn is_risk_sentence(&self, text: &str) -> bool {
        let lower = text.to_lowercase();
        let risk_indicators = [
            "risk", "threat", "adversely", "could result", "may result",
            "uncertain", "potential", "exposure", "vulnerability", "material impact",
            "harm", "loss", "failure", "disruption",
        ];
        risk_indicators.iter().any(|ind| lower.contains(ind))
    }

    /// Compare risk factors between two filings (quarter-over-quarter changes).
    pub fn compare_filings(
        &self,
        current_risks: &[RiskFactor],
        prior_risks: &[RiskFactor],
    ) -> RiskComparison {
        let current_descs: std::collections::HashSet<_> = current_risks
            .iter()
            .map(|r| r.description.to_lowercase())
            .collect();

        let prior_descs: std::collections::HashSet<_> = prior_risks
            .iter()
            .map(|r| r.description.to_lowercase())
            .collect();

        let new_risks: Vec<_> = current_risks
            .iter()
            .filter(|r| !prior_descs.contains(&r.description.to_lowercase()))
            .cloned()
            .collect();

        let removed_risks: Vec<_> = prior_risks
            .iter()
            .filter(|r| !current_descs.contains(&r.description.to_lowercase()))
            .cloned()
            .collect();

        // Find recurring risks (description overlap via substring matching)
        let mut recurring: Vec<&RiskFactor> = Vec::new();
        let mut novel: Vec<&RiskFactor> = Vec::new();
        for risk in current_risks {
            let desc_lower = risk.description.to_lowercase();
            let is_recurring = prior_risks.iter().any(|pr| {
                let pr_lower = pr.description.to_lowercase();
                // Check if they share significant overlap (>50% words in common)
                let current_words: std::collections::HashSet<_> =
                    desc_lower.split_whitespace().collect();
                let prior_words: std::collections::HashSet<_> =
                    pr_lower.split_whitespace().collect();
                let intersection = current_words.intersection(&prior_words).count();
                let union = current_words.union(&prior_words).count();
                union > 0 && (intersection as f64 / union as f64) > 0.5
            });
            if is_recurring {
                recurring.push(risk);
            } else {
                novel.push(risk);
            }
        }

        let severity_changed: Vec<_> = current_risks
            .iter()
            .filter(|cr| {
                prior_risks.iter().any(|pr| {
                    let pr_lower = pr.description.to_lowercase();
                    let cr_lower = cr.description.to_lowercase();
                    cr_lower.contains(&pr_lower[..pr_lower.len().min(30)])
                        && pr.severity != cr.severity
                })
            })
            .cloned()
            .collect();

        let avg_severity_current = if current_risks.is_empty() {
            0.0
        } else {
            current_risks.iter().map(|r| r.composite_score()).sum::<f64>()
                / current_risks.len() as f64
        };
        let avg_severity_prior = if prior_risks.is_empty() {
            0.0
        } else {
            prior_risks.iter().map(|r| r.composite_score()).sum::<f64>()
                / prior_risks.len() as f64
        };

        RiskComparison {
            new_risks,
            removed_risks,
            recurring: recurring.into_iter().cloned().collect(),
            novel: novel.into_iter().cloned().collect(),
            severity_changed,
            total_current: current_risks.len(),
            total_prior: prior_risks.len(),
            avg_severity_current,
            avg_severity_prior,
            severity_trend: avg_severity_current - avg_severity_prior,
        }
    }

    /// Get risk summary statistics for a set of risk factors.
    pub fn risk_summary(&self, risks: &[RiskFactor]) -> RiskSummary {
        let total = risks.len();
        let critical = risks.iter().filter(|r| r.severity == Severity::Critical).count();
        let high = risks.iter().filter(|r| r.severity == Severity::High).count();
        let medium = risks.iter().filter(|r| r.severity == Severity::Medium).count();
        let low = risks.iter().filter(|r| r.severity == Severity::Low).count();

        let avg_severity = if total == 0 {
            0.0
        } else {
            risks.iter().map(|r| r.composite_score()).sum::<f64>() / total as f64
        };

        let category_counts: std::collections::HashMap<RiskCategory, usize> =
            risks.iter().fold(std::collections::HashMap::new(), |mut acc, r| {
                *acc.entry(r.category).or_insert(0) += 1;
                acc
            });

        RiskSummary {
            total,
            critical,
            high,
            medium,
            low,
            avg_composite_score: avg_severity,
            category_counts,
        }
    }
}

/// Result of comparing risk factors between two filings.
#[derive(Debug, Clone)]
pub struct RiskComparison {
    pub new_risks: Vec<RiskFactor>,
    pub removed_risks: Vec<RiskFactor>,
    pub recurring: Vec<RiskFactor>,
    pub novel: Vec<RiskFactor>,
    pub severity_changed: Vec<RiskFactor>,
    pub total_current: usize,
    pub total_prior: usize,
    pub avg_severity_current: f64,
    pub avg_severity_prior: f64,
    pub severity_trend: f64,
}

/// Summary statistics for a set of risk factors.
#[derive(Debug, Clone)]
pub struct RiskSummary {
    pub total: usize,
    pub critical: usize,
    pub high: usize,
    pub medium: usize,
    pub low: usize,
    pub avg_composite_score: f64,
    pub category_counts: std::collections::HashMap<RiskCategory, usize>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extractor_new() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(extractor.category_patterns.len(), 7);
    }

    #[test]
    fn test_extract_risks() {
        let extractor = RiskFactorExtractor::new();
        let text = "Item 1A. Risk Factors\n\nWe face significant market risks from interest rate changes that could adversely affect our business. Cyber security threats pose a material risk to our operations. Climate change regulations may create compliance burdens. We are exposed to currency exchange rate fluctuations that could result in losses. Our debt obligations present a credit risk.";
        let risks = extractor.extract_risks(text);
        assert!(risks.len() >= 3);
    }

    #[test]
    fn test_categorize_risk_market() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Interest rate and currency exchange rate risk"),
            RiskCategory::Market
        );
    }

    #[test]
    fn test_categorize_risk_operational() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Cyber security breach and supply chain disruption"),
            RiskCategory::Operational
        );
    }

    #[test]
    fn test_categorize_risk_regulatory() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Regulatory compliance with federal laws"),
            RiskCategory::Regulatory
        );
    }

    #[test]
    fn test_categorize_risk_financial() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Debt and liquidity credit risk"),
            RiskCategory::Financial
        );
    }

    #[test]
    fn test_categorize_risk_legal() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Litigation and intellectual property patent lawsuits"),
            RiskCategory::Legal
        );
    }

    #[test]
    fn test_categorize_risk_environmental() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Climate change and carbon emissions regulations"),
            RiskCategory::Environmental
        );
    }

    #[test]
    fn test_categorize_risk_other() {
        let extractor = RiskFactorExtractor::new();
        assert_eq!(
            extractor.categorize_risk("Something completely unrelated to anything"),
            RiskCategory::Other
        );
    }

    #[test]
    fn test_score_severity_high() {
        let extractor = RiskFactorExtractor::new();
        let severity = extractor.score_severity("This is a significant material threat that could cause severe loss and major damage and failure");
        assert!(severity >= Severity::High);
    }

    #[test]
    fn test_score_severity_low() {
        let extractor = RiskFactorExtractor::new();
        let severity = extractor.score_severity("We have a minor limited manageable risk that is unlikely");
        assert!(severity <= Severity::Medium);
    }

    #[test]
    fn test_estimate_probability_high() {
        let extractor = RiskFactorExtractor::new();
        let prob = extractor.estimate_probability("This will likely happen and is expected");
        assert!(prob > 0.5);
    }

    #[test]
    fn test_estimate_probability_low() {
        let extractor = RiskFactorExtractor::new();
        let prob = extractor.estimate_probability("This is unlikely and remote");
        assert!(prob < 0.5);
    }

    #[test]
    fn test_is_risk_sentence() {
        let extractor = RiskFactorExtractor::new();
        assert!(extractor.is_risk_sentence("Market risk could adversely affect our revenue"));
        assert!(extractor.is_risk_sentence("This potential exposure to currency loss is significant"));
        assert!(!extractor.is_risk_sentence("We reported revenue of $50 billion."));
    }

    #[test]
    fn test_compare_filings_new_risk() {
        let extractor = RiskFactorExtractor::new();
        let current = vec![
            RiskFactor::new(RiskCategory::Market, "AI regulation risk", Severity::High),
            RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::Medium),
        ];
        let prior = vec![
            RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::Low),
        ];
        let comp = extractor.compare_filings(&current, &prior);
        assert!(comp.new_risks.len() >= 1);
        assert_eq!(comp.total_current, 2);
        assert_eq!(comp.total_prior, 1);
    }

    #[test]
    fn test_compare_filings_removed_risk() {
        let extractor = RiskFactorExtractor::new();
        let current = vec![RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::Medium)];
        let prior = vec![
            RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::Medium),
            RiskFactor::new(RiskCategory::Legal, "Old lawsuit risk", Severity::Low),
        ];
        let comp = extractor.compare_filings(&current, &prior);
        assert!(comp.removed_risks.len() >= 1);
    }

    #[test]
    fn test_compare_filings_severity_trend() {
        let extractor = RiskFactorExtractor::new();
        let current = vec![RiskFactor::new(RiskCategory::Market, "Market risk threat loss failure", Severity::Critical)];
        let prior = vec![RiskFactor::new(RiskCategory::Market, "Minor risk", Severity::Low)];
        let comp = extractor.compare_filings(&current, &prior);
        assert!(comp.severity_trend > 0.0);
    }

    #[test]
    fn test_risk_summary() {
        let extractor = RiskFactorExtractor::new();
        let risks = vec![
            RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::High),
            RiskFactor::new(RiskCategory::Legal, "Litigation risk", Severity::Critical),
            RiskFactor::new(RiskCategory::Market, "Currency risk", Severity::Low),
        ];
        let summary = extractor.risk_summary(&risks);
        assert_eq!(summary.total, 3);
        assert_eq!(summary.critical, 1);
        assert_eq!(summary.high, 1);
        assert_eq!(summary.low, 1);
        assert!(*summary.category_counts.get(&RiskCategory::Market).unwrap_or(&0) == 2);
    }

    #[test]
    fn test_extract_from_section() {
        let extractor = RiskFactorExtractor::new();
        let section = "Market risk from interest rate changes could adversely affect us. We face cybersecurity threats that pose a material risk. Climate regulations create compliance burdens.";
        let risks = extractor.extract_from_section(section);
        assert!(risks.len() >= 2);
    }

    #[test]
    fn test_empty_text() {
        let extractor = RiskFactorExtractor::new();
        let risks = extractor.extract_risks("");
        assert!(risks.is_empty());
    }

    #[test]
    fn test_risk_factor_composite_score() {
        let rf = RiskFactor::new(RiskCategory::Market, "test", Severity::High);
        let rf_with_prob = RiskFactor {
            probability: 0.8,
            ..rf
        };
        assert!((rf_with_prob.composite_score() - 0.6).abs() < 1e-10);
    }
}
