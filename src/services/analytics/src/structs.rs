use std::collections::BTreeMap;

use prost_types::value::Kind;
use prost_types::{ListValue, Struct, Value as ProstValue};
use serde_json::Value;

pub fn to_value(value: Value) -> ProstValue {
    let kind = match value {
        Value::Null => Kind::NullValue(0),
        Value::Bool(flag) => Kind::BoolValue(flag),
        Value::Number(number) => Kind::NumberValue(number.as_f64().unwrap_or(0.0)),
        Value::String(text) => Kind::StringValue(text),
        Value::Array(items) => Kind::ListValue(ListValue {
            values: items.into_iter().map(to_value).collect(),
        }),
        Value::Object(map) => Kind::StructValue(to_struct_map(map)),
    };
    ProstValue { kind: Some(kind) }
}

fn to_struct_map(map: serde_json::Map<String, Value>) -> Struct {
    Struct {
        fields: map
            .into_iter()
            .map(|(key, value)| (key, to_value(value)))
            .collect::<BTreeMap<_, _>>(),
    }
}

pub fn to_struct(value: Value) -> Struct {
    match value {
        Value::Object(map) => to_struct_map(map),
        other => Struct {
            fields: BTreeMap::from([("value".to_owned(), to_value(other))]),
        },
    }
}

pub fn to_structs(values: Vec<Value>) -> Vec<Struct> {
    values.into_iter().map(to_struct).collect()
}

pub fn from_value(value: &ProstValue) -> Value {
    match value.kind.as_ref() {
        None | Some(Kind::NullValue(_)) => Value::Null,
        Some(Kind::BoolValue(flag)) => Value::Bool(*flag),
        Some(Kind::NumberValue(number)) => {
            serde_json::Number::from_f64(*number).map_or(Value::Null, Value::Number)
        }
        Some(Kind::StringValue(text)) => Value::String(text.clone()),
        Some(Kind::ListValue(list)) => Value::Array(list.values.iter().map(from_value).collect()),
        Some(Kind::StructValue(inner)) => from_struct(inner),
    }
}

pub fn from_struct(value: &Struct) -> Value {
    Value::Object(
        value
            .fields
            .iter()
            .map(|(key, field)| (key.clone(), from_value(field)))
            .collect(),
    )
}
