use std::collections::HashMap;

use serde_json::{Map, Value, json};

const SHARED_FIELDS: [&str; 13] = [
    "name",
    "category",
    "fatigue_category",
    "equipment",
    "video_url",
    "lift_transfer",
    "description",
    "how_to_perform",
    "why_do_it",
    "primary_muscles",
    "secondary_muscles",
    "tertiary_muscles",
    "generic_status",
];

const PERSONAL_FIELDS: [&str; 5] = [
    "fatigue_profile",
    "fatigue_profile_source",
    "fatigue_profile_reasoning",
    "e1rm_estimate",
    "archived",
];

fn id_of(item: &Value) -> Option<&str> {
    item.get("id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
}

fn flag(item: Option<&Value>, key: &str) -> bool {
    item.and_then(|item| item.get(key))
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

fn merge(catalog: Option<&Value>, overlay: Option<&Value>) -> Value {
    let mut effective = Map::new();
    let copy = |effective: &mut Map<String, Value>, source: Option<&Value>, keys: &[&str]| {
        for key in keys {
            if let Some(value) = source.and_then(|source| source.get(*key)) {
                effective.insert((*key).to_owned(), value.clone());
            }
        }
    };
    copy(&mut effective, catalog, &SHARED_FIELDS);
    copy(&mut effective, overlay, &SHARED_FIELDS);
    copy(&mut effective, overlay, &PERSONAL_FIELDS);
    if let Some(id) = overlay.and_then(id_of).or_else(|| catalog.and_then(id_of)) {
        effective.insert("id".to_owned(), json!(id));
    }
    let personal = overlay.and_then(|overlay| overlay.get("fatigue_profile"));
    if personal.is_none()
        && let Some(generic) = catalog.and_then(|catalog| catalog.get("fatigue_profile"))
    {
        effective.insert("fatigue_profile".to_owned(), generic.clone());
        copy(
            &mut effective,
            catalog,
            &["fatigue_profile_source", "fatigue_profile_reasoning"],
        );
    }
    Value::Object(effective)
}

pub fn effective_exercises(catalog: Vec<Value>, overlays: Vec<Value>) -> Value {
    let mut order: Vec<String> = Vec::new();
    let mut shared: HashMap<String, Value> = HashMap::new();
    for item in catalog {
        if let Some(id) = id_of(&item).map(str::to_owned) {
            order.push(id.clone());
            shared.insert(id, item);
        }
    }
    let mut personal: HashMap<String, Value> = HashMap::new();
    for item in overlays {
        let Some(id) = id_of(&item).map(str::to_owned) else {
            continue;
        };
        if !shared.contains_key(&id) {
            if !flag(Some(&item), "custom") {
                continue;
            }
            order.push(id.clone());
        }
        personal.insert(id, item);
    }
    let exercises: Vec<Value> = order
        .iter()
        .filter(|id| !flag(personal.get(*id), "hidden"))
        .map(|id| merge(shared.get(id), personal.get(id)))
        .collect();
    json!({ "exercises": exercises })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile(axial: f64) -> Value {
        json!({"axial": axial, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0})
    }

    #[test]
    fn overlay_wins_field_by_field() {
        let catalog = vec![json!({
            "id": "a", "name": "Squat", "category": "primary_compound",
            "primary_muscles": ["quads"], "fatigue_profile": profile(0.1),
            "fatigue_profile_source": "ai_generic"
        })];
        let overlays = vec![json!({
            "id": "a", "category": "secondary_compound", "e1rm_estimate": {"kg": 200.0},
            "archived": true
        })];
        let out = effective_exercises(catalog, overlays);
        let item = &out["exercises"][0];
        assert_eq!(item["name"], "Squat");
        assert_eq!(item["category"], "secondary_compound");
        assert_eq!(item["primary_muscles"], json!(["quads"]));
        assert_eq!(item["e1rm_estimate"], json!({"kg": 200.0}));
        assert_eq!(item["archived"], true);
        assert_eq!(item["fatigue_profile"], profile(0.1));
        assert_eq!(item["fatigue_profile_source"], "ai_generic");
    }

    #[test]
    fn personal_fatigue_profile_replaces_generic() {
        let catalog = vec![json!({
            "id": "a", "name": "Squat", "fatigue_profile": profile(0.1),
            "fatigue_profile_source": "ai_generic"
        })];
        let overlays = vec![json!({
            "id": "a", "fatigue_profile": profile(0.9), "fatigue_profile_source": "ai_personal"
        })];
        let out = effective_exercises(catalog, overlays);
        let item = &out["exercises"][0];
        assert_eq!(item["fatigue_profile"], profile(0.9));
        assert_eq!(item["fatigue_profile_source"], "ai_personal");
    }

    #[test]
    fn hidden_is_excluded_and_uncatalogued_overlay_needs_custom() {
        let catalog = vec![
            json!({"id": "a", "name": "A"}),
            json!({"id": "b", "name": "B"}),
        ];
        let overlays = vec![
            json!({"id": "a", "hidden": true}),
            json!({"id": "stray", "name": "Stray"}),
            json!({"id": "mine", "name": "Mine", "custom": true}),
        ];
        let out = effective_exercises(catalog, overlays);
        let names: Vec<&str> = out["exercises"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["name"].as_str().unwrap())
            .collect();
        assert_eq!(names, ["B", "Mine"]);
    }

    #[test]
    fn empty_sources_yield_no_exercises() {
        assert_eq!(
            effective_exercises(vec![], vec![]),
            json!({"exercises": []})
        );
    }
}
