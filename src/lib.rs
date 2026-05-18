//! # SEC Earnings Workbench
//!
//! A comprehensive Rust crate for analyzing SEC filings, earnings reports,
//! insider trading activity, financial ratios, and risk factors. Provides
//! a full analysis pipeline from raw filing text to structured insights.

pub mod types;
pub mod parser;
pub mod sentiment;
pub mod risk;
pub mod financials;
pub mod insider;
pub mod earnings;
pub mod pipeline;

// Re-export key types for convenience
pub use types::{
    AlertThreshold, AnalysisResult, BeatMiss, ComparisonReport, EarningsReport,
    EarningsSurprise, FilingSection, FilingType, FinancialRatio, GuidanceItem,
    GuidanceType, InsiderTrade, ManagementTone, RiskCategory, RiskFactor, SecFiling,
    Severity, SentimentScore, Trend, TransactionType,
};

// Re-export key analyzers
pub use parser::FilingParser;
pub use sentiment::EarningsSentimentAnalyzer;
pub use risk::RiskFactorExtractor;
pub use financials::{FinancialExtractor, FinancialPeriod};
pub use insider::{InsiderAnalyzer, CompanyInsiderSummary, UnusualActivity};
pub use earnings::{EarningsAnalyzer, ConsistencyScore, RevenueQuality, GuidanceTrack, SurpriseResult};
pub use pipeline::{AnalysisPipeline, WatchlistConfig, Alert};
