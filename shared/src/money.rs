//! Money arithmetic helpers.
//!
//! The Python backend quantizes with `Decimal(str(value))` and
//! `ROUND_HALF_UP`. Rust's shortest float formatting plus manual decimal
//! rounding gives the same result for the values produced by the billing
//! engine (and avoids the banker's rounding of `f64::round`).

/// Round to two decimals, half away from zero (the backend's ROUND_HALF_UP).
pub fn round2(v: f64) -> f64 {
    if !v.is_finite() {
        return v;
    }
    let negative = v < 0.0;
    // `{}` produces the shortest round-trippable decimal, close to Python's str().
    let text = format!("{}", v.abs());
    let (integer, fraction) = match text.split_once('.') {
        Some((a, b)) => (a, b),
        None => (text.as_str(), ""),
    };
    let mut cents: i128 = integer.parse::<i128>().unwrap_or(i128::MAX / 100) * 100;
    let digits = fraction.as_bytes();
    if digits.len() > 0 {
        cents += (digits[0].saturating_sub(b'0')) as i128 * 10;
    }
    if digits.len() > 1 {
        cents += (digits[1].saturating_sub(b'0')) as i128;
    }
    // Third decimal digit decides the half-up step.
    if digits.len() > 2 && digits[2] >= b'5' {
        cents += 1;
    }
    let result = cents as f64 / 100.0;
    if negative { -result } else { result }
}

/// Format as Indian rupees with en-IN digit grouping, e.g. `₹1,23,456.78`.
pub fn format_inr(v: f64) -> String {
    let negative = v < 0.0;
    let cents = (round2(v.abs()) * 100.0).round() as i64;
    let units = cents / 100;
    let paise = cents % 100;
    let digits = units.to_string();
    let bytes = digits.as_bytes();
    let n = bytes.len();

    let grouped = if n <= 3 {
        digits.clone()
    } else {
        let mut parts: Vec<String> = Vec::new();
        parts.push(digits[n - 3..].to_string());
        let mut end = n - 3;
        while end > 2 {
            let start = end - 2;
            parts.push(digits[start..end].to_string());
            end = start;
        }
        parts.push(digits[..end].to_string());
        parts.reverse();
        parts.join(",")
    };

    format!("{}{}.{:02}", if negative { "-₹" } else { "₹" }, grouped, paise)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rounds_half_up_like_decimal() {
        assert_eq!(round2(1.005), 1.01);
        assert_eq!(round2(2.675), 2.68);
        assert_eq!(round2(10.0), 10.0);
        assert_eq!(round2(-1.005), -1.01);
        assert_eq!(round2(0.0), 0.0);
    }

    #[test]
    fn formats_indian_currency() {
        assert_eq!(format_inr(123456.78), "₹1,23,456.78");
        assert_eq!(format_inr(1500.5), "₹1,500.50");
        assert_eq!(format_inr(0.0), "₹0.00");
        assert_eq!(format_inr(-2500.0), "-₹2,500.00");
    }
}
