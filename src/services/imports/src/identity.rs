use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode};
use serde::Deserialize;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Identity {
    pub person: String,
    pub athlete: String,
    pub source: String,
}

#[derive(Deserialize)]
struct Claims {
    jti: String,
    person_pk: String,
    athlete_pk: String,
    scope: Vec<String>,
}

pub fn resolve(
    authorization: &str,
    mesh: Identity,
    method: &str,
    operation: &str,
    public_key: &str,
) -> Result<Identity, &'static str> {
    let auth = authorization.trim();
    let Some((scheme, token)) = auth.split_once(' ') else {
        return Ok(mesh);
    };
    if !scheme.eq_ignore_ascii_case("bearer") {
        return Ok(mesh);
    }
    if !mesh.person.is_empty() || !mesh.athlete.is_empty() {
        return Err("identity headers combined with bearer token");
    }
    let key = DecodingKey::from_ec_pem(public_key.as_bytes()).map_err(|_| "invalid public key")?;
    let mut validation = Validation::new(Algorithm::ES256);
    validation.leeway = 30;
    validation.set_audience(&["pl-domain-mcp"]);
    validation.set_issuer(&["pl-assistant"]);
    validation.set_required_spec_claims(&["exp", "iss", "aud", "jti"]);
    let claims = decode::<Claims>(token.trim(), &key, &validation)
        .map_err(|_| "invalid job token")?
        .claims;
    if claims.jti.is_empty() || claims.person_pk.is_empty() || claims.athlete_pk.is_empty() {
        return Err("required claim empty");
    }
    if method == "tools/call" && !claims.scope.iter().any(|name| name == operation) {
        return Err("operation outside token scope");
    }
    Ok(Identity {
        person: claims.person_pk,
        athlete: claims.athlete_pk,
        source: String::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{EncodingKey, Header, encode};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use rand_core::OsRng;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn validates_signed_scope_and_rejects_mixed_identity() {
        let key = p256::SecretKey::random(&mut OsRng);
        let private = key.to_pkcs8_pem(LineEnding::LF).unwrap();
        let public = key.public_key().to_public_key_pem(LineEnding::LF).unwrap();
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let token = encode(&Header::new(Algorithm::ES256), &json!({"exp":now+300,"iss":"pl-assistant","aud":"pl-domain-mcp","jti":"j","person_pk":"p","athlete_pk":"a","scope":["import_list"]}), &EncodingKey::from_ec_pem(private.as_bytes()).unwrap()).unwrap();
        let authorization = format!("Bearer {token}");
        let identity = resolve(
            &authorization,
            Identity::default(),
            "tools/call",
            "import_list",
            &public,
        )
        .unwrap();
        assert_eq!(identity.person, "p");
        assert!(
            resolve(
                &authorization,
                Identity::default(),
                "tools/call",
                "import_apply",
                &public
            )
            .is_err()
        );
        assert!(
            resolve(
                &authorization,
                Identity {
                    person: "forged".into(),
                    ..Identity::default()
                },
                "tools/call",
                "import_list",
                &public
            )
            .is_err()
        );
        assert!(
            resolve(
                &authorization,
                Identity::default(),
                "tools/call",
                "import_list",
                ""
            )
            .is_err()
        );
    }
}
