use std::collections::{BTreeSet, HashMap, HashSet};

use serde_json::{Value, json};
use uuid::Uuid;

pub fn plan(parsed: &Value, glossary: &[Value], athlete: &str) -> Result<Vec<Value>, String> {
    let mut names = BTreeSet::new();
    for session in parsed["sessions"].as_array().into_iter().flatten() {
        for exercise in session["exercises"].as_array().into_iter().flatten() {
            if exercise
                .get("glossary_id")
                .and_then(Value::as_str)
                .is_none_or(str::is_empty)
            {
                if let Some(name) = exercise
                    .get("name")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                {
                    names.insert(name.to_owned());
                }
            }
        }
    }
    let existing: HashSet<String> = glossary
        .iter()
        .filter_map(|item| item.get("name")?.as_str().map(|s| s.to_lowercase()))
        .collect();
    let proposals: HashMap<String, &Value> = parsed["new_exercises"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| Some((item.get("name")?.as_str()?.trim().to_lowercase(), item)))
        .collect();
    let muscles: HashSet<&str> = "quads hamstrings glutes calves tibialis_anterior hip_flexors adductors chest triceps front_delts side_delts rear_delts lats traps rhomboids teres_major biceps forearms erectors lower_back core obliques serratus".split_whitespace().collect();
    let mut result = Vec::new();
    for name in names {
        let key = name.trim().to_lowercase();
        if existing.contains(&key) {
            continue;
        }
        let proposal = proposals
            .get(&key)
            .ok_or_else(|| format!("Missing glossary metadata for {name}; retry the import"))?;
        let profile = &proposal["fatigue_profile"];
        if ["axial", "neural", "peripheral", "systemic"]
            .iter()
            .any(|axis| {
                profile[*axis]
                    .as_f64()
                    .is_none_or(|number| !number.is_finite() || !(0.0..=1.0).contains(&number))
            })
        {
            return Err(format!("Invalid fatigue profile for {name}"));
        }
        let mut seen = HashSet::new();
        for (field, limit) in [
            ("primary_muscles", 4),
            ("secondary_muscles", 5),
            ("tertiary_muscles", 5),
        ] {
            let group = proposal[field]
                .as_array()
                .ok_or_else(|| format!("Invalid muscle groups for {name}"))?;
            if group.len() > limit
                || (field == "primary_muscles" && group.is_empty())
                || group.iter().any(|value| {
                    value.as_str().is_none_or(|muscle| {
                        !muscles.contains(muscle) || !seen.insert(muscle.to_owned())
                    })
                })
            {
                return Err(format!("Invalid muscle groups for {name}"));
            }
        }
        for (field, values) in [
            (
                "category",
                "squat bench deadlift back chest arm legs core lower_back",
            ),
            (
                "equipment",
                "barbell dumbbell cable machine bodyweight hex_bar bands kettlebell",
            ),
            (
                "fatigue_category",
                "primary_axial primary_upper secondary accessory",
            ),
        ] {
            if proposal[field]
                .as_str()
                .is_none_or(|value| !values.split_whitespace().any(|allowed| allowed == value))
            {
                return Err(format!("Missing glossary metadata for {name}"));
            }
        }
        if proposal["fatigue_profile_reasoning"]
            .as_str()
            .is_none_or(|v| v.trim().is_empty())
        {
            return Err(format!("Missing glossary metadata for {name}"));
        }
        result.push(json!({"name":name,"id":Uuid::new_v5(&Uuid::NAMESPACE_URL, format!("nolift-import:{athlete}:{key}").as_bytes()).to_string(),"category":proposal["category"],"fatigue_category":proposal["fatigue_category"],"equipment":proposal["equipment"],"primary_muscles":proposal["primary_muscles"],"secondary_muscles":proposal["secondary_muscles"],"tertiary_muscles":proposal["tertiary_muscles"],"fatigue_profile_reasoning":proposal["fatigue_profile_reasoning"],"fatigue_profile":profile,"fatigue_profile_source":"ai_estimated"}));
    }
    Ok(result)
}

pub fn assign(parsed: &mut Value, created: &HashMap<String, String>) {
    for session in parsed["sessions"].as_array_mut().into_iter().flatten() {
        for exercise in session["exercises"].as_array_mut().into_iter().flatten() {
            if exercise
                .get("glossary_id")
                .and_then(Value::as_str)
                .is_none_or(str::is_empty)
            {
                if let Some(id) = exercise
                    .get("name")
                    .and_then(Value::as_str)
                    .and_then(|name| created.get(name))
                {
                    exercise["glossary_id"] = json!(id);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_incomplete_or_overlapping_muscle_metadata_before_creating() {
        let mut data = json!({"sessions":[{"exercises":[{"name":"Lift"}]}],"new_exercises":[{"name":"Lift","category":"back","equipment":"barbell","fatigue_category":"accessory","fatigue_profile":{"axial":0.1,"neural":0.2,"peripheral":0.3,"systemic":0.4},"fatigue_profile_reasoning":"Reason","primary_muscles":["lats"],"secondary_muscles":[],"tertiary_muscles":[]}]});
        let first = plan(&data, &[], "athlete").unwrap();
        assert_eq!(first.len(), 1);
        assert_eq!(
            first[0]["id"],
            plan(&data, &[], "athlete").unwrap()[0]["id"]
        );
        data["new_exercises"][0]["secondary_muscles"] = json!(["lats"]);
        assert!(plan(&data, &[], "athlete").is_err());
    }
}
