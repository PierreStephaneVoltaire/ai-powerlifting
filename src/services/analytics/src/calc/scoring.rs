use crate::constants::dots_coefficients;
use crate::util::round;

pub fn dots(total_kg: f64, bodyweight_kg: f64, sex: &str) -> Option<f64> {
    let coefficients = dots_coefficients(&sex.to_lowercase())?;
    if !total_kg.is_finite() || !bodyweight_kg.is_finite() || total_kg < 0.0 || bodyweight_kg <= 0.0
    {
        return None;
    }
    let weight = bodyweight_kg;
    let denominator = coefficients.a
        + coefficients.b * weight
        + coefficients.c * weight.powi(2)
        + coefficients.d * weight.powi(3)
        + coefficients.e * weight.powi(4);
    Some(if denominator.abs() >= 1e-12 {
        round(500.0 * total_kg / denominator, 2)
    } else {
        0.0
    })
}
