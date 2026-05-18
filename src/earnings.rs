//! # Earnings Analysis Engine
//!
//! Computes earnings surprises, classifies beat/miss/meet, tracks consistency
//! across quarters, monitors guidance, and assesses revenue quality.

use crate::types::{BeatMiss, EarningsReport, EarningsSurprise, GuidanceItem, GuidanceType};

/// Result of earnings surprise computation.
#[derive(Debug, Clone)]
pub struct SurpriseResult {
    pub metric: String,
    pub expected: f64,
    pub actual: f64,
    pub surprise_pct: f64,
    pub beat_miss: BeatMiss,
}

/// Consistency scoring across multiple quarters.
#[derive(Debug, Clone)]
pub struct ConsistencyScore {
    pub quarters_analyzed: usize,
    pub beat_count: usize,
    pub miss_count: usize,
    pub meet_count: usize,
    pub beat_rate: f64,
    pub consistency_index: f64, // 0.0 = erratic, 1.0 = perfectly consistent
}

/// Revenue quality assessment.
#[derive(Debug, Clone)]
pub struct RevenueQuality {
    pub recurring_ratio: f64,     // 0.0–1.0 estimated ratio of recurring revenue
    pub one_time_indicators: Vec<String>,
    pub quality_score: f64,       // 0.0–1.0 overall quality score
}

/// Guidance tracking: initial → revised → actual.
#[derive(Debug, Clone)]
pub struct GuidanceTrack {
    pub metric: String,
    pub initial: Option<GuidanceItem>,
    pub revised: Vec<GuidanceItem>,
    pub actual: Option<GuidanceItem>,
    pub initial_vs_actual_pct: Option<f64>,
}

/// Analyzes earnings data for surprises, consistency, and quality.
#[derive(Debug)]
pub struct EarningsAnalyzer {
    /// Threshold in % above which a positive surprise is classified as Beat.
    beat_threshold: f64,
    /// Threshold in % below which a negative surprise is classified as Miss.
    miss_threshold: f64,
}

impl Default for EarningsAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl EarningsAnalyzer {
    /// Create an analyzer with default thresholds (2% beat, -2% miss).
    pub fn new() -> Self {
        Self {
            beat_threshold: 2.0,
            miss_threshold: -2.0,
        }
    }

    /// Create an analyzer with custom thresholds.
    pub fn with_thresholds(beat_threshold: f64, miss_threshold: f64) -> Self {
        Self {
            beat_threshold,
            miss_threshold,
        }
    }

    // ─── Surprise Computation ─────────────────────────────────────

    /// Compute earnings surprise: (actual - expected) / |expected| * 100.
    pub fn compute_surprise(&self, expected: f64, actual: f64) -> f64 {
        if expected.abs() < f64::EPSILON {
            return 0.0;
        }
        (actual - expected) / expected.abs() * 100.0
    }

    /// Compute surprise and classify as Beat/Miss/Meet.
    pub fn compute_surprise_result(
        &self,
        metric: &str,
        expected: f64,
        actual: f64,
    ) -> SurpriseResult {
        let surprise_pct = self.compute_surprise(expected, actual);
        let beat_miss = self.classify_surprise(surprise_pct);
        SurpriseResult {
            metric: metric.to_string(),
            expected,
            actual,
            surprise_pct,
            beat_miss,
        }
    }

    /// Classify surprise percentage into Beat/Miss/Meet using configured thresholds.
    pub fn classify_surprise(&self, surprise_pct: f64) -> BeatMiss {
        if surprise_pct > self.beat_threshold {
            BeatMiss::Beat
        } else if surprise_pct < self.miss_threshold {
            BeatMiss::Miss
        } else {
            BeatMiss::Meet
        }
    }

    /// Compute surprise using the types module's `EarningsSurprise` (uses built-in thresholds).
    pub fn to_earnings_surprise(&self, metric: &str, expected: f64, actual: f64) -> EarningsSurprise {
        EarningsSurprise::new(metric, expected, actual)
    }

    /// Compute surprise from an `EarningsReport` and consensus estimates.
    pub fn surprise_from_report(
        &self,
        report: &EarningsReport,
        expected_eps: Option<f64>,
        expected_revenue: Option<f64>,
    ) -> Vec<SurpriseResult> {
        let mut results = Vec::new();

        if let (Some(ea), Some(aa)) = (expected_eps, report.earnings_per_share) {
            results.push(self.compute_surprise_result("EPS", ea, aa));
        }
        if let (Some(er), Some(ar)) = (expected_revenue, report.revenue) {
            results.push(self.compute_surprise_result("Revenue", er, ar));
        }

        results
    }

    // ─── Consistency Scoring ──────────────────────────────────────

    /// Compute earnings consistency score from a list of BeatMiss results.
    pub fn consistency_score(&self, results: &[BeatMiss]) -> ConsistencyScore {
        let total = results.len();
        if total == 0 {
            return ConsistencyScore {
                quarters_analyzed: 0,
                beat_count: 0,
                miss_count: 0,
                meet_count: 0,
                beat_rate: 0.0,
                consistency_index: 0.0,
            };
        }

        let beat_count = results.iter().filter(|&&r| r == BeatMiss::Beat).count();
        let miss_count = results.iter().filter(|&&r| r == BeatMiss::Miss).count();
        let meet_count = results.iter().filter(|&&r| r == BeatMiss::Meet).count();

        let beat_rate = beat_count as f64 / total as f64;

        // Consistency index: higher when results are all the same direction
        // Perfectly consistent (all beats or all misses) = 1.0
        // Mixed results = lower
        let beat_frac = beat_count as f64 / total as f64;
        let miss_frac = miss_count as f64 / total as f64;
        let consistency_index = beat_frac * beat_frac + miss_frac * miss_frac;

        ConsistencyScore {
            quarters_analyzed: total,
            beat_count,
            miss_count,
            meet_count,
            beat_rate,
            consistency_index,
        }
    }

    /// Compute consistency from surprise percentages.
    pub fn consistency_from_pcts(&self, surprise_pcts: &[f64]) -> ConsistencyScore {
        let results: Vec<BeatMiss> = surprise_pcts
            .iter()
            .map(|&pct| self.classify_surprise(pct))
            .collect();
        self.consistency_score(&results)
    }

    /// Compute rolling N-quarter beat rate from surprise percentages.
    pub fn rolling_beat_rate(&self, surprise_pcts: &[f64], n: usize) -> f64 {
        if surprise_pcts.is_empty() || n == 0 {
            return 0.0;
        }
        let window = surprise_pcts.len().min(n);
        let recent = &surprise_pcts[surprise_pcts.len() - window..];
        let beats = recent
            .iter()
            .filter(|&&pct| self.classify_surprise(pct) == BeatMiss::Beat)
            .count();
        beats as f64 / window as f64
    }

    // ─── Guidance Tracking ────────────────────────────────────────

    /// Create a new guidance track for a metric.
    pub fn new_guidance_track(metric: &str) -> GuidanceTrack {
        GuidanceTrack {
            metric: metric.to_string(),
            initial: None,
            revised: Vec::new(),
            actual: None,
            initial_vs_actual_pct: None,
        }
    }

    /// Track guidance from initial → revised → actual.
    pub fn track_guidance(
        &self,
        metric: &str,
        initial: Option<f64>,
        revised_values: &[f64],
        actual: Option<f64>,
    ) -> GuidanceTrack {
        let mut track = Self::new_guidance_track(metric);
        if let Some(v) = initial {
            track.initial = Some(GuidanceItem::new(metric, v, GuidanceType::Initial));
        }
        for &v in revised_values {
            track.revised.push(GuidanceItem::new(metric, v, GuidanceType::Revised));
        }
        if let Some(v) = actual {
            track.actual = Some(GuidanceItem::new(metric, v, GuidanceType::Actual));
        }
        if let (Some(i), Some(a)) = (initial, actual) {
            if i.abs() > f64::EPSILON {
                track.initial_vs_actual_pct = Some((a - i) / i.abs() * 100.0);
            }
        }
        track
    }

    /// Check if guidance was met (actual within ±2% of last revised or initial).
    pub fn guidance_met(&self, track: &GuidanceTrack) -> Option<bool> {
        let target = track
            .revised
            .last()
            .or(track.initial.as_ref())
            .map(|g| g.value)?;

        track
            .actual
            .as_ref()
            .map(|a| (a.value - target).abs() / target.abs() * 100.0 <= 2.0)
    }

    // ─── Revenue Quality ──────────────────────────────────────────

    /// Assess revenue quality using simple heuristics.
    /// Flags one-time items and estimates recurring revenue ratio.
    pub fn assess_revenue_quality(
        &self,
        report: &EarningsReport,
        filing_text: Option<&str>,
    ) -> RevenueQuality {
        let mut one_time_indicators = Vec::new();

        if let Some(text) = filing_text {
            let lower = text.to_lowercase();
            let one_time_phrases = [
                "one-time",
                "one time",
                "non-recurring",
                "nonrecurring",
                "extraordinary",
                "asset sale",
                "gain on sale",
                "legal settlement",
                "restructuring charge",
                "impairment charge",
                "write-down",
                "writedown",
                "divestiture",
                "acquisition-related",
            ];
            for phrase in &one_time_phrases {
                if lower.contains(phrase) {
                    one_time_indicators.push(phrase.to_string());
                }
            }
        }

        // Estimate recurring ratio: start at 1.0, reduce for each indicator
        let recurring_ratio = (1.0 - one_time_indicators.len() as f64 * 0.08).clamp(0.3, 1.0);

        // Quality score: also consider if revenue is growing (positive net income)
        let income_factor = report
            .net_income
            .zip(report.revenue)
            .map(|(ni, rev)| if ni > 0.0 && rev > 0.0 { 0.1 } else { 0.0 })
            .unwrap_or(0.0);

        let quality_score = (recurring_ratio + income_factor).clamp(0.0, 1.0);

        RevenueQuality {
            recurring_ratio,
            one_time_indicators,
            quality_score,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn analyzer() -> EarningsAnalyzer {
        EarningsAnalyzer::new()
    }

    #[test]
    fn test_compute_surprise_beat() {
        let a = analyzer();
        let pct = a.compute_surprise(2.00, 2.10);
        assert!(pct > 0.0);
        assert!((pct - 5.0).abs() < 1e-6);
    }

    #[test]
    fn test_compute_surprise_miss() {
        let a = analyzer();
        let pct = a.compute_surprise(2.00, 1.90);
        assert!(pct < 0.0);
        assert!((pct - (-5.0)).abs() < 1e-6);
    }

    #[test]
    fn test_compute_surprise_zero_expected() {
        let a = analyzer();
        let pct = a.compute_surprise(0.0, 1.0);
        assert!((pct).abs() < 1e-10);
    }

    #[test]
    fn test_classify_surprise_beat() {
        let a = analyzer();
        assert_eq!(a.classify_surprise(5.0), BeatMiss::Beat);
        assert_eq!(a.classify_surprise(2.1), BeatMiss::Beat);
    }

    #[test]
    fn test_classify_surprise_miss() {
        let a = analyzer();
        assert_eq!(a.classify_surprise(-5.0), BeatMiss::Miss);
        assert_eq!(a.classify_surprise(-2.1), BeatMiss::Miss);
    }

    #[test]
    fn test_classify_surprise_meet() {
        let a = analyzer();
        assert_eq!(a.classify_surprise(0.0), BeatMiss::Meet);
        assert_eq!(a.classify_surprise(1.0), BeatMiss::Meet);
        assert_eq!(a.classify_surprise(-1.5), BeatMiss::Meet);
    }

    #[test]
    fn test_surprise_result_beat() {
        let a = analyzer();
        let result = a.compute_surprise_result("EPS", 2.00, 2.10);
        assert_eq!(result.beat_miss, BeatMiss::Beat);
        assert!((result.surprise_pct - 5.0).abs() < 1e-6);
    }

    #[test]
    fn test_to_earnings_surprise() {
        let a = analyzer();
        let es = a.to_earnings_surprise("EPS", 2.00, 2.10);
        assert_eq!(es.metric, "EPS");
        assert_eq!(es.beat_miss, BeatMiss::Beat);
    }

    #[test]
    fn test_surprise_from_report() {
        let a = analyzer();
        let mut report = EarningsReport::new("Apple", "AAPL", 1, 2024);
        report.earnings_per_share = Some(2.50);
        report.revenue = Some(100_000.0);
        let results = a.surprise_from_report(&report, Some(2.40), Some(95_000.0));
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].metric, "EPS");
        assert_eq!(results[1].metric, "Revenue");
    }

    #[test]
    fn test_consistency_score_all_beats() {
        let a = analyzer();
        let results = vec![BeatMiss::Beat; 4];
        let cs = a.consistency_score(&results);
        assert_eq!(cs.quarters_analyzed, 4);
        assert_eq!(cs.beat_count, 4);
        assert!((cs.beat_rate - 1.0).abs() < 1e-10);
        assert!((cs.consistency_index - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_consistency_score_mixed() {
        let a = analyzer();
        let results = vec![BeatMiss::Beat, BeatMiss::Miss, BeatMiss::Beat, BeatMiss::Meet];
        let cs = a.consistency_score(&results);
        assert_eq!(cs.beat_count, 2);
        assert_eq!(cs.miss_count, 1);
        assert_eq!(cs.meet_count, 1);
        assert!((cs.beat_rate - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_consistency_score_empty() {
        let a = analyzer();
        let cs = a.consistency_score(&[]);
        assert_eq!(cs.quarters_analyzed, 0);
    }

    #[test]
    fn test_rolling_beat_rate() {
        let a = analyzer();
        let pcts = vec![5.0, -3.0, 8.0, 1.0, 10.0];
        let rate = a.rolling_beat_rate(&pcts, 3);
        // Last 3: 1.0 (meet), 10.0 (beat) → 1 beat / 3 = 0.333
        // Actually: classify(1.0)=Meet, classify(10.0)=Beat, classify(8.0)=Beat
        // Wait, rolling last 3 = [1.0, 10.0] only has 2 elements? No, last 3 of 5 = [8.0, 1.0, 10.0]
        // classify(8.0)=Beat, classify(1.0)=Meet, classify(10.0)=Beat → 2 beats out of 3
        assert!((rate - 2.0 / 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_track_guidance() {
        let a = analyzer();
        let track = a.track_guidance("EPS", Some(2.40), &[2.50], Some(2.55));
        assert!(track.initial.is_some());
        assert_eq!(track.revised.len(), 1);
        assert!(track.actual.is_some());
        assert!(track.initial_vs_actual_pct.is_some());
    }

    #[test]
    fn test_guidance_met() {
        let a = analyzer();
        let track = a.track_guidance("EPS", Some(2.40), &[], Some(2.42));
        assert_eq!(a.guidance_met(&track), Some(true));
    }

    #[test]
    fn test_guidance_missed() {
        let a = analyzer();
        let track = a.track_guidance("EPS", Some(2.40), &[], Some(2.60));
        assert_eq!(a.guidance_met(&track), Some(false));
    }

    #[test]
    fn test_assess_revenue_quality_clean() {
        let a = analyzer();
        let mut report = EarningsReport::new("Co", "T", 1, 2024);
        report.revenue = Some(100.0);
        report.net_income = Some(10.0);
        let rq = a.assess_revenue_quality(&report, Some("Standard quarterly revenue from operations."));
        assert!((rq.recurring_ratio - 1.0).abs() < 1e-10);
        assert!(rq.one_time_indicators.is_empty());
    }

    #[test]
    fn test_assess_revenue_quality_one_time() {
        let a = analyzer();
        let report = EarningsReport::new("Co", "T", 1, 2024);
        let text = "Revenue included a one-time gain from an asset sale and a non-recurring legal settlement.";
        let rq = a.assess_revenue_quality(&report, Some(text));
        assert!(rq.one_time_indicators.len() >= 2);
        assert!(rq.recurring_ratio < 1.0);
    }

    #[test]
    fn test_custom_thresholds() {
        let a = EarningsAnalyzer::with_thresholds(5.0, -5.0);
        assert_eq!(a.classify_surprise(3.0), BeatMiss::Meet); // 3% < 5% threshold
        assert_eq!(a.classify_surprise(6.0), BeatMiss::Beat);
        assert_eq!(a.classify_surprise(-6.0), BeatMiss::Miss);
    }
}
