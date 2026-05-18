//! # SEC Earnings Workbench — Core Types
//!
//! Defines all data structures used throughout the SEC filing and earnings
//! analysis pipeline: filing metadata, financial figures, sentiment scores,
//! risk factors, insider trades, and analysis results.

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

/// SEC filing type enumeration.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FilingType {
    TenK,
    TenQ,
    EightK,
    Proxy,
    Schedule13D,
    Schedule13G,
    SC13G,
    Form4,
}

impl FilingType {
    /// Return the human-readable SEC form name.
    pub fn form_name(&self) -> &'static str {
        match self {
            FilingType::TenK => "10-K",
            FilingType::TenQ => "10-Q",
            FilingType::EightK => "8-K",
            FilingType::Proxy => "DEF 14A",
            FilingType::Schedule13D => "SC 13D",
            FilingType::Schedule13G => "SC 13G",
            FilingType::SC13G => "SC 13G/A",
            FilingType::Form4 => "Form 4",
        }
    }

    /// Return true if this filing type is an annual report.
    pub fn is_annual(&self) -> bool {
        matches!(self, FilingType::TenK)
    }

    /// Return true if this filing type is a quarterly report.
    pub fn is_quarterly(&self) -> bool {
        matches!(self, FilingType::TenQ)
    }

    /// Parse from a string form number.
    pub fn from_str_loose(s: &str) -> Option<Self> {
        let s = s.trim().to_uppercase();
        match s.as_str() {
            "10-K" | "10K" | "FORM 10-K" => Some(FilingType::TenK),
            "10-Q" | "10Q" | "FORM 10-Q" => Some(FilingType::TenQ),
            "8-K" | "8K" | "FORM 8-K" => Some(FilingType::EightK),
            "DEF 14A" | "PROXY" | "DEF14A" => Some(FilingType::Proxy),
            "SC 13D" | "SCHEDULE 13D" | "SC13D" => Some(FilingType::Schedule13D),
            "SC 13G" | "SCHEDULE 13G" | "SC13G" => Some(FilingType::Schedule13G),
            "SC 13G/A" | "SC13G/A" => Some(FilingType::SC13G),
            "FORM 4" | "FORM4" | "4" => Some(FilingType::Form4),
            _ => None,
        }
    }
}

impl std::fmt::Display for FilingType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.form_name())
    }
}

/// A parsed section within an SEC filing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FilingSection {
    pub section_name: String,
    pub content: String,
    pub page_range: Option<(usize, usize)>,
}

impl FilingSection {
    pub fn new(name: &str, content: &str) -> Self {
        Self {
            section_name: name.to_string(),
            content: content.to_string(),
            page_range: None,
        }
    }

    pub fn with_pages(name: &str, content: &str, start: usize, end: usize) -> Self {
        Self {
            section_name: name.to_string(),
            content: content.to_string(),
            page_range: Some((start, end)),
        }
    }

    /// Number of characters in the section content.
    pub fn char_count(&self) -> usize {
        self.content.len()
    }

    /// Word count approximation.
    pub fn word_count(&self) -> usize {
        self.content.split_whitespace().count()
    }
}

/// Represents a parsed SEC filing document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecFiling {
    pub filing_type: FilingType,
    pub company_cik: String,
    pub company_name: String,
    pub filed_date: Option<NaiveDate>,
    pub accepted_date: Option<NaiveDate>,
    pub period_of_report: Option<NaiveDate>,
    pub document_url: Option<String>,
    pub raw_text: String,
    pub sections: Vec<FilingSection>,
}

impl SecFiling {
    /// Create a minimal filing with required fields.
    pub fn new(filing_type: FilingType, cik: &str, company_name: &str, raw_text: &str) -> Self {
        Self {
            filing_type,
            company_cik: cik.to_string(),
            company_name: company_name.to_string(),
            filed_date: None,
            accepted_date: None,
            period_of_report: None,
            document_url: None,
            raw_text: raw_text.to_string(),
            sections: Vec::new(),
        }
    }

    /// Get a section by name (case-insensitive partial match).
    pub fn get_section(&self, name: &str) -> Option<&FilingSection> {
        let name_lower = name.to_lowercase();
        self.sections
            .iter()
            .find(|s| s.section_name.to_lowercase().contains(&name_lower))
    }

    /// Get section content by name.
    pub fn section_content(&self, name: &str) -> Option<&str> {
        self.get_section(name).map(|s| s.content.as_str())
    }

    /// Total word count across all sections.
    pub fn total_word_count(&self) -> usize {
        self.sections.iter().map(|s| s.word_count()).sum()
    }
}

/// A structured earnings report.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarningsReport {
    pub company: String,
    pub ticker: String,
    pub fiscal_quarter: u8,
    pub fiscal_year: u32,
    pub report_date: Option<NaiveDate>,
    pub revenue: Option<f64>,
    pub earnings_per_share: Option<f64>,
    pub net_income: Option<f64>,
    pub operating_income: Option<f64>,
    pub ebitda: Option<f64>,
    pub guidance: Option<String>,
}

impl EarningsReport {
    pub fn new(company: &str, ticker: &str, quarter: u8, year: u32) -> Self {
        Self {
            company: company.to_string(),
            ticker: ticker.to_string(),
            fiscal_quarter: quarter,
            fiscal_year: year,
            report_date: None,
            revenue: None,
            earnings_per_share: None,
            net_income: None,
            operating_income: None,
            ebitda: None,
            guidance: None,
        }
    }

    /// Compute gross margin from revenue and net income if available.
    pub fn net_margin(&self) -> Option<f64> {
        match (self.revenue, self.net_income) {
            (Some(rev), Some(ni)) if rev.abs() > f64::EPSILON => Some(ni / rev),
            _ => None,
        }
    }
}

/// Direction of earnings surprise.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BeatMiss {
    Beat,
    Miss,
    Meet,
}

impl std::fmt::Display for BeatMiss {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BeatMiss::Beat => write!(f, "Beat"),
            BeatMiss::Miss => write!(f, "Miss"),
            BeatMiss::Meet => write!(f, "Meet"),
        }
    }
}

/// Earnings surprise metric.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarningsSurprise {
    pub metric: String,
    pub expected: f64,
    pub actual: f64,
    pub surprise_pct: f64,
    pub beat_miss: BeatMiss,
}

impl EarningsSurprise {
    pub fn new(metric: &str, expected: f64, actual: f64) -> Self {
        let surprise_pct = if expected.abs() > f64::EPSILON {
            (actual - expected) / expected.abs() * 100.0
        } else {
            0.0
        };
        let beat_miss = if (surprise_pct - 0.5).abs() <= 0.5 {
            BeatMiss::Meet
        } else if surprise_pct > 0.0 {
            BeatMiss::Beat
        } else {
            BeatMiss::Miss
        };
        Self {
            metric: metric.to_string(),
            expected,
            actual,
            surprise_pct,
            beat_miss,
        }
    }
}

/// Financial sentiment analysis result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SentimentScore {
    pub overall: f64,
    pub forward_looking: f64,
    pub risk_disclosures: f64,
    pub management_tone: f64,
    pub sector_context: Option<f64>,
}

impl SentimentScore {
    /// Create a neutral sentiment score.
    pub fn neutral() -> Self {
        Self {
            overall: 0.5,
            forward_looking: 0.5,
            risk_disclosures: 0.5,
            management_tone: 0.5,
            sector_context: None,
        }
    }

    /// Create a sentiment score from a simple overall value.
    pub fn from_overall(overall: f64) -> Self {
        Self {
            overall: overall.clamp(0.0, 1.0),
            forward_looking: overall.clamp(0.0, 1.0),
            risk_disclosures: (1.0 - overall).clamp(0.0, 1.0),
            management_tone: overall.clamp(0.0, 1.0),
            sector_context: None,
        }
    }

    /// Weighted aggregate of all available sentiment dimensions.
    pub fn aggregate(&self) -> f64 {
        let mut total_weight = 0.0;
        let mut weighted_sum = 0.0;
        let pairs: &[(&str, f64, f64)] = &[
            ("overall", 0.3, self.overall),
            ("forward_looking", 0.2, self.forward_looking),
            ("risk_disclosures", 0.2, self.risk_disclosures),
            ("management_tone", 0.2, self.management_tone),
        ];
        for (_, w, v) in pairs {
            total_weight += w;
            weighted_sum += w * v;
        }
        if let Some(sc) = self.sector_context {
            total_weight += 0.1;
            weighted_sum += 0.1 * sc;
        }
        if total_weight > 0.0 {
            weighted_sum / total_weight
        } else {
            0.5
        }
    }
}

/// Risk factor category.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RiskCategory {
    Market,
    Operational,
    Regulatory,
    Financial,
    Strategic,
    Legal,
    Environmental,
    Other,
}

impl RiskCategory {
    pub fn label(&self) -> &'static str {
        match self {
            RiskCategory::Market => "Market Risk",
            RiskCategory::Operational => "Operational Risk",
            RiskCategory::Regulatory => "Regulatory Risk",
            RiskCategory::Financial => "Financial Risk",
            RiskCategory::Strategic => "Strategic Risk",
            RiskCategory::Legal => "Legal Risk",
            RiskCategory::Environmental => "Environmental Risk",
            RiskCategory::Other => "Other Risk",
        }
    }

    /// Classify risk text into a category based on keyword presence.
    pub fn classify(text: &str) -> Self {
        let lower = text.to_lowercase();
        if lower.contains("regulation") || lower.contains("compliance") || lower.contains("legal") {
            RiskCategory::Regulatory
        } else if lower.contains("litigation") || lower.contains("lawsuit") {
            RiskCategory::Legal
        } else if lower.contains("climate") || lower.contains("environment") {
            RiskCategory::Environmental
        } else if lower.contains("market") || lower.contains("interest rate") || lower.contains("currency") {
            RiskCategory::Market
        } else if lower.contains("operat") || lower.contains("cyber") || lower.contains("supply chain") {
            RiskCategory::Operational
        } else if lower.contains("debt") || lower.contains("liquidity") || lower.contains("credit") {
            RiskCategory::Financial
        } else if lower.contains("competition") || lower.contains("strategic") {
            RiskCategory::Strategic
        } else {
            RiskCategory::Other
        }
    }
}

impl std::fmt::Display for RiskCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.label())
    }
}

/// Risk severity level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

impl Severity {
    /// Score on a 0-1 scale.
    pub fn score(&self) -> f64 {
        match self {
            Severity::Low => 0.25,
            Severity::Medium => 0.50,
            Severity::High => 0.75,
            Severity::Critical => 1.0,
        }
    }

    /// Determine severity from a numeric score (0.0 – 1.0).
    pub fn from_score(score: f64) -> Self {
        if score >= 0.85 {
            Severity::Critical
        } else if score >= 0.60 {
            Severity::High
        } else if score >= 0.35 {
            Severity::Medium
        } else {
            Severity::Low
        }
    }
}

/// A risk factor extracted from a filing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskFactor {
    pub category: RiskCategory,
    pub description: String,
    pub severity: Severity,
    pub probability: f64,
    pub financial_impact: Option<f64>,
}

impl RiskFactor {
    pub fn new(category: RiskCategory, description: &str, severity: Severity) -> Self {
        Self {
            category,
            description: description.to_string(),
            severity,
            probability: 0.5,
            financial_impact: None,
        }
    }

    /// Compute a composite risk score (severity × probability).
    pub fn composite_score(&self) -> f64 {
        self.severity.score() * self.probability
    }
}

/// Insider transaction type.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TransactionType {
    Purchase,
    Sale,
    OptionExercise,
    Gift,
    Other,
}

impl std::fmt::Display for TransactionType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TransactionType::Purchase => write!(f, "Purchase"),
            TransactionType::Sale => write!(f, "Sale"),
            TransactionType::OptionExercise => write!(f, "Option Exercise"),
            TransactionType::Gift => write!(f, "Gift"),
            TransactionType::Other => write!(f, "Other"),
        }
    }
}

impl TransactionType {
    /// Classify from SEC Form 4 transaction code.
    pub fn from_code(code: &str) -> Self {
        match code.trim().to_uppercase().as_str() {
            "P" => TransactionType::Purchase,
            "S" => TransactionType::Sale,
            "M" => TransactionType::OptionExercise,
            "G" => TransactionType::Gift,
            _ => TransactionType::Other,
        }
    }

    /// Return true if this is a buying activity.
    pub fn is_buy(&self) -> bool {
        matches!(self, TransactionType::Purchase | TransactionType::OptionExercise)
    }

    /// Return true if this is a selling activity.
    pub fn is_sell(&self) -> bool {
        matches!(self, TransactionType::Sale)
    }
}

/// An insider trade record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InsiderTrade {
    pub insider_name: String,
    pub title: String,
    pub transaction_type: TransactionType,
    pub shares: f64,
    pub price: f64,
    pub total_value: f64,
    pub date: Option<NaiveDate>,
}

impl InsiderTrade {
    pub fn new(name: &str, title: &str, txn_type: TransactionType, shares: f64, price: f64) -> Self {
        Self {
            insider_name: name.to_string(),
            title: title.to_string(),
            transaction_type: txn_type,
            shares,
            price,
            total_value: shares * price,
            date: None,
        }
    }

    /// Net shares impact (positive for buys, negative for sells).
    pub fn net_shares(&self) -> f64 {
        if self.transaction_type.is_buy() {
            self.shares
        } else if self.transaction_type.is_sell() {
            -self.shares
        } else {
            0.0
        }
    }
}

/// Trend direction for a financial ratio.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Trend {
    Improving,
    Stable,
    Declining,
    Unknown,
}

impl Trend {
    /// Determine trend from a sequence of values.
    pub fn from_values(values: &[f64]) -> Self {
        if values.len() < 2 {
            return Trend::Unknown;
        }
        let recent = values[values.len() - 1];
        let earlier = values[values.len() - 2];
        let change_pct = if earlier.abs() > f64::EPSILON {
            (recent - earlier) / earlier.abs() * 100.0
        } else {
            0.0
        };
        if change_pct > 2.0 {
            Trend::Improving
        } else if change_pct < -2.0 {
            Trend::Declining
        } else {
            Trend::Stable
        }
    }
}

/// A computed financial ratio with benchmark comparison.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinancialRatio {
    pub ratio_name: String,
    pub value: f64,
    pub benchmark: Option<f64>,
    pub percentile: Option<f64>,
    pub trend: Trend,
}

impl FinancialRatio {
    pub fn new(name: &str, value: f64) -> Self {
        Self {
            ratio_name: name.to_string(),
            value,
            benchmark: None,
            percentile: None,
            trend: Trend::Unknown,
        }
    }

    pub fn with_benchmark(name: &str, value: f64, benchmark: f64) -> Self {
        Self {
            ratio_name: name.to_string(),
            value,
            benchmark: Some(benchmark),
            percentile: None,
            trend: Trend::Unknown,
        }
    }

    /// How the value compares to benchmark (positive = above, negative = below).
    pub fn vs_benchmark(&self) -> Option<f64> {
        self.benchmark.map(|b| self.value - b)
    }
}

/// Complete analysis result for an SEC filing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisResult {
    pub filing_id: String,
    pub company: String,
    pub sentiment: SentimentScore,
    pub risks: Vec<RiskFactor>,
    pub financials: Vec<FinancialRatio>,
    pub insider_trades: Vec<InsiderTrade>,
    pub key_takeaways: Vec<String>,
}

impl AnalysisResult {
    pub fn new(filing_id: &str, company: &str) -> Self {
        Self {
            filing_id: filing_id.to_string(),
            company: company.to_string(),
            sentiment: SentimentScore::neutral(),
            risks: Vec::new(),
            financials: Vec::new(),
            insider_trades: Vec::new(),
            key_takeaways: Vec::new(),
        }
    }

    /// Top N risk factors sorted by composite score descending.
    pub fn top_risks(&self, n: usize) -> Vec<&RiskFactor> {
        let mut sorted: Vec<_> = self.risks.iter().collect();
        sorted.sort_by(|a, b| b.composite_score().partial_cmp(&a.composite_score()).unwrap());
        sorted.into_iter().take(n).collect()
    }

    /// Summary: number of risk factors by severity.
    pub fn risk_summary(&self) -> String {
        let mut counts = std::collections::HashMap::new();
        for r in &self.risks {
            *counts.entry(format!("{:?}", r.severity)).or_insert(0usize) += 1;
        }
        let parts: Vec<String> = counts.into_iter().map(|(k, v)| format!("{}: {}", k, v)).collect();
        parts.join(", ")
    }
}

/// Management tone classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ManagementTone {
    Optimistic,
    Cautious,
    Neutral,
}

impl ManagementTone {
    pub fn label(&self) -> &'static str {
        match self {
            ManagementTone::Optimistic => "Optimistic",
            ManagementTone::Cautious => "Cautious",
            ManagementTone::Neutral => "Neutral",
        }
    }

    /// Map from sentiment score to tone.
    pub fn from_score(score: f64) -> Self {
        if score >= 0.65 {
            ManagementTone::Optimistic
        } else if score <= 0.35 {
            ManagementTone::Cautious
        } else {
            ManagementTone::Neutral
        }
    }
}

impl std::fmt::Display for ManagementTone {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.label())
    }
}

/// Guidance type for earnings guidance tracking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum GuidanceType {
    Initial,
    Revised,
    Actual,
}

impl std::fmt::Display for GuidanceType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            GuidanceType::Initial => write!(f, "Initial"),
            GuidanceType::Revised => write!(f, "Revised"),
            GuidanceType::Actual => write!(f, "Actual"),
        }
    }
}

/// A tracked guidance item.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuidanceItem {
    pub metric: String,
    pub value: f64,
    pub guidance_type: GuidanceType,
    pub date: Option<NaiveDate>,
}

impl GuidanceItem {
    pub fn new(metric: &str, value: f64, guidance_type: GuidanceType) -> Self {
        Self {
            metric: metric.to_string(),
            value,
            guidance_type,
            date: None,
        }
    }
}

/// Alert threshold configuration for watchlist monitoring.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertThreshold {
    pub metric_name: String,
    pub min_value: Option<f64>,
    pub max_value: Option<f64>,
    pub alert_on_direction: Option<BeatMiss>,
}

impl AlertThreshold {
    pub fn new(metric_name: &str) -> Self {
        Self {
            metric_name: metric_name.to_string(),
            min_value: None,
            max_value: None,
            alert_on_direction: None,
        }
    }

    pub fn with_range(metric_name: &str, min: f64, max: f64) -> Self {
        Self {
            metric_name: metric_name.to_string(),
            min_value: Some(min),
            max_value: Some(max),
            alert_on_direction: None,
        }
    }

    /// Check if a value triggers this alert.
    pub fn triggers(&self, value: f64) -> bool {
        if let Some(min) = self.min_value {
            if value < min {
                return true;
            }
        }
        if let Some(max) = self.max_value {
            if value > max {
                return true;
            }
        }
        false
    }
}

/// Comparison report between multiple filings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComparisonReport {
    pub company: String,
    pub filing_ids: Vec<String>,
    pub sentiment_trend: Vec<f64>,
    pub risk_trend: Vec<f64>,
    pub financial_trends: std::collections::HashMap<String, Vec<f64>>,
    pub key_changes: Vec<String>,
}

impl ComparisonReport {
    pub fn new(company: &str) -> Self {
        Self {
            company: company.to_string(),
            filing_ids: Vec::new(),
            sentiment_trend: Vec::new(),
            risk_trend: Vec::new(),
            financial_trends: std::collections::HashMap::new(),
            key_changes: Vec::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filing_type_form_name() {
        assert_eq!(FilingType::TenK.form_name(), "10-K");
        assert_eq!(FilingType::TenQ.form_name(), "10-Q");
        assert_eq!(FilingType::EightK.form_name(), "8-K");
        assert_eq!(FilingType::Form4.form_name(), "Form 4");
    }

    #[test]
    fn test_filing_type_is_annual() {
        assert!(FilingType::TenK.is_annual());
        assert!(!FilingType::TenQ.is_annual());
        assert!(!FilingType::EightK.is_annual());
    }

    #[test]
    fn test_filing_type_is_quarterly() {
        assert!(FilingType::TenQ.is_quarterly());
        assert!(!FilingType::TenK.is_quarterly());
    }

    #[test]
    fn test_filing_type_from_str_loose() {
        assert_eq!(FilingType::from_str_loose("10-K"), Some(FilingType::TenK));
        assert_eq!(FilingType::from_str_loose("10K"), Some(FilingType::TenK));
        assert_eq!(FilingType::from_str_loose("FORM 10-Q"), Some(FilingType::TenQ));
        assert_eq!(FilingType::from_str_loose("8-K"), Some(FilingType::EightK));
        assert_eq!(FilingType::from_str_loose("FORM 4"), Some(FilingType::Form4));
        assert_eq!(FilingType::from_str_loose("SC 13D"), Some(FilingType::Schedule13D));
        assert_eq!(FilingType::from_str_loose("DEF 14A"), Some(FilingType::Proxy));
        assert_eq!(FilingType::from_str_loose("UNKNOWN"), None);
    }

    #[test]
    fn test_filing_type_display() {
        assert_eq!(format!("{}", FilingType::TenK), "10-K");
        assert_eq!(format!("{}", FilingType::Form4), "Form 4");
    }

    #[test]
    fn test_filing_section_new() {
        let sec = FilingSection::new("Risk Factors", "We face many risks.");
        assert_eq!(sec.section_name, "Risk Factors");
        assert_eq!(sec.content, "We face many risks.");
        assert!(sec.page_range.is_none());
    }

    #[test]
    fn test_filing_section_with_pages() {
        let sec = FilingSection::with_pages("MD&A", "Content here", 10, 25);
        assert_eq!(sec.page_range, Some((10, 25)));
    }

    #[test]
    fn test_filing_section_word_count() {
        let sec = FilingSection::new("Test", "one two three four five");
        assert_eq!(sec.word_count(), 5);
    }

    #[test]
    fn test_sec_filing_new() {
        let filing = SecFiling::new(FilingType::TenK, "0000320193", "Apple Inc.", "Annual report text");
        assert_eq!(filing.company_cik, "0000320193");
        assert_eq!(filing.company_name, "Apple Inc.");
        assert!(filing.sections.is_empty());
    }

    #[test]
    fn test_sec_filing_get_section() {
        let mut filing = SecFiling::new(FilingType::TenK, "CIK", "Co", "text");
        filing.sections.push(FilingSection::new("Risk Factors", "risk content"));
        filing.sections.push(FilingSection::new("Business", "biz content"));
        assert!(filing.get_section("risk").is_some());
        assert!(filing.get_section("RISK").is_some());
        assert!(filing.get_section("nonexistent").is_none());
    }

    #[test]
    fn test_sec_filing_total_word_count() {
        let mut filing = SecFiling::new(FilingType::TenK, "CIK", "Co", "text");
        filing.sections.push(FilingSection::new("A", "one two"));
        filing.sections.push(FilingSection::new("B", "three four five"));
        assert_eq!(filing.total_word_count(), 5);
    }

    #[test]
    fn test_earnings_report_new() {
        let er = EarningsReport::new("Apple Inc.", "AAPL", 1, 2024);
        assert_eq!(er.ticker, "AAPL");
        assert_eq!(er.fiscal_quarter, 1);
        assert!(er.revenue.is_none());
    }

    #[test]
    fn test_earnings_report_net_margin() {
        let mut er = EarningsReport::new("Co", "T", 1, 2024);
        assert!(er.net_margin().is_none());
        er.revenue = Some(1_000_000.0);
        er.net_income = Some(100_000.0);
        assert!((er.net_margin().unwrap() - 0.1).abs() < 1e-10);
    }

    #[test]
    fn test_earnings_surprise_new() {
        let es = EarningsSurprise::new("EPS", 2.50, 2.80);
        assert!(es.surprise_pct > 0.0);
        assert_eq!(es.beat_miss, BeatMiss::Beat);
    }

    #[test]
    fn test_earnings_surprise_miss() {
        let es = EarningsSurprise::new("Revenue", 10_000.0, 9_500.0);
        assert!(es.surprise_pct < 0.0);
        assert_eq!(es.beat_miss, BeatMiss::Miss);
    }

    #[test]
    fn test_earnings_surprise_meet() {
        let es = EarningsSurprise::new("EPS", 2.00, 2.00);
        assert_eq!(es.beat_miss, BeatMiss::Meet);
    }

    #[test]
    fn test_sentiment_score_neutral() {
        let s = SentimentScore::neutral();
        assert!((s.overall - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_sentiment_score_from_overall() {
        let s = SentimentScore::from_overall(0.8);
        assert!((s.overall - 0.8).abs() < 1e-10);
        assert!((s.risk_disclosures - 0.2).abs() < 1e-10);
    }

    #[test]
    fn test_sentiment_score_aggregate() {
        let s = SentimentScore::from_overall(0.7);
        let agg = s.aggregate();
        assert!(agg > 0.0 && agg <= 1.0);
    }

    #[test]
    fn test_risk_category_classify() {
        assert_eq!(RiskCategory::classify("market risk from interest rates"), RiskCategory::Market);
        assert_eq!(RiskCategory::classify("regulatory compliance burden"), RiskCategory::Regulatory);
        assert_eq!(RiskCategory::classify("climate change exposure"), RiskCategory::Environmental);
        assert_eq!(RiskCategory::classify("operational cybersecurity threats"), RiskCategory::Operational);
    }

    #[test]
    fn test_risk_category_label() {
        assert_eq!(RiskCategory::Market.label(), "Market Risk");
        assert_eq!(RiskCategory::Legal.label(), "Legal Risk");
    }

    #[test]
    fn test_severity_score() {
        assert!((Severity::Low.score() - 0.25).abs() < 1e-10);
        assert!((Severity::Critical.score() - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_severity_from_score() {
        assert_eq!(Severity::from_score(0.1), Severity::Low);
        assert_eq!(Severity::from_score(0.5), Severity::Medium);
        assert_eq!(Severity::from_score(0.7), Severity::High);
        assert_eq!(Severity::from_score(0.9), Severity::Critical);
    }

    #[test]
    fn test_risk_factor_composite_score() {
        let rf = RiskFactor::new(RiskCategory::Market, "Interest rate risk", Severity::High);
        assert!((rf.composite_score() - 0.375).abs() < 1e-10); // 0.75 * 0.5
    }

    #[test]
    fn test_transaction_type_from_code() {
        assert_eq!(TransactionType::from_code("P"), TransactionType::Purchase);
        assert_eq!(TransactionType::from_code("S"), TransactionType::Sale);
        assert_eq!(TransactionType::from_code("M"), TransactionType::OptionExercise);
        assert_eq!(TransactionType::from_code("G"), TransactionType::Gift);
        assert_eq!(TransactionType::from_code("X"), TransactionType::Other);
    }

    #[test]
    fn test_transaction_type_buy_sell() {
        assert!(TransactionType::Purchase.is_buy());
        assert!(TransactionType::OptionExercise.is_buy());
        assert!(TransactionType::Sale.is_sell());
        assert!(!TransactionType::Gift.is_buy());
        assert!(!TransactionType::Gift.is_sell());
    }

    #[test]
    fn test_insider_trade_new() {
        let t = InsiderTrade::new("John Doe", "CEO", TransactionType::Purchase, 1000.0, 150.0);
        assert!((t.total_value - 150_000.0).abs() < 1e-6);
        assert!((t.net_shares() - 1000.0).abs() < 1e-6);
    }

    #[test]
    fn test_insider_trade_net_shares_sell() {
        let t = InsiderTrade::new("Jane Smith", "CFO", TransactionType::Sale, 500.0, 200.0);
        assert!((t.net_shares() - (-500.0)).abs() < 1e-6);
    }

    #[test]
    fn test_trend_from_values() {
        assert_eq!(Trend::from_values(&[1.0, 1.1]), Trend::Improving);
        assert_eq!(Trend::from_values(&[1.0, 0.9]), Trend::Declining);
        assert_eq!(Trend::from_values(&[1.0, 1.0]), Trend::Stable);
        assert_eq!(Trend::from_values(&[1.0]), Trend::Unknown);
        assert_eq!(Trend::from_values(&[]), Trend::Unknown);
    }

    #[test]
    fn test_financial_ratio_new() {
        let r = FinancialRatio::new("ROE", 0.15);
        assert_eq!(r.ratio_name, "ROE");
        assert!((r.value - 0.15).abs() < 1e-10);
        assert!(r.vs_benchmark().is_none());
    }

    #[test]
    fn test_financial_ratio_with_benchmark() {
        let r = FinancialRatio::with_benchmark("P/E", 25.0, 20.0);
        assert!((r.vs_benchmark().unwrap() - 5.0).abs() < 1e-10);
    }

    #[test]
    fn test_analysis_result_new() {
        let ar = AnalysisResult::new("F123", "Apple");
        assert!(ar.risks.is_empty());
        assert!((ar.sentiment.overall - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_analysis_result_top_risks() {
        let mut ar = AnalysisResult::new("F1", "Co");
        ar.risks.push(RiskFactor::new(RiskCategory::Market, "Low risk", Severity::Low));
        ar.risks.push(RiskFactor::new(RiskCategory::Financial, "High risk", Severity::Critical));
        let top = ar.top_risks(1);
        assert_eq!(top.len(), 1);
        assert_eq!(top[0].severity, Severity::Critical);
    }

    #[test]
    fn test_management_tone_from_score() {
        assert_eq!(ManagementTone::from_score(0.8), ManagementTone::Optimistic);
        assert_eq!(ManagementTone::from_score(0.2), ManagementTone::Cautious);
        assert_eq!(ManagementTone::from_score(0.5), ManagementTone::Neutral);
    }

    #[test]
    fn test_alert_threshold_triggers() {
        let at = AlertThreshold::with_range("EPS", 1.0, 5.0);
        assert!(!at.triggers(2.5));
        assert!(at.triggers(0.5));
        assert!(at.triggers(6.0));
    }

    #[test]
    fn test_beat_miss_display() {
        assert_eq!(format!("{}", BeatMiss::Beat), "Beat");
        assert_eq!(format!("{}", BeatMiss::Miss), "Miss");
        assert_eq!(format!("{}", BeatMiss::Meet), "Meet");
    }

    #[test]
    fn test_serde_round_trip_filing_type() {
        let ft = FilingType::TenK;
        let json = serde_json::to_string(&ft).unwrap();
        let back: FilingType = serde_json::from_str(&json).unwrap();
        assert_eq!(ft, back);
    }

    #[test]
    fn test_serde_round_trip_earnings_surprise() {
        let es = EarningsSurprise::new("EPS", 2.0, 2.5);
        let json = serde_json::to_string(&es).unwrap();
        let back: EarningsSurprise = serde_json::from_str(&json).unwrap();
        assert!((back.surprise_pct - es.surprise_pct).abs() < 1e-10);
    }
}
