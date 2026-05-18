//! # Full Analysis Pipeline Orchestration
//!
//! Runs complete SEC filing analysis: parse → sentiment → risk → financials
//! → insider → earnings. Supports multi-filing comparison, watchlist monitoring,
//! and report generation.

use crate::earnings::EarningsAnalyzer;
use crate::financials::FinancialExtractor;
use crate::insider::InsiderAnalyzer;
use crate::parser::FilingParser;
use crate::risk::RiskFactorExtractor;
use crate::sentiment::EarningsSentimentAnalyzer;
use crate::types::{
    AnalysisResult, AlertThreshold, ComparisonReport, FilingType, SecFiling,
};

/// A triggered alert from watchlist monitoring.
#[derive(Debug, Clone)]
pub struct Alert {
    pub company: String,
    pub metric: String,
    pub value: f64,
    pub threshold_name: String,
    pub message: String,
}

/// Watchlist configuration for monitoring companies.
#[derive(Debug, Clone, Default)]
pub struct WatchlistConfig {
    pub company: String,
    pub ticker: String,
    pub thresholds: Vec<AlertThreshold>,
}

impl WatchlistConfig {
    pub fn new(company: &str, ticker: &str) -> Self {
        Self {
            company: company.to_string(),
            ticker: ticker.to_string(),
            thresholds: Vec::new(),
        }
    }

    /// Add an alert threshold for a metric.
    pub fn with_threshold(mut self, threshold: AlertThreshold) -> Self {
        self.thresholds.push(threshold);
        self
    }
}

/// Orchestrates the complete filing analysis pipeline.
#[derive(Debug)]
pub struct AnalysisPipeline {
    parser: FilingParser,
    sentiment_analyzer: EarningsSentimentAnalyzer,
    risk_extractor: RiskFactorExtractor,
    financial_extractor: FinancialExtractor,
    insider_analyzer: InsiderAnalyzer,
    earnings_analyzer: EarningsAnalyzer,
}

impl Default for AnalysisPipeline {
    fn default() -> Self {
        Self::new()
    }
}

impl AnalysisPipeline {
    /// Create a new pipeline with default analyzers.
    pub fn new() -> Self {
        Self {
            parser: FilingParser::new(),
            sentiment_analyzer: EarningsSentimentAnalyzer::new(),
            risk_extractor: RiskFactorExtractor::new(),
            financial_extractor: FinancialExtractor::new(),
            insider_analyzer: InsiderAnalyzer::new(),
            earnings_analyzer: EarningsAnalyzer::new(),
        }
    }

    // ─── Full Filing Analysis ─────────────────────────────────────

    /// Run complete analysis on raw text: parse → sentiment → risk → financials.
    /// Returns a fully populated `AnalysisResult`.
    pub fn analyze_filing(
        &self,
        raw_text: &str,
        filing_type: FilingType,
        cik: &str,
        company_name: &str,
    ) -> AnalysisResult {
        // 1. Parse
        let _filing = self.parser.parse_filing(raw_text, filing_type, cik, company_name);
        let filing_id = format!("{}_{}", cik, filing_type);
        let mut result = AnalysisResult::new(&filing_id, company_name);

        // 2. Sentiment
        result.sentiment = self.sentiment_analyzer.analyze(raw_text);

        // 3. Risk
        result.risks = self.risk_extractor.extract_risks(raw_text);

        // 4. Financials
        let fp = self.financial_extractor.extract_full_period(raw_text, "current");
        result.financials = self.financial_extractor.compute_ratios(&fp);

        // 5. Key takeaways
        result.key_takeaways = self.generate_takeaways(&result);

        result
    }

    /// Run complete analysis on an already-parsed `SecFiling`.
    pub fn analyze_parsed_filing(&self, filing: &SecFiling) -> AnalysisResult {
        let filing_id = format!("{}_{}", filing.company_cik, filing.filing_type);
        let mut result = AnalysisResult::new(&filing_id, &filing.company_name);

        // Sentiment from all section content
        let all_text: String = filing
            .sections
            .iter()
            .map(|s| s.content.as_str())
            .collect::<Vec<_>>()
            .join("\n\n");
        let text = if all_text.is_empty() {
            filing.raw_text.clone()
        } else {
            all_text
        };

        result.sentiment = self.sentiment_analyzer.analyze(&text);
        result.risks = self.risk_extractor.extract_risks(&text);

        let fp = self.financial_extractor.extract_full_period(&text, "current");
        result.financials = self.financial_extractor.compute_ratios(&fp);

        result.key_takeaways = self.generate_takeaways(&result);

        result
    }

    // ─── Multi-Filing Comparison ──────────────────────────────────

    /// Compare metrics across multiple filings (e.g., quarter-over-quarter).
    pub fn compare_filings(&self, results: &[AnalysisResult]) -> ComparisonReport {
        if results.is_empty() {
            return ComparisonReport::new("");
        }

        let company = results[0].company.clone();
        let mut report = ComparisonReport::new(&company);

        for result in results {
            report.filing_ids.push(result.filing_id.clone());
            report.sentiment_trend.push(result.sentiment.aggregate());

            let avg_risk = if result.risks.is_empty() {
                0.0
            } else {
                result.risks.iter().map(|r| r.composite_score()).sum::<f64>()
                    / result.risks.len() as f64
            };
            report.risk_trend.push(avg_risk);

            for ratio in &result.financials {
                report
                    .financial_trends
                    .entry(ratio.ratio_name.clone())
                    .or_default()
                    .push(ratio.value);
            }
        }

        // Detect key changes between consecutive filings
        report.key_changes = self.detect_key_changes(results);

        report
    }

    /// Detect significant changes between consecutive analysis results.
    fn detect_key_changes(&self, results: &[AnalysisResult]) -> Vec<String> {
        let mut changes = Vec::new();
        if results.len() < 2 {
            return changes;
        }

        for i in 1..results.len() {
            let prev = &results[i - 1];
            let curr = &results[i];

            // Sentiment change
            let prev_sent = prev.sentiment.aggregate();
            let curr_sent = curr.sentiment.aggregate();
            let sent_change = curr_sent - prev_sent;
            if sent_change.abs() > 0.1 {
                let direction = if sent_change > 0.0 { "improved" } else { "declined" };
                changes.push(format!(
                    "Sentiment {} from {:.2} to {:.2} ({})",
                    direction,
                    prev_sent,
                    curr_sent,
                    curr.filing_id
                ));
            }

            // Risk count change
            if curr.risks.len() > prev.risks.len() + 2 {
                changes.push(format!(
                    "Risk factors increased from {} to {} ({})",
                    prev.risks.len(),
                    curr.risks.len(),
                    curr.filing_id
                ));
            }
        }

        changes
    }

    // ─── Watchlist Monitoring ─────────────────────────────────────

    /// Monitor a watchlist of companies against their analysis results.
    /// Returns alerts for any threshold breaches.
    pub fn monitor_watchlist(
        &self,
        configs: &[WatchlistConfig],
        results_map: &HashMap<String, AnalysisResult>,
    ) -> Vec<Alert> {
        let mut alerts = Vec::new();

        for config in configs {
            if let Some(result) = results_map.get(&config.company) {
                for threshold in &config.thresholds {
                    // Check sentiment
                    if threshold.metric_name == "sentiment" {
                        if let Some(min) = threshold.min_value {
                            if result.sentiment.aggregate() < min {
                                alerts.push(Alert {
                                    company: config.company.clone(),
                                    metric: "sentiment".to_string(),
                                    value: result.sentiment.aggregate(),
                                    threshold_name: threshold.metric_name.clone(),
                                    message: format!(
                                        "{}: sentiment {:.2} below threshold {:.2}",
                                        config.company,
                                        result.sentiment.aggregate(),
                                        min
                                    ),
                                });
                            }
                        }
                    }

                    // Check financial ratios
                    for ratio in &result.financials {
                        if ratio.ratio_name == threshold.metric_name {
                            if threshold.triggers(ratio.value) {
                                alerts.push(Alert {
                                    company: config.company.clone(),
                                    metric: ratio.ratio_name.clone(),
                                    value: ratio.value,
                                    threshold_name: threshold.metric_name.clone(),
                                    message: format!(
                                        "{}: {} = {:.4} outside threshold range",
                                        config.company,
                                        ratio.ratio_name,
                                        ratio.value
                                    ),
                                });
                            }
                        }
                    }
                }
            }
        }

        alerts
    }

    // ─── Report Generation ────────────────────────────────────────

    /// Generate a text summary report from analysis results.
    pub fn generate_report(&self, result: &AnalysisResult) -> String {
        let mut lines = Vec::new();

        lines.push(format!("=== Analysis Report: {} ===", result.company));
        lines.push(format!("Filing: {}", result.filing_id));
        lines.push(String::new());

        // Sentiment
        lines.push("--- Sentiment ---".to_string());
        lines.push(format!("Overall: {:.2}", result.sentiment.overall));
        lines.push(format!("Forward-Looking: {:.2}", result.sentiment.forward_looking));
        lines.push(format!("Risk Disclosures: {:.2}", result.sentiment.risk_disclosures));
        lines.push(format!("Management Tone: {:.2}", result.sentiment.management_tone));
        lines.push(String::new());

        // Risk Summary
        lines.push("--- Risk Factors ---".to_string());
        lines.push(format!("Total: {}", result.risks.len()));
        lines.push(format!("{}", result.risk_summary()));
        if !result.top_risks(3).is_empty() {
            lines.push("Top Risks:".to_string());
            for risk in result.top_risks(3) {
                lines.push(format!(
                    "  - [{}] {} (severity: {:?})",
                    risk.category,
                    &risk.description[..risk.description.len().min(80)],
                    risk.severity
                ));
            }
        }
        lines.push(String::new());

        // Financial Ratios
        lines.push("--- Financial Ratios ---".to_string());
        for ratio in &result.financials {
            let bench = ratio
                .benchmark
                .map(|b| format!(", benchmark: {:.4}", b))
                .unwrap_or_default();
            lines.push(format!("  {}: {:.4}{}", ratio.ratio_name, ratio.value, bench));
        }
        lines.push(String::new());

        // Key Takeaways
        if !result.key_takeaways.is_empty() {
            lines.push("--- Key Takeaways ---".to_string());
            for (i, takeaway) in result.key_takeaways.iter().enumerate() {
                lines.push(format!("  {}. {}", i + 1, takeaway));
            }
        }

        lines.join("\n")
    }

    // ─── Internal ─────────────────────────────────────────────────

    /// Generate key takeaways from an analysis result.
    fn generate_takeaways(&self, result: &AnalysisResult) -> Vec<String> {
        let mut takeaways = Vec::new();

        // Sentiment-based takeaways
        if result.sentiment.overall > 0.7 {
            takeaways.push("Strong positive sentiment across the filing.".to_string());
        } else if result.sentiment.overall < 0.3 {
            takeaways.push("Negative sentiment detected — investigate further.".to_string());
        }

        // Risk-based takeaways
        let critical_count = result
            .risks
            .iter()
            .filter(|r| r.severity == crate::types::Severity::Critical)
            .count();
        if critical_count > 0 {
            takeaways.push(format!(
                "{} critical risk factor(s) identified.",
                critical_count
            ));
        }

        // Financial-based takeaways
        if let Some(margin) = result
            .financials
            .iter()
            .find(|r| r.ratio_name == "gross_margin")
        {
            if margin.value > 0.5 {
                takeaways.push(format!(
                    "Healthy gross margin of {:.1}%.",
                    margin.value * 100.0
                ));
            }
        }

        if takeaways.is_empty() {
            takeaways.push("No significant findings.".to_string());
        }

        takeaways
    }
}

// Import HashMap for monitor_watchlist
use std::collections::HashMap;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{FilingType};

    fn sample_10k_text() -> &'static str {
        r#"Item 1. Business
We had record growth and strong innovation in our products.

Item 1A. Risk Factors
We face significant market risks from interest rate changes that could adversely affect our business.
Cyber security threats pose a material risk to our operations.

Item 7. Management's Discussion and Analysis
We expect continued growth. Total Revenue: $394,328,000,000
Net Income: $100,916,000,000
Operating Income: $130,000,000,000
We plan to invest in new technologies.

Item 8. Financial Statements
Total Assets: $352,583,000,000
Total Liabilities: $275,000,000,000
Stockholders' Equity: $77,583,000,000
Gross Profit: $184,328,000,000
"#
    }

    fn pipeline() -> AnalysisPipeline {
        AnalysisPipeline::new()
    }

    #[test]
    fn test_pipeline_new() {
        let _p = pipeline();
    }

    #[test]
    fn test_analyze_filing() {
        let p = pipeline();
        let result = p.analyze_filing(
            sample_10k_text(),
            FilingType::TenK,
            "0000320193",
            "Apple Inc.",
        );
        assert_eq!(result.company, "Apple Inc.");
        assert!(result.sentiment.overall > 0.0);
        assert!(!result.risks.is_empty());
        assert!(!result.financials.is_empty());
    }

    #[test]
    fn test_analyze_filing_has_financial_ratios() {
        let p = pipeline();
        let result = p.analyze_filing(
            sample_10k_text(),
            FilingType::TenK,
            "CIK",
            "TestCo",
        );
        let names: Vec<&str> = result.financials.iter().map(|r| r.ratio_name.as_str()).collect();
        assert!(names.contains(&"gross_margin"));
    }

    #[test]
    fn test_analyze_filing_has_takeaways() {
        let p = pipeline();
        let result = p.analyze_filing(
            sample_10k_text(),
            FilingType::TenK,
            "CIK",
            "TestCo",
        );
        assert!(!result.key_takeaways.is_empty());
    }

    #[test]
    fn test_analyze_parsed_filing() {
        let p = pipeline();
        let filing =
            SecFiling::new(FilingType::TenK, "CIK", "TestCo", sample_10k_text());
        let result = p.analyze_parsed_filing(&filing);
        assert_eq!(result.company, "TestCo");
        assert!(result.sentiment.overall > 0.0);
    }

    #[test]
    fn test_compare_filings() {
        let p = pipeline();
        let r1 = p.analyze_filing(sample_10k_text(), FilingType::TenK, "CIK", "Co");
        let r2 = p.analyze_filing(sample_10k_text(), FilingType::TenQ, "CIK", "Co");
        let report = p.compare_filings(&[r1, r2]);
        assert_eq!(report.company, "Co");
        assert_eq!(report.filing_ids.len(), 2);
        assert_eq!(report.sentiment_trend.len(), 2);
    }

    #[test]
    fn test_compare_filings_empty() {
        let p = pipeline();
        let report = p.compare_filings(&[]);
        assert_eq!(report.company, "");
    }

    #[test]
    fn test_monitor_watchlist_no_alerts() {
        let p = pipeline();
        let result = p.analyze_filing(sample_10k_text(), FilingType::TenK, "CIK", "Apple Inc.");
        let config = WatchlistConfig::new("Apple Inc.", "AAPL");
        let mut map = HashMap::new();
        map.insert("Apple Inc.".to_string(), result);
        let alerts = p.monitor_watchlist(&[config], &map);
        // No thresholds configured, so no alerts
        assert!(alerts.is_empty());
    }

    #[test]
    fn test_monitor_watchlist_with_threshold() {
        let p = pipeline();
        let result = p.analyze_filing(sample_10k_text(), FilingType::TenK, "CIK", "Apple Inc.");
        let config = WatchlistConfig::new("Apple Inc.", "AAPL")
            .with_threshold(AlertThreshold::new("sentiment"));
        let mut map = HashMap::new();
        map.insert("Apple Inc.".to_string(), result);
        let alerts = p.monitor_watchlist(&[config], &map);
        // sentiment threshold with no min_value won't trigger
        assert!(alerts.is_empty());
    }

    #[test]
    fn test_generate_report() {
        let p = pipeline();
        let result = p.analyze_filing(
            sample_10k_text(),
            FilingType::TenK,
            "CIK",
            "Apple Inc.",
        );
        let report = p.generate_report(&result);
        assert!(report.contains("Apple Inc."));
        assert!(report.contains("Sentiment"));
        assert!(report.contains("Risk Factors"));
    }

    #[test]
    fn test_watchlist_config_new() {
        let config = WatchlistConfig::new("Apple Inc.", "AAPL");
        assert_eq!(config.company, "Apple Inc.");
        assert_eq!(config.ticker, "AAPL");
        assert!(config.thresholds.is_empty());
    }

    #[test]
    fn test_watchlist_config_with_threshold() {
        let config = WatchlistConfig::new("Co", "T")
            .with_threshold(AlertThreshold::with_range("EPS", 1.0, 5.0));
        assert_eq!(config.thresholds.len(), 1);
    }
}
