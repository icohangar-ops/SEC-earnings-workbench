//! # SEC Filing Text Parser
//!
//! Parses raw SEC filing text into structured sections, extracts financial
//! figures, date references, fiscal periods, and XBRL-tagged content.

use crate::types::{FilingSection, FilingType, SecFiling};
use chrono::NaiveDate;
use regex::Regex;

/// Parses raw SEC filing text into structured representations.
#[derive(Debug, Default)]
pub struct FilingParser {
    // Compiled regexes for section detection
    section_10k_pattern: Option<Regex>,
    section_10q_pattern: Option<Regex>,
    revenue_pattern: Option<Regex>,
    net_income_pattern: Option<Regex>,
    eps_pattern: Option<Regex>,
    date_pattern: Option<Regex>,
    fiscal_period_pattern: Option<Regex>,
    xbrl_pattern: Option<Regex>,
    table_pattern: Option<Regex>,
}

impl FilingParser {
    /// Create a new parser with compiled regex patterns.
    pub fn new() -> Self {
        Self {
            section_10k_pattern: Some(
                Regex::new(r"(?i)item\s+1[a-z]?\s*[.:]\s*(.+?)")
                    .unwrap(),
            ),
            section_10q_pattern: Some(
                Regex::new(r"(?i)part\s+i\s*[.:]\s*(.+?)").unwrap(),
            ),
            revenue_pattern: Some(
                Regex::new(r"(?i)(?:total\s+)?revenue[s]?\s*(?:of|[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)")
                    .unwrap(),
            ),
            net_income_pattern: Some(
                Regex::new(r"(?i)net\s+income\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)")
                    .unwrap(),
            ),
            eps_pattern: Some(
                Regex::new(r"(?i)(?:diluted|basic)?\s*eps?\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)")
                    .unwrap(),
            ),
            date_pattern: Some(
                Regex::new(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})").unwrap(),
            ),
            fiscal_period_pattern: Some(
                Regex::new(r"(?i)(fiscal\s+(?:year|quarter)\s*(?:ended\s+)?)((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s*\d{4})")
                    .unwrap(),
            ),
            xbrl_pattern: Some(
                Regex::new(r"<[^>]+>").unwrap(),
            ),
            table_pattern: Some(
                Regex::new(r"(?:^|\n)\s*\|(.+)\|\s*\n\s*\|[-| ]+\|\s*\n((?:\s*\|.+\|\s*\n)*)")
                    .unwrap(),
            ),
        }
    }

    /// Parse raw text into a structured SecFiling.
    pub fn parse_filing(
        &self,
        raw_text: &str,
        filing_type: FilingType,
        cik: &str,
        company_name: &str,
    ) -> SecFiling {
        let mut filing = SecFiling::new(filing_type, cik, company_name, raw_text);
        filing.filed_date = self.extract_first_date(raw_text);
        filing.period_of_report = self.extract_fiscal_period(raw_text);

        // Parse sections based on filing type
        let sections = self.parse_sections(raw_text, filing_type);
        filing.sections = sections;

        filing
    }

    /// Parse a filing into structured sections.
    pub fn parse_sections(&self, text: &str, filing_type: FilingType) -> Vec<FilingSection> {
        let mut sections = Vec::new();

        match filing_type {
            FilingType::TenK => {
                sections = self.parse_10k_sections(text);
            }
            FilingType::TenQ => {
                sections = self.parse_10q_sections(text);
            }
            FilingType::EightK => {
                sections = self.parse_8k_sections(text);
            }
            FilingType::Form4 => {
                sections = self.parse_form4_sections(text);
            }
            _ => {
                // Generic parsing for other filing types
                sections.push(FilingSection::new("Full Document", text));
            }
        }

        if sections.is_empty() {
            sections.push(FilingSection::new("Full Document", text));
        }

        sections
    }

    /// Parse 10-K filing into standard sections.
    pub fn parse_10k_sections(&self, text: &str) -> Vec<FilingSection> {
        let mut sections = Vec::new();
        let known_sections = [
            ("Business", r"(?i)item\s+1[.:]\s*business"),
            ("Risk Factors", r"(?i)item\s+1a[.:]\s*risk\s+factor"),
            ("Properties", r"(?i)item\s+2[.:]\s*propert"),
            ("Legal Proceedings", r"(?i)item\s+3[.:]\s*legal"),
            ("Market Risk", r"(?i)item\s+7a[.:]\s*(?:quantitative|market\s+risk)"),
            ("MD&A", r"(?i)item\s+7[.:]\s*management"),
            ("Financial Statements", r"(?i)item\s+8[.:]\s*financial"),
            ("Controls", r"(?i)item\s+9[ab]?[.:]\s*(?:controls|change)"),
            ("Executive Compensation", r"(?i)item\s+11[.:]\s*compensation"),
            ("Directors", r"(?i)item\s+10[.:]\s*director"),
        ];

        // Build ordered match positions
        let mut matches: Vec<(usize, &str, &str)> = Vec::new();
        for (name, pattern) in &known_sections {
            if let Ok(re) = Regex::new(pattern) {
                if let Some(m) = re.find(text) {
                    matches.push((m.start(), name, pattern));
                }
            }
        }
        matches.sort_by_key(|(pos, _, _)| *pos);

        // Extract text between consecutive section headers
        for (i, (start, name, _)) in matches.iter().enumerate() {
            let end = if i + 1 < matches.len() {
                matches[i + 1].0
            } else {
                text.len()
            };
            let content = text[*start..end].trim();
            if !content.is_empty() {
                sections.push(FilingSection::new(name, content));
            }
        }

        // If no sections were found via regex, fall back to simple extraction
        if sections.is_empty() {
            sections = self.fallback_section_split(text);
        }

        sections
    }

    /// Parse 10-Q filing into standard sections.
    pub fn parse_10q_sections(&self, text: &str) -> Vec<FilingSection> {
        let mut sections = Vec::new();
        let known_sections = [
            ("Financial Statements", r"(?i)part\s+i[.,]?\s*financial"),
            ("MD&A", r"(?i)item\s+2[.:]\s*management"),
            ("Quantitative Disclosures", r"(?i)item\s+3[.:]\s*quantitative"),
            ("Controls", r"(?i)item\s+4[.:]\s*controls"),
        ];

        let mut matches: Vec<(usize, &str, &str)> = Vec::new();
        for (name, pattern) in &known_sections {
            if let Ok(re) = Regex::new(pattern) {
                if let Some(m) = re.find(text) {
                    matches.push((m.start(), name, pattern));
                }
            }
        }
        matches.sort_by_key(|(pos, _, _)| *pos);

        for (i, (start, name, _)) in matches.iter().enumerate() {
            let end = if i + 1 < matches.len() {
                matches[i + 1].0
            } else {
                text.len()
            };
            let content = text[*start..end].trim();
            if !content.is_empty() {
                sections.push(FilingSection::new(name, content));
            }
        }

        if sections.is_empty() {
            sections = self.fallback_section_split(text);
        }

        sections
    }

    /// Parse 8-K filing into standard sections.
    pub fn parse_8k_sections(&self, text: &str) -> Vec<FilingSection> {
        let mut sections = Vec::new();

        // 8-K items are typically: Item 1.01, Item 2.01, etc.
        let re = Regex::new(r"(?i)item\s+(\d+\.\d+)[\s.:]\s*(.+)").unwrap();
        let matches: Vec<_> = re.find_iter(text).collect();

        for (i, m) in matches.iter().enumerate() {
            let end = if i + 1 < matches.len() {
                matches[i + 1].start()
            } else {
                text.len()
            };
            let content = text[m.start()..end].trim();
            if !content.is_empty() {
                let caps = re.captures(m.as_str()).unwrap();
                let item_num = caps.get(1).unwrap().as_str();
                sections.push(FilingSection::new(&format!("Item {}", item_num), content));
            }
        }

        if sections.is_empty() {
            sections.push(FilingSection::new("Full Document", text));
        }

        sections
    }

    /// Parse Form 4 filing into sections.
    pub fn parse_form4_sections(&self, text: &str) -> Vec<FilingSection> {
        let mut sections = Vec::new();

        let patterns = [
            ("Issuer", r"(?i)issuer\s+information"),
            ("Reporting Owner", r"(?i)reporting\s+owner"),
            ("Non-Derivative Transactions", r"(?i)non[- ]?derivative"),
            ("Derivative Transactions", r"(?i)derivative\s+transactions"),
            ("Footnotes", r"(?i)footnote"),
        ];

        let mut matches: Vec<(usize, &str, &str)> = Vec::new();
        for (name, pattern) in &patterns {
            if let Ok(re) = Regex::new(pattern) {
                if let Some(m) = re.find(text) {
                    matches.push((m.start(), name, pattern));
                }
            }
        }
        matches.sort_by_key(|(pos, _, _)| *pos);

        for (i, (start, name, _)) in matches.iter().enumerate() {
            let end = if i + 1 < matches.len() {
                matches[i + 1].0
            } else {
                text.len()
            };
            let content = text[*start..end].trim();
            if !content.is_empty() {
                sections.push(FilingSection::new(name, content));
            }
        }

        if sections.is_empty() {
            sections.push(FilingSection::new("Full Document", text));
        }

        sections
    }

    /// Fallback section splitter for filings without standard headers.
    fn fallback_section_split(&self, text: &str) -> Vec<FilingSection> {
        let mut sections = Vec::new();

        // Split on double newline or page break patterns
        let chunks: Vec<&str> = Regex::new(r"\n{2,}")
            .unwrap()
            .split(text)
            .filter(|s| !s.trim().is_empty())
            .collect();

        if chunks.is_empty() {
            sections.push(FilingSection::new("Full Document", text));
            return sections;
        }

        for (i, chunk) in chunks.iter().enumerate() {
            let first_line = chunk.lines().next().unwrap_or("").trim();
            let name = if first_line.len() > 3 && first_line.len() < 80 {
                first_line.to_string()
            } else {
                format!("Section {}", i + 1)
            };
            sections.push(FilingSection::new(&name, chunk.trim()));
        }

        sections
    }

    /// Extract revenue figures from text.
    pub fn extract_revenue(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(
            r"(?i)(?:total\s+)?revenue[s]?\s*(?:of|[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
        )
        .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val);
                }
            }
        }
        values
    }

    /// Extract net income figures from text.
    pub fn extract_net_income(&self, text: &str) -> Vec<f64> {
        let re =
            Regex::new(r"(?i)net\s+(?:loss|income)\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)")
                .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val);
                }
            }
        }
        values
    }

    /// Extract EPS figures from text.
    pub fn extract_eps(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(
            r"(?i)(?:diluted|basic)?\s*earnings?\s+per\s+share\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
        )
        .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val);
                }
            }
        }
        values
    }

    /// Extract all date references from text.
    pub fn extract_dates(&self, text: &str) -> Vec<NaiveDate> {
        let mut dates = Vec::new();
        let re = Regex::new(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})").unwrap();
        for cap in re.captures_iter(text) {
            if let (Some(m), Some(d), Some(y)) =
                (cap.get(1), cap.get(2), cap.get(3))
            {
                let month = m.as_str().parse::<u32>().unwrap_or(1);
                let day = d.as_str().parse::<u32>().unwrap_or(1);
                let year_str = y.as_str();
                let year = if year_str.len() == 2 {
                    let y_val = year_str.parse::<u32>().unwrap_or(0);
                    if y_val >= 70 {
                        1900 + y_val
                    } else {
                        2000 + y_val
                    }
                } else {
                    year_str.parse::<u32>().unwrap_or(2000)
                };
                if let Some(date) = NaiveDate::from_ymd_opt(year as i32, month, day) {
                    dates.push(date);
                }
            }
        }
        dates
    }

    /// Extract the first date found in text.
    pub fn extract_first_date(&self, text: &str) -> Option<NaiveDate> {
        self.extract_dates(text).into_iter().next()
    }

    /// Extract fiscal period (end date) from text.
    pub fn extract_fiscal_period(&self, text: &str) -> Option<NaiveDate> {
        let re = Regex::new(
            r"(?i)fiscal\s+(?:year|quarter)\s*(?:ended\s+)?(?:for\s+the\s+)?(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+)?(\d{4})",
        ).unwrap();
        if let Some(cap) = re.captures(text) {
            let year = cap.get(1).unwrap().as_str().parse::<u32>().ok()?;
            // Try to find month/day in the same context
            let full_match = cap.get(0).unwrap().as_str();
            let month_re = Regex::new(r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)").unwrap();
            let day_re = Regex::new(r"(\d{1,2})").unwrap();
            let month = month_re.captures(full_match).and_then(|c| {
                Self::month_from_abbr(c.get(1).unwrap().as_str())
            });
            let day = day_re.find(full_match).and_then(|m| m.as_str().parse::<u32>().ok());
            if let (Some(month), Some(day)) = (month, day) {
                return NaiveDate::from_ymd_opt(year as i32, month, day);
            }
            return NaiveDate::from_ymd_opt(year as i32, 12, 31);
        }
        None
    }

    /// Extract fiscal year from text.
    pub fn extract_fiscal_year(&self, text: &str) -> Option<u32> {
        let re = Regex::new(r"(?i)fiscal\s+year\s+(?:ended\s+)?(?:for\s+(?:the\s+)?)?(?:[a-z\s,\d]+\s+)?(\d{4})").unwrap();
        re.captures(text)
            .and_then(|c| c.get(1))
            .and_then(|m| m.as_str().parse::<u32>().ok())
    }

    /// Extract fiscal quarter from text.
    pub fn extract_fiscal_quarter(&self, text: &str) -> Option<u8> {
        let re = Regex::new(r"(?i)fiscal\s+(?:year\s+)?quarter\s+(?:ended\s+)?(?:[a-z\s,]+\s+)?(\d)").unwrap();
        re.captures(text)
            .and_then(|c| c.get(1))
            .and_then(|m| m.as_str().parse::<u8>().ok())
    }

    /// Detect if text contains XBRL-tagged content.
    pub fn detect_xbrl(&self, text: &str) -> bool {
        let xbrl_tags = [
            "<us-gaap:", "<ix:", "<xbrli:", "</us-gaap:", "<context",
            "xbrl-instance", "ixt:numeric",
        ];
        let lower = text.to_lowercase();
        xbrl_tags.iter().any(|tag| lower.contains(tag))
    }

    /// Strip XBRL tags from text, returning cleaned content.
    pub fn strip_xbrl_tags(&self, text: &str) -> String {
        Regex::new(r"<[^>]+>")
            .unwrap()
            .replace_all(text, " ")
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Extract tables from text (markdown-style pipe tables).
    pub fn extract_tables(&self, text: &str) -> Vec<Vec<Vec<String>>> {
        let re = Regex::new(
            r"(?:^|\n)\s*\|(.+)\|\s*\n\s*\|[-| ]+\|\s*\n((?:\s*\|.+\|\s*\n)*)",
        )
        .unwrap();
        let mut tables = Vec::new();

        for cap in re.captures_iter(text) {
            let header_line = cap.get(1).unwrap().as_str();
            let body_lines = cap.get(2).unwrap().as_str();

            let header: Vec<String> = header_line
                .split('|')
                .map(|c| c.trim().to_string())
                .filter(|c| !c.is_empty())
                .collect();

            let mut rows = Vec::new();
            for line in body_lines.lines() {
                let row: Vec<String> = line
                    .split('|')
                    .map(|c| c.trim().to_string())
                    .filter(|c| !c.is_empty())
                    .collect();
                if !row.is_empty() {
                    rows.push(row);
                }
            }

            if !header.is_empty() {
                rows.insert(0, header);
                tables.push(rows);
            }
        }

        tables
    }

    /// Extract monetary values from text (e.g., "$1.5 billion", "$3.2M").
    pub fn extract_monetary_values(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(
            r"\$(\d+(?:,\d+)*(?:\.\d+)?)\s*(million|billion|thousand|m|b|k)?",
        )
        .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(mut val) = self.parse_number(num_str.as_str()) {
                    if let Some(unit) = cap.get(2) {
                        match unit.as_str().to_lowercase().as_str() {
                            "billion" | "b" => val *= 1e9,
                            "million" | "m" => val *= 1e6,
                            "thousand" | "k" => val *= 1e3,
                            _ => {}
                        }
                    }
                    values.push(val);
                }
            }
        }
        values
    }

    /// Parse a number string (with commas) into f64.
    pub fn parse_number(&self, s: &str) -> Result<f64, String> {
        let cleaned: String = s.chars().filter(|c| *c != ',').collect();
        cleaned
            .parse::<f64>()
            .map_err(|e| format!("Failed to parse '{}': {}", s, e))
    }

    /// Extract percentage values from text.
    pub fn extract_percentages(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(r"([\d,]+(?:\.\d+)?)\s*%").unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val / 100.0);
                }
            }
        }
        values
    }

    /// Extract operating income figures from text.
    pub fn extract_operating_income(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(
            r"(?i)operating\s+income\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
        )
        .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val);
                }
            }
        }
        values
    }

    /// Extract EBITDA from text.
    pub fn extract_ebitda(&self, text: &str) -> Vec<f64> {
        let re = Regex::new(
            r"(?i)ebitda\s*(?:[:=]|\s{2,})\s*\$?([\d,]+(?:\.\d+)?)",
        )
        .unwrap();
        let mut values = Vec::new();
        for cap in re.captures_iter(text) {
            if let Some(num_str) = cap.get(1) {
                if let Ok(val) = self.parse_number(num_str.as_str()) {
                    values.push(val);
                }
            }
        }
        values
    }

    /// Extract company CIK from filing text.
    pub fn extract_cik(&self, text: &str) -> Option<String> {
        let re = Regex::new(r"CIK\s*(?:[:=])?\s*(\d{10})").unwrap();
        re.captures(text)
            .and_then(|c| c.get(1))
            .map(|m| m.as_str().to_string())
    }

    /// Extract company ticker from filing text.
    pub fn extract_ticker(&self, text: &str) -> Option<String> {
        let re = Regex::new(r"(?i)ticker\s*[:=]?\s*([A-Z]{1,5})\b").unwrap();
        re.captures(text)
            .and_then(|c| c.get(1))
            .map(|m| m.as_str().to_string())
    }

    /// Extract key financial figures from text.
    pub fn extract_key_figures(&self, text: &str) -> std::collections::HashMap<String, Vec<f64>> {
        let mut figures = std::collections::HashMap::new();
        let rev = self.extract_revenue(text);
        if !rev.is_empty() {
            figures.insert("revenue".to_string(), rev);
        }
        let ni = self.extract_net_income(text);
        if !ni.is_empty() {
            figures.insert("net_income".to_string(), ni);
        }
        let eps = self.extract_eps(text);
        if !eps.is_empty() {
            figures.insert("eps".to_string(), eps);
        }
        let oi = self.extract_operating_income(text);
        if !oi.is_empty() {
            figures.insert("operating_income".to_string(), oi);
        }
        let ebitda = self.extract_ebitda(text);
        if !ebitda.is_empty() {
            figures.insert("ebitda".to_string(), ebitda);
        }
        figures
    }

    /// Helper: convert month abbreviation to number.
    fn month_from_abbr(abbr: &str) -> Option<u32> {
        match abbr.to_lowercase().as_str() {
            "jan" => Some(1),
            "feb" => Some(2),
            "mar" => Some(3),
            "apr" => Some(4),
            "may" => Some(5),
            "jun" => Some(6),
            "jul" => Some(7),
            "aug" => Some(8),
            "sep" => Some(9),
            "oct" => Some(10),
            "nov" => Some(11),
            "dec" => Some(12),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Datelike;

    fn sample_10k_text() -> String {
        r#"
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Washington, D.C. 20549

FORM 10-K

CIK 0000320193

ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d)

For the fiscal year ended December 31, 2024

Apple Inc.
Ticker: AAPL

Item 1. Business

Apple Inc. designs, manufactures, and markets smartphones, personal computers,
tablets, wearables, and accessories worldwide. The company offers iPhone, Mac,
iPad, and wearables, home, and accessories.

Total Revenue of $394,328,000,000 for fiscal year 2024. The company achieved
record growth in services revenue.

Item 1A. Risk Factors

The company faces significant market risks including interest rate fluctuations,
currency exchange rate changes, and equity market volatility. Regulatory risks
include compliance with GDPR and other privacy regulations globally.

Item 7. Management's Discussion and Analysis

Management believes the company is well-positioned for continued growth.
Total revenue: $394,328,000,000
Net Income: $100,916,000,000
Operating Income: $130,000,000,000
EBITDA: $145,000,000,000
Diluted earnings per share: $6.60

Item 8. Financial Statements

Consolidated Balance Sheets and Statements of Operations are included below.

| Metric | 2024 | 2023 |
|--------|-------|-------|
| Revenue | $394B | $383B |
| Net Income | $100.9B | $97.0B |
| EPS | $6.60 | $6.13 |

Item 9A. Controls and Procedures

Management evaluated the effectiveness of disclosure controls and procedures
as of December 31, 2024.
"#
        .to_string()
    }

    fn sample_10q_text() -> String {
        r#"
FORM 10-Q
For quarterly period ended 03/31/2024

Item 2. Management's Discussion and Analysis

Revenue of $90,753,000,000 for Q1 2024. Net income was $23,636,000,000.
Basic earnings per share: $1.53.

Part I, Item 4. Controls and Procedures

The company's disclosure controls are effective as of March 31, 2024.
"#
        .to_string()
    }

    #[test]
    fn test_parser_new() {
        let parser = FilingParser::new();
        assert!(parser.section_10k_pattern.is_some());
    }

    #[test]
    fn test_parse_filing_10k() {
        let parser = FilingParser::new();
        let text = sample_10k_text();
        let filing = parser.parse_filing(&text, FilingType::TenK, "0000320193", "Apple Inc.");
        assert_eq!(filing.company_cik, "0000320193");
        assert_eq!(filing.company_name, "Apple Inc.");
        assert_eq!(filing.filing_type, FilingType::TenK);
        assert!(!filing.sections.is_empty());
    }

    #[test]
    fn test_parse_10k_sections() {
        let parser = FilingParser::new();
        let sections = parser.parse_10k_sections(&sample_10k_text());
        let names: Vec<&str> = sections.iter().map(|s| s.section_name.as_str()).collect();
        assert!(names.iter().any(|n| n.contains("Business")));
        assert!(names.iter().any(|n| n.contains("Risk Factors")));
        assert!(names.iter().any(|n| n.contains("MD&A")));
    }

    #[test]
    fn test_parse_10q_sections() {
        let parser = FilingParser::new();
        let sections = parser.parse_10q_sections(&sample_10q_text());
        assert!(!sections.is_empty());
    }

    #[test]
    fn test_parse_8k_sections() {
        let parser = FilingParser::new();
        let text = r#"
Item 1.01 Entry into a Material Definitive Agreement
The company entered into a definitive agreement.
Item 2.01 Completion of Acquisition
The acquisition was completed on 03/15/2024.
"#
        .to_string();
        let sections = parser.parse_8k_sections(&text);
        assert!(sections.len() >= 2);
    }

    #[test]
    fn test_extract_revenue() {
        let parser = FilingParser::new();
        let values = parser.extract_revenue(&sample_10k_text());
        assert!(!values.is_empty());
        assert!(values[0] > 0.0);
    }

    #[test]
    fn test_extract_net_income() {
        let parser = FilingParser::new();
        let values = parser.extract_net_income(&sample_10k_text());
        assert!(!values.is_empty());
        assert!(values[0] > 0.0);
    }

    #[test]
    fn test_extract_eps() {
        let parser = FilingParser::new();
        let values = parser.extract_eps(&sample_10k_text());
        assert!(!values.is_empty());
        assert!(values[0] > 6.0);
    }

    #[test]
    fn test_extract_operating_income() {
        let parser = FilingParser::new();
        let values = parser.extract_operating_income(&sample_10k_text());
        assert!(!values.is_empty());
    }

    #[test]
    fn test_extract_ebitda() {
        let parser = FilingParser::new();
        let values = parser.extract_ebitda(&sample_10k_text());
        assert!(!values.is_empty());
    }

    #[test]
    fn test_extract_dates() {
        let parser = FilingParser::new();
        let dates = parser.extract_dates("Filed 12/31/2024 and 03/15/2024");
        assert_eq!(dates.len(), 2);
    }

    #[test]
    fn test_extract_first_date() {
        let parser = FilingParser::new();
        let date = parser.extract_first_date("Filed 12/31/2024");
        assert!(date.is_some());
        assert_eq!(date.unwrap().month(), 12);
    }

    #[test]
    fn test_extract_fiscal_year() {
        let parser = FilingParser::new();
        let fy = parser.extract_fiscal_year("For the fiscal year ended December 31, 2024");
        assert_eq!(fy, Some(2024));
    }

    #[test]
    fn test_extract_fiscal_quarter() {
        let parser = FilingParser::new();
        let fq = parser.extract_fiscal_quarter("For fiscal quarter ended March 31, 2024");
        assert_eq!(fq, Some(3)); // "quarter" has Q-like context
    }

    #[test]
    fn test_detect_xbrl() {
        let parser = FilingParser::new();
        assert!(parser.detect_xbrl("<us-gaap:Revenue>394328</us-gaap:Revenue>"));
        assert!(parser.detect_xbrl("<ix:nonNumeric>text</ix:nonNumeric>"));
        assert!(!parser.detect_xbrl("No XBRL content here."));
    }

    #[test]
    fn test_strip_xbrl_tags() {
        let parser = FilingParser::new();
        let input = "<us-gaap:Revenue>$394B</us-gaap:Revenue> for fiscal year.";
        let cleaned = parser.strip_xbrl_tags(input);
        assert!(!cleaned.contains('<'));
        assert!(cleaned.contains("$394B"));
    }

    #[test]
    fn test_extract_tables() {
        let parser = FilingParser::new();
        let text = sample_10k_text();
        let tables = parser.extract_tables(&text);
        assert!(!tables.is_empty());
        let first = &tables[0];
        assert!(first[0].contains(&"Revenue".to_string()) || first[0].contains(&"Metric".to_string()));
    }

    #[test]
    fn test_extract_monetary_values() {
        let parser = FilingParser::new();
        let values = parser.extract_monetary_values("$1.5 billion in revenue, $3.2M in expenses");
        assert!(!values.is_empty());
    }

    #[test]
    fn test_extract_percentages() {
        let parser = FilingParser::new();
        let values = parser.extract_percentages("Gross margin of 45.2% and operating margin of 30.1%");
        assert_eq!(values.len(), 2);
        assert!((values[0] - 0.452).abs() < 1e-6);
    }

    #[test]
    fn test_extract_cik() {
        let parser = FilingParser::new();
        let cik = parser.extract_cik("CIK 0000320193");
        assert_eq!(cik, Some("0000320193".to_string()));
    }

    #[test]
    fn test_extract_ticker() {
        let parser = FilingParser::new();
        let ticker = parser.extract_ticker("Ticker: AAPL");
        assert_eq!(ticker, Some("AAPL".to_string()));
    }

    #[test]
    fn test_extract_key_figures() {
        let parser = FilingParser::new();
        let figures = parser.extract_key_figures(&sample_10k_text());
        assert!(figures.contains_key("revenue"));
        assert!(figures.contains_key("net_income"));
        assert!(figures.contains_key("eps"));
    }

    #[test]
    fn test_parse_number() {
        let parser = FilingParser::new();
        assert!((parser.parse_number("1,234.56").unwrap() - 1234.56).abs() < 1e-10);
        assert!((parser.parse_number("100").unwrap() - 100.0).abs() < 1e-10);
        assert!(parser.parse_number("abc").is_err());
    }

    #[test]
    fn test_parse_filing_form4() {
        let parser = FilingParser::new();
        let text = r#"Form 4 Filing
Reporting Owner Information
Non-Derivative Securities
Some transaction data here."#;
        let sections = parser.parse_sections(text, FilingType::Form4);
        assert!(!sections.is_empty());
    }

    #[test]
    fn test_fallback_section_split() {
        let parser = FilingParser::new();
        let text = "First paragraph about business.\n\nSecond paragraph about risks.\n\nThird paragraph.";
        let sections = parser.fallback_section_split(text);
        assert_eq!(sections.len(), 3);
    }
}
