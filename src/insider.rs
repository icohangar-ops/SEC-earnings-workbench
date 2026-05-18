//! # Insider Trading Analysis
//!
//! Parses insider trade data, classifies transactions, aggregates activity,
//! computes insider sentiment scores, and detects unusual trading patterns.

use crate::types::{InsiderTrade, TransactionType};
use chrono::NaiveDate;
use regex::Regex;
use std::collections::HashMap;

/// Aggregated insider activity for a single company.
#[derive(Debug, Clone, Default)]
pub struct CompanyInsiderSummary {
    pub company: String,
    pub total_purchases: f64,
    pub total_sales: f64,
    pub net_shares: f64,
    pub total_purchase_value: f64,
    pub total_sale_value: f64,
    pub num_transactions: usize,
    pub num_insiders: usize,
    pub unique_insiders: Vec<String>,
}

impl CompanyInsiderSummary {
    /// Compute net buying ratio: (purchase_value - sale_value) / (purchase_value + sale_value).
    /// Returns 1.0 when all buying, -1.0 when all selling, 0.0 for none.
    pub fn net_buying_ratio(&self) -> f64 {
        let total = self.total_purchase_value + self.total_sale_value;
        if total.abs() < f64::EPSILON {
            return 0.0;
        }
        (self.total_purchase_value - self.total_sale_value) / total
    }

    /// Insider sentiment score on 0.0–1.0 scale.
    /// 1.0 = strong buying, 0.0 = strong selling, 0.5 = neutral.
    pub fn sentiment_score(&self) -> f64 {
        ((self.net_buying_ratio() + 1.0) / 2.0).clamp(0.0, 1.0)
    }
}

/// A detected unusual activity alert.
#[derive(Debug, Clone)]
pub struct UnusualActivity {
    pub insider_name: String,
    pub transaction_type: TransactionType,
    pub shares: f64,
    pub total_value: f64,
    pub spike_factor: f64,
    pub description: String,
}

/// Analyzes insider trading data for sentiment signals and anomalies.
#[derive(Debug)]
pub struct InsiderAnalyzer {
    line_pattern: Regex,
    json_pattern: Regex,
}

impl Default for InsiderAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl InsiderAnalyzer {
    /// Create a new analyzer with compiled patterns.
    pub fn new() -> Self {
        // Pattern for structured text lines: name, title, code, shares, price
        // e.g. "John Doe,CEO,P,1000,$150.25"
        let line_pattern = Regex::new(
            r"(?i)^([a-z\s]+),\s*([a-z\s]+),\s*([A-Z]),\s*([\d,]+(?:\.\d+)?),\s*\$?([\d,]+(?:\.\d+)?)",
        )
        .unwrap();

        // Simple JSON key-value extraction helper (used for JSON-like inputs)
        let json_pattern = Regex::new(r#""(\w+)"\s*:\s*"([^"]*)""#).unwrap();

        Self {
            line_pattern,
            json_pattern,
        }
    }

    // ─── Parsing ──────────────────────────────────────────────────

    /// Parse a single CSV-style line into an `InsiderTrade`.
    /// Format: "Name,Title,Code,Shares,Price"
    /// Code: P=Purchase, S=Sale, M=OptionExercise, G=Gift
    pub fn parse_trade_line(&self, line: &str) -> Option<InsiderTrade> {
        let caps = self.line_pattern.captures(line.trim())?;
        let name = caps.get(1)?.as_str().trim();
        let title = caps.get(2)?.as_str().trim();
        let code = caps.get(3)?.as_str();
        let shares_str = caps.get(4)?.as_str();
        let price_str = caps.get(5)?.as_str();

        let txn_type = TransactionType::from_code(code);
        let shares = Self::parse_num(shares_str)?;
        let price = Self::parse_num(price_str)?;

        Some(InsiderTrade::new(name, title, txn_type, shares, price))
    }

    /// Parse multiple lines of trade data.
    pub fn parse_trades(&self, text: &str) -> Vec<InsiderTrade> {
        text.lines()
            .filter_map(|line| self.parse_trade_line(line))
            .collect()
    }

    /// Parse a JSON-formatted string of insider trades.
    /// Expects a JSON array of objects with keys: name, title, code, shares, price.
    pub fn parse_trades_json(&self, json_str: &str) -> Vec<InsiderTrade> {
        // Use serde_json for robust parsing
        let values: Vec<serde_json::Value> = match serde_json::from_str(json_str) {
            Ok(v) => v,
            Err(_) => return Vec::new(),
        };

        values
            .iter()
            .filter_map(|v| {
                let name = v.get("name")?.as_str()?;
                let title = v.get("title")?.as_str()?;
                let code = v.get("code")?.as_str()?;
                let shares = v.get("shares")?.as_f64()?;
                let price = v.get("price")?.as_f64()?;

                Some(InsiderTrade::new(
                    name,
                    title,
                    TransactionType::from_code(code),
                    shares,
                    price,
                ))
            })
            .collect()
    }

    /// Classify transaction type from a free-form description string.
    pub fn classify_transaction(&self, description: &str) -> TransactionType {
        let lower = description.to_lowercase();
        if lower.contains("purchase") || lower.contains("bought") || lower.contains("acquired") {
            TransactionType::Purchase
        } else if lower.contains("sale") || lower.contains("sold") || lower.contains("disposed") {
            TransactionType::Sale
        } else if lower.contains("option") && (lower.contains("exercise") || lower.contains("exercised")) {
            TransactionType::OptionExercise
        } else if lower.contains("gift") {
            TransactionType::Gift
        } else {
            TransactionType::Other
        }
    }

    /// Set the date on a trade.
    pub fn with_date(trade: InsiderTrade, date: NaiveDate) -> InsiderTrade {
        InsiderTrade { date: Some(date), ..trade }
    }

    // ─── Aggregation ──────────────────────────────────────────────

    /// Aggregate all trades into a single company summary.
    pub fn aggregate(&self, trades: &[InsiderTrade]) -> CompanyInsiderSummary {
        let mut summary = CompanyInsiderSummary::default();
        let mut insider_set = std::collections::HashSet::new();

        for trade in trades {
            summary.num_transactions += 1;
            insider_set.insert(trade.insider_name.clone());

            match trade.transaction_type {
                TransactionType::Purchase => {
                    summary.total_purchases += trade.shares;
                    summary.total_purchase_value += trade.total_value;
                }
                TransactionType::Sale => {
                    summary.total_sales += trade.shares;
                    summary.total_sale_value += trade.total_value;
                }
                TransactionType::OptionExercise => {
                    // Treat option exercises as acquisitions
                    summary.total_purchases += trade.shares;
                    summary.total_purchase_value += trade.total_value;
                }
                _ => {}
            }
        }

        summary.net_shares = summary.total_purchases - summary.total_sales;
        summary.num_insiders = insider_set.len();
        summary.unique_insiders = insider_set.into_iter().collect();
        summary
    }

    /// Aggregate by company (groups trades by insider_name similarity — for single-company use).
    pub fn aggregate_by_period(
        &self,
        trades: &[InsiderTrade],
    ) -> HashMap<String, CompanyInsiderSummary> {
        let mut map: HashMap<String, Vec<InsiderTrade>> = HashMap::new();
        for trade in trades {
            let key = trade
                .date
                .map(|d| format!("period_{}", d.format("%Y-%m")))
                .unwrap_or_else(|| "unknown_period".to_string());
            map.entry(key).or_default().push(trade.clone());
        }

        map.into_iter()
            .map(|(k, v)| {
                let summary = self.aggregate(&v);
                (k, summary)
            })
            .collect()
    }

    /// Compute overall insider sentiment score from a list of trades.
    pub fn sentiment_score(&self, trades: &[InsiderTrade]) -> f64 {
        self.aggregate(trades).sentiment_score()
    }

    // ─── Unusual Activity Detection ───────────────────────────────

    /// Detect unusual activity: trades whose value exceeds `spike_threshold`
    /// times the average trade value for the same transaction type.
    pub fn detect_unusual_activity(
        &self,
        trades: &[InsiderTrade],
        spike_threshold: f64,
    ) -> Vec<UnusualActivity> {
        if trades.is_empty() {
            return Vec::new();
        }

        // Compute average value per transaction type
        let mut type_values: HashMap<TransactionType, Vec<f64>> = HashMap::new();
        for trade in trades {
            type_values
                .entry(trade.transaction_type)
                .or_default()
                .push(trade.total_value);
        }

        let type_averages: HashMap<TransactionType, f64> = type_values
            .iter()
            .map(|(k, v)| {
                let avg = v.iter().sum::<f64>() / v.len() as f64;
                (*k, avg)
            })
            .collect();

        let mut alerts = Vec::new();
        for trade in trades {
            if let Some(&avg) = type_averages.get(&trade.transaction_type) {
                if avg.abs() > f64::EPSILON {
                    let factor = trade.total_value / avg;
                    if factor >= spike_threshold {
                        alerts.push(UnusualActivity {
                            insider_name: trade.insider_name.clone(),
                            transaction_type: trade.transaction_type,
                            shares: trade.shares,
                            total_value: trade.total_value,
                            spike_factor: factor,
                            description: format!(
                                "{} traded {} shares (${:.2}) — {:.1}x average for {}",
                                trade.insider_name,
                                trade.shares,
                                trade.total_value,
                                factor,
                                trade.transaction_type,
                            ),
                        });
                    }
                }
            }
        }

        // Sort by spike factor descending
        alerts.sort_by(|a, b| b.spike_factor.partial_cmp(&a.spike_factor).unwrap());
        alerts
    }

    // ─── Helpers ──────────────────────────────────────────────────

    fn parse_num(s: &str) -> Option<f64> {
        let cleaned: String = s.chars().filter(|c| *c != ',').collect();
        cleaned.parse::<f64>().ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn analyzer() -> InsiderAnalyzer {
        InsiderAnalyzer::new()
    }

    fn sample_trades() -> Vec<InsiderTrade> {
        vec![
            InsiderTrade::new("John Doe", "CEO", TransactionType::Purchase, 10_000.0, 150.0),
            InsiderTrade::new("Jane Smith", "CFO", TransactionType::Sale, 5_000.0, 155.0),
            InsiderTrade::new("Bob Johnson", "CTO", TransactionType::Purchase, 3_000.0, 148.0),
            InsiderTrade::new("Alice Lee", "VP", TransactionType::OptionExercise, 20_000.0, 100.0),
        ]
    }

    #[test]
    fn test_parse_trade_line_purchase() {
        let a = analyzer();
        let trade = a.parse_trade_line("John Doe,CEO,P,1000,$150.25").unwrap();
        assert_eq!(trade.insider_name, "John Doe");
        assert_eq!(trade.title, "CEO");
        assert_eq!(trade.transaction_type, TransactionType::Purchase);
        assert!((trade.shares - 1000.0).abs() < 1e-6);
        assert!((trade.price - 150.25).abs() < 1e-6);
        assert!((trade.total_value - 150_250.0).abs() < 1e-3);
    }

    #[test]
    fn test_parse_trade_line_sale() {
        let a = analyzer();
        let trade = a.parse_trade_line("Jane Smith,CFO,S,500,$200.00").unwrap();
        assert_eq!(trade.transaction_type, TransactionType::Sale);
        assert!((trade.shares - 500.0).abs() < 1e-6);
    }

    #[test]
    fn test_parse_trade_line_option_exercise() {
        let a = analyzer();
        let trade = a.parse_trade_line("Bob Johnson,CTO,M,2000,$100.00").unwrap();
        assert_eq!(trade.transaction_type, TransactionType::OptionExercise);
    }

    #[test]
    fn test_parse_trade_line_invalid() {
        let a = analyzer();
        let result = a.parse_trade_line("not a valid trade line");
        assert!(result.is_none());
    }

    #[test]
    fn test_parse_trades_multiple() {
        let a = analyzer();
        let text = "John Doe,CEO,P,1000,$150.00\nJane Smith,CFO,S,500,$200.00";
        let trades = a.parse_trades(text);
        assert_eq!(trades.len(), 2);
    }

    #[test]
    fn test_parse_trades_json() {
        let a = analyzer();
        let json = r#"[
            {"name":"John Doe","title":"CEO","code":"P","shares":1000,"price":150.0},
            {"name":"Jane Smith","title":"CFO","code":"S","shares":500,"price":200.0}
        ]"#;
        let trades = a.parse_trades_json(json);
        assert_eq!(trades.len(), 2);
        assert_eq!(trades[0].insider_name, "John Doe");
        assert_eq!(trades[1].transaction_type, TransactionType::Sale);
    }

    #[test]
    fn test_parse_trades_json_invalid() {
        let a = analyzer();
        let trades = a.parse_trades_json("not json");
        assert!(trades.is_empty());
    }

    #[test]
    fn test_classify_transaction_purchase() {
        let a = analyzer();
        assert_eq!(
            a.classify_transaction("Purchased 1000 shares of common stock"),
            TransactionType::Purchase
        );
    }

    #[test]
    fn test_classify_transaction_sale() {
        let a = analyzer();
        assert_eq!(
            a.classify_transaction("Sold 500 shares of common stock"),
            TransactionType::Sale
        );
    }

    #[test]
    fn test_classify_transaction_option() {
        let a = analyzer();
        assert_eq!(
            a.classify_transaction("Exercised stock options for 2000 shares"),
            TransactionType::OptionExercise
        );
    }

    #[test]
    fn test_classify_transaction_gift() {
        let a = analyzer();
        assert_eq!(
            a.classify_transaction("Gift of 100 shares to family member"),
            TransactionType::Gift
        );
    }

    #[test]
    fn test_aggregate() {
        let a = analyzer();
        let trades = sample_trades();
        let summary = a.aggregate(&trades);
        assert_eq!(summary.num_transactions, 4);
        assert_eq!(summary.num_insiders, 4);
        // Purchases: 10000 + 3000 + 20000(option) = 33000
        // Sales: 5000
        assert!((summary.total_purchases - 33_000.0).abs() < 1e-6);
        assert!((summary.total_sales - 5_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_net_buying_ratio() {
        let a = analyzer();
        let trades = vec![
            InsiderTrade::new("A", "CEO", TransactionType::Purchase, 1000.0, 100.0),
            InsiderTrade::new("B", "CFO", TransactionType::Sale, 1000.0, 100.0),
        ];
        let summary = a.aggregate(&trades);
        // Equal values → ratio = 0.0
        assert!((summary.net_buying_ratio() - 0.0).abs() < 1e-10);
        assert!((summary.sentiment_score() - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_sentiment_score_all_buying() {
        let a = analyzer();
        let trades = vec![
            InsiderTrade::new("A", "CEO", TransactionType::Purchase, 1000.0, 100.0),
        ];
        let score = a.sentiment_score(&trades);
        assert!((score - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_sentiment_score_all_selling() {
        let a = analyzer();
        let trades = vec![
            InsiderTrade::new("A", "CEO", TransactionType::Sale, 1000.0, 100.0),
        ];
        let score = a.sentiment_score(&trades);
        assert!((score - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_detect_unusual_activity() {
        let a = analyzer();
        let trades = vec![
            InsiderTrade::new("A", "CEO", TransactionType::Purchase, 100.0, 10.0),  // $1000
            InsiderTrade::new("B", "CFO", TransactionType::Purchase, 200.0, 10.0),  // $2000
            InsiderTrade::new("C", "CTO", TransactionType::Purchase, 5000.0, 10.0), // $50000
        ];
        // avg = (1000+2000+50000)/3 ≈ 17667. factor for C = 50000/17667 ≈ 2.83. Use threshold 2.8.
        let alerts = a.detect_unusual_activity(&trades, 2.8);
        assert_eq!(alerts.len(), 1);
        assert_eq!(alerts[0].insider_name, "C");
    }

    #[test]
    fn test_detect_unusual_activity_empty() {
        let a = analyzer();
        let alerts = a.detect_unusual_activity(&[], 3.0);
        assert!(alerts.is_empty());
    }

    #[test]
    fn test_with_date() {
        let trade = InsiderTrade::new("A", "CEO", TransactionType::Purchase, 100.0, 10.0);
        let dated = InsiderAnalyzer::with_date(trade, NaiveDate::from_ymd_opt(2024, 3, 15).unwrap());
        assert!(dated.date.is_some());
        assert_eq!(dated.date.unwrap(), NaiveDate::from_ymd_opt(2024, 3, 15).unwrap());
    }

    #[test]
    fn test_aggregate_by_period() {
        let a = analyzer();
        let mut t1 = InsiderTrade::new("A", "CEO", TransactionType::Purchase, 1000.0, 100.0);
        t1.date = Some(NaiveDate::from_ymd_opt(2024, 1, 15).unwrap());
        let mut t2 = InsiderTrade::new("B", "CFO", TransactionType::Sale, 500.0, 100.0);
        t2.date = Some(NaiveDate::from_ymd_opt(2024, 2, 15).unwrap());

        let by_period = a.aggregate_by_period(&[t1, t2]);
        assert_eq!(by_period.len(), 2);
    }
}
