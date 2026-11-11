#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Sex {
    Male,
    Female,
}

impl Sex {
    pub fn from_code(code: &str) -> Option<Self> {
        match code {
            "M" => Some(Self::Male),
            "F" => Some(Self::Female),
            _ => None,
        }
    }

    fn classes(self) -> &'static [f64; 8] {
        match self {
            Self::Male => &[59.0, 66.0, 74.0, 83.0, 93.0, 105.0, 120.0, f64::INFINITY],
            Self::Female => &[47.0, 52.0, 57.0, 63.0, 69.0, 76.0, 84.0, f64::INFINITY],
        }
    }
}

fn class_index(classes: &[f64; 8], bodyweight: f64) -> usize {
    classes
        .iter()
        .position(|limit| bodyweight <= *limit)
        .unwrap_or(classes.len() - 1)
}

pub fn bounds(bodyweight: f64, sex: Sex) -> (f64, f64) {
    let classes = sex.classes();
    if bodyweight <= 0.0 {
        return (0.0, f64::INFINITY);
    }
    let index = class_index(classes, bodyweight);
    let start = index.saturating_sub(1);
    let end = (index + 1).min(classes.len() - 1);
    let lower = if start > 0 { classes[start - 1] } else { 0.0 };
    (lower, classes[end])
}

pub fn label(bodyweight: f64, sex: Sex) -> String {
    let classes = sex.classes();
    let limit = classes[class_index(classes, bodyweight)];
    if limit.is_finite() {
        format!("{}kg", limit as i64)
    } else {
        format!("{}kg+", classes[classes.len() - 2] as i64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn middle_class_spans_neighbours() {
        assert_eq!(bounds(78.0, Sex::Male), (66.0, 93.0));
    }

    #[test]
    fn lightest_class_has_zero_lower_bound() {
        assert_eq!(bounds(55.0, Sex::Male), (0.0, 66.0));
        assert_eq!(bounds(59.0, Sex::Male), (0.0, 66.0));
    }

    #[test]
    fn heaviest_class_is_unbounded() {
        let (lower, upper) = bounds(150.0, Sex::Male);
        assert_eq!(lower, 105.0);
        assert!(upper.is_infinite());
    }

    #[test]
    fn labels_follow_ipf_limits() {
        assert_eq!(label(82.5, Sex::Male), "83kg");
        assert_eq!(label(130.0, Sex::Male), "120kg+");
        assert_eq!(label(60.0, Sex::Female), "63kg");
        assert_eq!(label(100.0, Sex::Female), "84kg+");
    }

    #[test]
    fn sex_codes() {
        assert_eq!(Sex::from_code("M"), Some(Sex::Male));
        assert_eq!(Sex::from_code("X"), None);
    }
}
