use crate::classes::Sex;

pub fn round_to(value: f64, digits: usize) -> f64 {
    format!("{value:.digits$}").parse().unwrap_or(value)
}

pub fn round_f32_hundredths(value: f32) -> f32 {
    (value * 100.0).round_ties_even() / 100.0
}

pub fn dots(total_kg: f64, bodyweight_kg: f64, sex: Sex) -> Option<f64> {
    if bodyweight_kg <= 0.0 || total_kg <= 0.0 {
        return None;
    }
    let (a, b, c, d, e) = match sex {
        Sex::Male => (
            -307.75076,
            24.0900756,
            -0.1918759221,
            0.0007391293,
            -0.000001093,
        ),
        Sex::Female => (
            -57.96288,
            13.6175032,
            -0.1126655495,
            0.0005158568,
            -0.0000010706,
        ),
    };
    let denominator = a
        + b * bodyweight_kg
        + c * bodyweight_kg.powf(2.0)
        + d * bodyweight_kg.powf(3.0)
        + e * bodyweight_kg.powf(4.0);
    (denominator != 0.0).then(|| round_to(500.0 / denominator * total_kg, 2))
}

pub fn sum_f32(values: &[f32]) -> f32 {
    let n = values.len();
    if n < 8 {
        return values.iter().fold(0.0, |sum, value| sum + value);
    }
    if n <= 128 {
        let mut lanes = [0.0f32; 8];
        lanes.copy_from_slice(&values[..8]);
        let body = n - n % 8;
        for chunk in values[8..body].chunks_exact(8) {
            for (lane, value) in lanes.iter_mut().zip(chunk) {
                *lane += value;
            }
        }
        let paired = ((lanes[0] + lanes[1]) + (lanes[2] + lanes[3]))
            + ((lanes[4] + lanes[5]) + (lanes[6] + lanes[7]));
        return values[body..].iter().fold(paired, |sum, value| sum + value);
    }
    let mut half = n / 2;
    half -= half % 8;
    sum_f32(&values[..half]) + sum_f32(&values[half..])
}

pub fn mean_f32(values: &[f32]) -> f32 {
    sum_f32(values) / values.len() as f32
}

pub fn median_f32(values: &[f32]) -> f32 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f32::total_cmp);
    let mid = sorted.len() / 2;
    if sorted.len() % 2 == 1 {
        sorted[mid]
    } else {
        (sorted[mid - 1] + sorted[mid]) / 2.0
    }
}

pub fn upper_quartile(values: &[f32]) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f32::total_cmp);
    let position = (sorted.len() - 1) as f64 * 0.75;
    let below = position.floor();
    let gamma = position - below;
    let low = f64::from(sorted[below as usize]);
    let high = f64::from(sorted[(below as usize + 1).min(sorted.len() - 1)]);
    let diff = high - low;
    if gamma >= 0.5 {
        high - diff * (1.0 - gamma)
    } else {
        low + diff * gamma
    }
}

pub fn percent_below(values: &[f32], value: f32) -> i64 {
    let below = values.iter().filter(|v| **v < value).count();
    round_half_even(below as f64 / values.len() as f64 * 100.0)
}

pub fn round_half_even(value: f64) -> i64 {
    value.round_ties_even() as i64
}

pub fn top_quartile_mean(values: &[f32]) -> Option<f64> {
    if values.len() < 10 {
        return None;
    }
    let threshold = upper_quartile(values);
    let top: Vec<f32> = values
        .iter()
        .copied()
        .filter(|v| f64::from(*v) >= threshold)
        .collect();
    (!top.is_empty()).then(|| round_to(f64::from(mean_f32(&top)), 1))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dots_matches_reference_values() {
        assert_eq!(dots(500.0, 83.0, Sex::Male), Some(337.54));
        assert_eq!(dots(0.0, 83.0, Sex::Male), None);
        assert_eq!(dots(300.0, -1.0, Sex::Female), None);
    }

    #[test]
    fn rounding_is_half_even_on_exact_ties() {
        assert_eq!(round_to(0.125, 2), 0.12);
        assert_eq!(round_to(2.675, 2), 2.67);
        assert_eq!(round_half_even(2.5), 2);
        assert_eq!(round_half_even(3.5), 4);
    }

    #[test]
    fn percentile_is_strictly_below() {
        let values: Vec<f32> = (1..=10).map(|v| v as f32).collect();
        assert_eq!(percent_below(&values, 5.0), 40);
        assert_eq!(percent_below(&values, 11.0), 100);
        assert_eq!(percent_below(&values, 1.0), 0);
    }

    #[test]
    fn top_quartile_requires_ten_values() {
        let few: Vec<f32> = (1..=9).map(|v| v as f32).collect();
        assert_eq!(top_quartile_mean(&few), None);
        let values: Vec<f32> = (1..=100).map(|v| v as f32).collect();
        assert_eq!(top_quartile_mean(&values), Some(88.0));
    }

    #[test]
    fn upper_quartile_interpolates_linearly() {
        let values = [1.0f32, 2.0, 3.0, 4.0, 5.0];
        assert_eq!(upper_quartile(&values), 4.0);
        let even = [1.0f32, 2.0, 3.0, 4.0];
        assert!((upper_quartile(&even) - 3.25).abs() < 1e-12);
    }

    #[test]
    fn median_handles_even_and_odd() {
        assert_eq!(median_f32(&[3.0, 1.0, 2.0]), 2.0);
        assert_eq!(median_f32(&[4.0, 1.0, 3.0, 2.0]), 2.5);
    }

    #[test]
    fn pairwise_sum_matches_exact_small_integers() {
        let values: Vec<f32> = (1..=300).map(|v| v as f32).collect();
        assert_eq!(sum_f32(&values), 45150.0);
        assert_eq!(mean_f32(&values), 150.5);
    }

    #[test]
    fn f32_hundredths_rounding() {
        assert_eq!(round_f32_hundredths(98.254), 98.25);
        assert_eq!(round_f32_hundredths(100.0), 100.0);
    }
}
