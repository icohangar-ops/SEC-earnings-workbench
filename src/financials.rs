//! # Financial Data Extraction & Ratio Computation
//!
//! Extracts income statement, balance sheet, and cash flow items from SEC filing
//! text using regex patterns, then computes key financial ratios and tracks trends
//! across multiple periods.

use crate::types::{FinancialRatio, Trend};
use regex::Regex;

/// A single period's extracted financial data.
#[derive(Debug, Clone, Default)]
pub struct FinancialPeriod {
    pub period_label: String,
    pub revenue: Option<f64>,
    pub cogs: Option<f64>,
    pub gross_profit: Option<f64>,
    pub operating_income: Option<f64>,
    pub net_income: Option<f64>,
    pub total_assets: Option<f64>,
    pub total_liabilities: Option<f64>,
    pub equity: Option<f64>,
    pub current_assets: Option<f64>,
    pub current_liabilities: Option<f64>,
    pub cash: Option<f64>,
    pub debt: Option<f64>,
    pub operating_cf: Option<f64>,
    pub investing_cf: Option<f64>,
    pub financing_cf: Option<f64>,
}

impl FinancialPeriod {
    pub fn new(label: &str) -> Self {
        Self {
            period_label: label.to_string(),
            ..Default::default()
        }
    }
}

/// Extracts financial figures from raw text and computes ratios.
#[derive(Debug)]
pub struct FinancialExtractor {
    revenue_re: Regex,
    cogs_re: Regex,
    gross_profit_re: Regex,
    operating_income_re: Regex,
    net_income_re: Regex,
    total_assets_re: Regex,
    total_liabilities_re: Regex,
    equity_re: Regex,
    cash_re: Regex,
    debt_re: Regex,
    current_assets_re: Regex,
    current_liabilities_re: Regex,
    operating_cf_re: Regex,
    investing_cf_re: Regex,
    financing_cf_re: Regex,
    number_re: Regex,
}

impl Default for FinancialExtractor {
    fn default() -> Self {
        Self::new()
    }
}

impl FinancialExtractor {
    /// Create a new extractor with compiled regex patterns.
    pub fn new() -> Self {
        Self {
            revenue_re: Regex::new(
                r"(?i)(?:total\s+)?revenue[s]?\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            cogs_re: Regex::new(
                r"(?i)cost\s+of\s+(?:goods\s+sold|revenue|sales)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            gross_profit_re: Regex::new(
                r"(?i)gross\s+(?:profit|margin|income)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            operating_income_re: Regex::new(
                r"(?i)operating\s+income\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            net_income_re: Regex::new(
                r"(?i)net\s+(?:income|loss|earnings)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            total_assets_re: Regex::new(
                r"(?i)total\s+assets?\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            total_liabilities_re: Regex::new(
                r"(?i)total\s+liabilit(?:y|ies)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            equity_re: Regex::new(
                r"(?i)(?:total\s+)?(?:stockholders?'?|shareholders?'?)\s+(?:equity|deficit)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            cash_re: Regex::new(
                r"(?i)(?:cash\s+and\s+cash\s+equivalents?|cash(?:\s+equivalents?)?)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            debt_re: Regex::new(
                r"(?i)(?:long[\s-]term\s+debt|short[\s-]term\s+debt|total\s+debt)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            current_assets_re: Regex::new(
                r"(?i)total\s+current\s+assets?\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            current_liabilities_re: Regex::new(
                r"(?i)total\s+current\s+liabilit(?:y|ies)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            operating_cf_re: Regex::new(
                r"(?i)(?:net\s+)?cash\s+(?:provided\s+by|used\s+in)\s+operating\s+activities\s*(?:[:=]|\s{2,})\s*\(?\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            investing_cf_re: Regex::new(
                r"(?i)(?:net\s+)?cash\s+(?:provided\s+by|used\s+in)\s+investing\s+activities\s*(?:[:=]|\s{2,})\s*\(?\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            financing_cf_re: Regex::new(
                r"(?i)(?:net\s+)?cash\s+(?:provided\s+by|used\s+in)\s+financing\s+activities\s*(?:[:=]|\s{2,})\s*\(?\$?([\d,]+(?:\.\d+)?)",
            )
            .unwrap(),
            number_re: Regex::new(r"([\d,]+(?:\.\d+)?)").unwrap(),
        }
    }

    /// Extract a single first-match numeric value from a regex on text.
    fn first_match_f64(re: &Regex, text: &str) -> Option<f64> {
        re.captures(text)
            .and_then(|c| c.get(1))
            .and_then(|m| Self::parse_number(m.as_str()))
    }

    /// Parse a number string (with commas) into f64.
    fn parse_number(s: &str) -> Option<f64> {
        let cleaned: String = s.chars().filter(|c| *c != ',').collect();
        cleaned.parse::<f64>().ok()
    }

    // ─── Income Statement Extraction ───────────────────────────────

    /// Extract revenue from text.
    pub fn extract_revenue(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.revenue_re, text)
    }

    /// Extract cost of goods sold from text.
    pub fn extract_cogs(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.cogs_re, text)
    }

    /// Extract gross profit from text.
    pub fn extract_gross_profit(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.gross_profit_re, text)
    }

    /// Extract operating income from text.
    pub fn extract_operating_income(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.operating_income_re, text)
    }

    /// Extract net income from text.
    pub fn extract_net_income(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.net_income_re, text)
    }

    /// Extract all income statement items into a partial `FinancialPeriod`.
    pub fn extract_income_statement(&self, text: &str, label: &str) -> FinancialPeriod {
        let mut fp = FinancialPeriod::new(label);
        fp.revenue = self.extract_revenue(text);
        fp.cogs = self.extract_cogs(text);
        fp.gross_profit = self.extract_gross_profit(text);
        fp.operating_income = self.extract_operating_income(text);
        fp.net_income = self.extract_net_income(text);
        fp
    }

    // ─── Balance Sheet Extraction ──────────────────────────────────

    /// Extract total assets from text.
    pub fn extract_total_assets(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.total_assets_re, text)
    }

    /// Extract total liabilities from text.
    pub fn extract_total_liabilities(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.total_liabilities_re, text)
    }

    /// Extract shareholders' equity from text.
    pub fn extract_equity(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.equity_re, text)
    }

    /// Extract cash & equivalents from text.
    pub fn extract_cash(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.cash_re, text)
    }

    /// Extract debt from text.
    pub fn extract_debt(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.debt_re, text)
    }

    /// Extract current assets from text.
    pub fn extract_current_assets(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.current_assets_re, text)
    }

    /// Extract current liabilities from text.
    pub fn extract_current_liabilities(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.current_liabilities_re, text)
    }

    /// Extract all balance sheet items.
    pub fn extract_balance_sheet(&self, text: &str, label: &str) -> FinancialPeriod {
        let mut fp = FinancialPeriod::new(label);
        fp.total_assets = self.extract_total_assets(text);
        fp.total_liabilities = self.extract_total_liabilities(text);
        fp.equity = self.extract_equity(text);
        fp.cash = self.extract_cash(text);
        fp.debt = self.extract_debt(text);
        fp.current_assets = self.extract_current_assets(text);
        fp.current_liabilities = self.extract_current_liabilities(text);
        fp
    }

    // ─── Cash Flow Extraction ──────────────────────────────────────

    /// Extract operating cash flow from text.
    pub fn extract_operating_cf(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.operating_cf_re, text)
    }

    /// Extract investing cash flow from text.
    pub fn extract_investing_cf(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.investing_cf_re, text)
    }

    /// Extract financing cash flow from text.
    pub fn extract_financing_cf(&self, text: &str) -> Option<f64> {
        Self::first_match_f64(&self.financing_cf_re, text)
    }

    /// Extract all cash flow items.
    pub fn extract_cash_flow(&self, text: &str, label: &str) -> FinancialPeriod {
        let mut fp = FinancialPeriod::new(label);
        fp.operating_cf = self.extract_operating_cf(text);
        fp.investing_cf = self.extract_investing_cf(text);
        fp.financing_cf = self.extract_financing_cf(text);
        fp
    }

    // ─── Ratio Computation ─────────────────────────────────────────

    /// Compute debt-to-equity ratio.
    pub fn debt_to_equity(debt: Option<f64>, equity: Option<f64>) -> Option<f64> {
        match (debt, equity) {
            (Some(d), Some(e)) if e.abs() > f64::EPSILON => Some(d / e),
            _ => None,
        }
    }

    /// Compute current ratio (current assets / current liabilities).
    pub fn current_ratio(current_assets: Option<f64>, current_liabilities: Option<f64>) -> Option<f64> {
        match (current_assets, current_liabilities) {
            (Some(ca), Some(cl)) if cl.abs() > f64::EPSILON => Some(ca / cl),
            _ => None,
        }
    }

    /// Compute gross margin (gross_profit / revenue).
    pub fn gross_margin(gross_profit: Option<f64>, revenue: Option<f64>) -> Option<f64> {
        match (gross_profit, revenue) {
            (Some(gp), Some(r)) if r.abs() > f64::EPSILON => Some(gp / r),
            _ => None,
        }
    }

    /// Compute operating margin (operating_income / revenue).
    pub fn operating_margin(operating_income: Option<f64>, revenue: Option<f64>) -> Option<f64> {
        match (operating_income, revenue) {
            (Some(oi), Some(r)) if r.abs() > f64::EPSILON => Some(oi / r),
            _ => None,
        }
    }

    /// Compute net margin (net_income / revenue).
    pub fn net_margin(net_income: Option<f64>, revenue: Option<f64>) -> Option<f64> {
        match (net_income, revenue) {
            (Some(ni), Some(r)) if r.abs() > f64::EPSILON => Some(ni / r),
            _ => None,
        }
    }

    /// Compute return on equity (net_income / equity).
    pub fn roe(net_income: Option<f64>, equity: Option<f64>) -> Option<f64> {
        match (net_income, equity) {
            (Some(ni), Some(e)) if e.abs() > f64::EPSILON => Some(ni / e),
            _ => None,
        }
    }

    /// Compute return on assets (net_income / total_assets).
    pub fn roa(net_income: Option<f64>, total_assets: Option<f64>) -> Option<f64> {
        match (net_income, total_assets) {
            (Some(ni), Some(ta)) if ta.abs() > f64::EPSILON => Some(ni / ta),
            _ => None,
        }
    }

    /// Compute all key ratios from a `FinancialPeriod`.
    pub fn compute_ratios(&self, fp: &FinancialPeriod) -> Vec<FinancialRatio> {
        let mut ratios = Vec::new();

        if let Some(v) = Self::debt_to_equity(fp.debt, fp.equity) {
            ratios.push(FinancialRatio::new("debt_to_equity", v));
        }
        if let Some(v) = Self::current_ratio(fp.current_assets, fp.current_liabilities) {
            ratios.push(FinancialRatio::new("current_ratio", v));
        }
        if let Some(v) = Self::gross_margin(fp.gross_profit, fp.revenue) {
            ratios.push(FinancialRatio::new("gross_margin", v));
        }
        if let Some(v) = Self::operating_margin(fp.operating_income, fp.revenue) {
            ratios.push(FinancialRatio::new("operating_margin", v));
        }
        if let Some(v) = Self::net_margin(fp.net_income, fp.revenue) {
            ratios.push(FinancialRatio::new("net_margin", v));
        }
        if let Some(v) = Self::roe(fp.net_income, fp.equity) {
            ratios.push(FinancialRatio::new("roe", v));
        }
        if let Some(v) = Self::roa(fp.net_income, fp.total_assets) {
            ratios.push(FinancialRatio::new("roa", v));
        }

        ratios
    }

    /// Compute all key ratios with benchmark comparison.
    pub fn compute_ratios_with_benchmarks(
        &self,
        fp: &FinancialPeriod,
        benchmarks: &std::collections::HashMap<String, f64>,
    ) -> Vec<FinancialRatio> {
        let raw = self.compute_ratios(fp);
        raw.into_iter()
            .map(|mut r| {
                if let Some(&b) = benchmarks.get(&r.ratio_name) {
                    r.benchmark = Some(b);
                }
                r
            })
            .collect()
    }

    // ─── Trend Analysis ────────────────────────────────────────────

    /// Analyze trends for a given ratio name across multiple financial periods.
    pub fn trend_analysis(&self, periods: &[FinancialPeriod], ratio_name: &str) -> Trend {
        let values: Vec<f64> = periods
            .iter()
            .filter_map(|fp| {
                let ratios = self.compute_ratios(fp);
                ratios.iter().find(|r| r.ratio_name == ratio_name).map(|r| r.value)
            })
            .collect();
        Trend::from_values(&values)
    }

    /// Compute the trend for each ratio across periods, returning a map of ratio_name → Trend.
    pub fn all_trends(&self, periods: &[FinancialPeriod]) -> std::collections::HashMap<String, Trend> {
        let ratio_names = [
            "debt_to_equity",
            "current_ratio",
            "gross_margin",
            "operating_margin",
            "net_margin",
            "roe",
            "roa",
        ];
        let mut trends = std::collections::HashMap::new();
        for name in &ratio_names {
            trends.insert(name.to_string(), self.trend_analysis(periods, name));
        }
        trends
    }

    // ─── Full Extraction ───────────────────────────────────────────

    /// Extract a full `FinancialPeriod` from combined filing text (attempts all categories).
    pub fn extract_full_period(&self, text: &str, label: &str) -> FinancialPeriod {
        let mut fp = FinancialPeriod::new(label);
        fp.revenue = self.extract_revenue(text);
        fp.cogs = self.extract_cogs(text);
        fp.gross_profit = self.extract_gross_profit(text);
        fp.operating_income = self.extract_operating_income(text);
        fp.net_income = self.extract_net_income(text);
        fp.total_assets = self.extract_total_assets(text);
        fp.total_liabilities = self.extract_total_liabilities(text);
        fp.equity = self.extract_equity(text);
        fp.cash = self.extract_cash(text);
        fp.debt = self.extract_debt(text);
        fp.current_assets = self.extract_current_assets(text);
        fp.current_liabilities = self.extract_current_liabilities(text);
        fp.operating_cf = self.extract_operating_cf(text);
        fp.investing_cf = self.extract_investing_cf(text);
        fp.financing_cf = self.extract_financing_cf(text);
        fp
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_income_text() -> &'static str {
        r#"Total Revenue: $394,328,000,000
Cost of Revenue: $210,000,000,000
Gross Profit: $184,328,000,000
Operating Income: $130,000,000,000
Net Income: $100,916,000,000"#
    }

    fn sample_balance_text() -> &'static str {
        r#"Total Assets: $352,583,000,000
Total Liabilities: $275,000,000,000
Stockholders' Equity: $77,583,000,000
Cash and cash equivalents: $30,000,000,000
Long-term debt: $100,000,000,000
Total current assets: $150,000,000,000
Total current liabilities: $120,000,000,000"#
    }

    fn sample_cashflow_text() -> &'static str {
        r#"Net cash provided by operating activities: $110,000,000,000
Net cash used in investing activities: ($40,000,000,000)
Net cash used in financing activities: ($55,000,000,000)"#
    }

    fn extractor() -> FinancialExtractor {
        FinancialExtractor::new()
    }

    #[test]
    fn test_extract_revenue() {
        let e = extractor();
        let v = e.extract_revenue(sample_income_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 394_328_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_cogs() {
        let e = extractor();
        let v = e.extract_cogs(sample_income_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 210_000_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_gross_profit() {
        let e = extractor();
        let v = e.extract_gross_profit(sample_income_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 184_328_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_operating_income() {
        let e = extractor();
        let v = e.extract_operating_income(sample_income_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 130_000_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_net_income() {
        let e = extractor();
        let v = e.extract_net_income(sample_income_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 100_916_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_total_assets() {
        let e = extractor();
        let v = e.extract_total_assets(sample_balance_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 352_583_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_total_liabilities() {
        let e = extractor();
        let v = e.extract_total_liabilities(sample_balance_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 275_000_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_equity() {
        let e = extractor();
        let v = e.extract_equity(sample_balance_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 77_583_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_cash() {
        let e = extractor();
        let v = e.extract_cash(sample_balance_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 30_000_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_debt() {
        let e = extractor();
        let v = e.extract_debt(sample_balance_text());
        assert!(v.is_some());
        assert!((v.unwrap() - 100_000_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_extract_operating_cf() {
        let e = extractor();
        // The regex for operating CF uses "provided by" pattern. Let's verify.
        let v = e.extract_operating_cf(sample_cashflow_text());
        assert!(v.is_some());
    }

    #[test]
    fn test_extract_investing_cf() {
        let e = extractor();
        let v = e.extract_investing_cf(sample_cashflow_text());
        assert!(v.is_some());
    }

    #[test]
    fn test_extract_financing_cf() {
        let e = extractor();
        let v = e.extract_financing_cf(sample_cashflow_text());
        assert!(v.is_some());
    }

    #[test]
    fn test_debt_to_equity() {
        let result = FinancialExtractor::debt_to_equity(Some(100.0), Some(50.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_debt_to_equity_zero_equity() {
        let result = FinancialExtractor::debt_to_equity(Some(100.0), Some(0.0));
        assert!(result.is_none());
    }

    #[test]
    fn test_current_ratio() {
        let result = FinancialExtractor::current_ratio(Some(200.0), Some(100.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_gross_margin() {
        let result = FinancialExtractor::gross_margin(Some(40.0), Some(100.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 0.4).abs() < 1e-10);
    }

    #[test]
    fn test_operating_margin() {
        let result = FinancialExtractor::operating_margin(Some(25.0), Some(100.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 0.25).abs() < 1e-10);
    }

    #[test]
    fn test_net_margin() {
        let result = FinancialExtractor::net_margin(Some(10.0), Some(100.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 0.1).abs() < 1e-10);
    }

    #[test]
    fn test_roe() {
        let result = FinancialExtractor::roe(Some(15.0), Some(100.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 0.15).abs() < 1e-10);
    }

    #[test]
    fn test_roa() {
        let result = FinancialExtractor::roa(Some(10.0), Some(200.0));
        assert!(result.is_some());
        assert!((result.unwrap() - 0.05).abs() < 1e-10);
    }

    #[test]
    fn test_ratio_none_on_missing_data() {
        let result = FinancialExtractor::net_margin(None, Some(100.0));
        assert!(result.is_none());
    }

    #[test]
    fn test_compute_ratios() {
        let e = extractor();
        let fp = e.extract_full_period(
            &format!(
                "{}\n{}\n{}",
                sample_income_text(),
                sample_balance_text(),
                sample_cashflow_text()
            ),
            "FY2024",
        );
        let ratios = e.compute_ratios(&fp);
        assert!(!ratios.is_empty());
        let names: Vec<&str> = ratios.iter().map(|r| r.ratio_name.as_str()).collect();
        assert!(names.contains(&"gross_margin"));
        assert!(names.contains(&"net_margin"));
        assert!(names.contains(&"roe"));
    }

    #[test]
    fn test_compute_ratios_with_benchmarks() {
        let e = extractor();
        let mut fp = FinancialPeriod::new("FY");
        fp.net_income = Some(10.0);
        fp.equity = Some(50.0);
        let mut bm = std::collections::HashMap::new();
        bm.insert("roe".to_string(), 0.15);
        let ratios = e.compute_ratios_with_benchmarks(&fp, &bm);
        let roe = ratios.iter().find(|r| r.ratio_name == "roe").unwrap();
        assert!(roe.benchmark.is_some());
    }

    #[test]
    fn test_trend_analysis_improving() {
        let e = extractor();
        let mut fp1 = FinancialPeriod::new("Q1");
        fp1.net_income = Some(8.0);
        fp1.equity = Some(100.0);
        let mut fp2 = FinancialPeriod::new("Q2");
        fp2.net_income = Some(12.0);
        fp2.equity = Some(100.0);
        let trend = e.trend_analysis(&[fp1, fp2], "roe");
        assert_eq!(trend, Trend::Improving);
    }

    #[test]
    fn test_trend_analysis_declining() {
        let e = extractor();
        let mut fp1 = FinancialPeriod::new("Q1");
        fp1.net_income = Some(20.0);
        fp1.equity = Some(100.0);
        let mut fp2 = FinancialPeriod::new("Q2");
        fp2.net_income = Some(10.0);
        fp2.equity = Some(100.0);
        let trend = e.trend_analysis(&[fp1, fp2], "roe");
        assert_eq!(trend, Trend::Declining);
    }

    #[test]
    fn test_trend_unknown_insufficient_data() {
        let e = extractor();
        let mut fp1 = FinancialPeriod::new("Q1");
        fp1.net_income = Some(10.0);
        fp1.equity = Some(100.0);
        let trend = e.trend_analysis(&[fp1], "roe");
        assert_eq!(trend, Trend::Unknown);
    }

    #[test]
    fn test_all_trends() {
        let e = extractor();
        let mut fp1 = FinancialPeriod::new("Q1");
        fp1.revenue = Some(100.0);
        fp1.gross_profit = Some(40.0);
        fp1.operating_income = Some(25.0);
        fp1.net_income = Some(10.0);
        fp1.total_assets = Some(200.0);
        fp1.equity = Some(80.0);
        fp1.debt = Some(60.0);
        fp1.current_assets = Some(120.0);
        fp1.current_liabilities = Some(60.0);

        let mut fp2 = FinancialPeriod::new("Q2");
        fp2.revenue = Some(110.0);
        fp2.gross_profit = Some(46.2);
        fp2.operating_income = Some(28.6);
        fp2.net_income = Some(11.0);
        fp2.total_assets = Some(210.0);
        fp2.equity = Some(85.0);
        fp2.debt = Some(65.0);
        fp2.current_assets = Some(130.0);
        fp2.current_liabilities = Some(65.0);

        let trends = e.all_trends(&[fp1, fp2]);
        assert_eq!(trends.len(), 7);
        assert!(trends.contains_key("gross_margin"));
        assert!(trends.contains_key("roe"));
    }

    #[test]
    fn test_extract_full_period() {
        let e = extractor();
        let fp = e.extract_full_period(
            &format!(
                "{}\n{}\n{}",
                sample_income_text(),
                sample_balance_text(),
                sample_cashflow_text()
            ),
            "FY2024",
        );
        assert!(fp.revenue.is_some());
        assert!(fp.net_income.is_some());
        assert!(fp.total_assets.is_some());
        assert!(fp.equity.is_some());
        assert!(fp.operating_cf.is_some());
    }

    #[test]
    fn test_extract_income_statement() {
        let e = extractor();
        let fp = e.extract_income_statement(sample_income_text(), "FY");
        assert!(fp.revenue.is_some());
        assert!(fp.cogs.is_some());
        assert!(fp.gross_profit.is_some());
        assert!(fp.operating_income.is_some());
        assert!(fp.net_income.is_some());
        assert!(fp.total_assets.is_none());
    }

    #[test]
    fn test_extract_balance_sheet() {
        let e = extractor();
        let fp = e.extract_balance_sheet(sample_balance_text(), "FY");
        assert!(fp.total_assets.is_some());
        assert!(fp.total_liabilities.is_some());
        assert!(fp.equity.is_some());
        assert!(fp.revenue.is_none());
    }
}
