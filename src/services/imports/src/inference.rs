use serde_json::{Value, json};

use crate::parse::Extracted;

pub fn challenge(
    extracted: &Extracted,
    filename: &str,
    classification: &str,
    context: &Value,
    instructions: &str,
) -> Result<Value, serde_json::Error> {
    let rows = if classification == "template" {
        &extracted.rows[..]
    } else {
        &extracted.rows[..extracted.rows.len().min(100)]
    };
    let user = json!({
        "file_content": serde_json::to_string_pretty(rows)?,
        "file_name": filename,
        "sheet_headings": extracted.headings,
        "classification": classification,
        "athlete_context": context,
        "import_instructions": if instructions.is_empty() { "Not provided." } else { instructions }
    });
    Ok(json!({
        "messages": [
            {"role":"system", "content":include_str!("../../runtime/prompts/import_parse_system.j2").trim()},
            {"role":"user", "content":serde_json::to_string_pretty(&user)?}
        ],
        "tools": [{"type":"function","function":{
            "name":"report_parse_result", "description":"Report the structured parse result of a training program",
            "parameters":{"type":"object","properties":{
                "program_name":{"type":["string","null"]}, "phases":{"type":"array","items":{"type":"object"}},
                "sessions":{"type":"array","items":{"type":"object"}}, "warnings":{"type":"array","items":{"type":"object"}},
                "new_exercises":{"type":"array","items":{"type":"object"}}, "parse_notes":{"type":"string"}
            }, "required":["program_name","phases","sessions","warnings","parse_notes"]}
        }}],
        "response_format":null,
        "instruction":"Use a native Specialist child to answer these messages. Return its structured result using domain_resume. Do not submit another IF job."
    }))
}

pub fn validate_result(parsed: &Value) -> Result<(), String> {
    let object = parsed
        .as_object()
        .ok_or("The AI parser returned an invalid result")?;
    if let Some(error) = object
        .get("warnings")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|warning| warning["type"] == "error")
    {
        return Err(error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("AI could not parse the uploaded file")
            .to_owned());
    }
    if object
        .get("sessions")
        .and_then(Value::as_array)
        .is_none_or(Vec::is_empty)
    {
        return Err("No training sessions were found in the uploaded file".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn limits_session_prompt_and_validates_ai_errors() {
        let extracted = Extracted {
            rows: (0..101).map(|n| json!({"row":n})).collect(),
            headings: BTreeMap::new(),
            file_hash: String::new(),
        };
        let prompt = challenge(&extracted, "test.csv", "session_import", &json!({}), "").unwrap();
        let user: Value =
            serde_json::from_str(prompt["messages"][1]["content"].as_str().unwrap()).unwrap();
        let rows: Vec<Value> =
            serde_json::from_str(user["file_content"].as_str().unwrap()).unwrap();
        assert_eq!(rows.len(), 100);
        assert!(validate_result(&json!({"sessions":[]})).is_err());
        assert!(
            validate_result(
                &json!({"sessions":[{}],"warnings":[{"type":"error","message":"bad"}]})
            )
            .is_err()
        );
        assert!(validate_result(&json!({"sessions":[{}]})).is_ok());
    }
}
