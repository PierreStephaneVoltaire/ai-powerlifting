// Fission-spawned job pod for the IF agent's OpenCode execution phase.
//
// One-shot HTTP server: bind on $HOST:$PORT, accept exactly one request,
// run OpenCode against the shared workspace PVCs, return the response,
// exit. With minScale=0 on the Fission newdeploy function, the
// Deployment scales to zero between requests and respawns on demand.
//
// Why Rust here (vs Node/Python): the wrapper streams opencode's
// stdout/stderr line-by-line to the pod log while opencode runs. No GC
// pauses means we never drop lines under load; RAII on `Child` gives us
// deterministic subprocess cleanup; `tiny_http` is allocation-bounded.
// The compiled binary is a single ~5 MB static file, no runtime.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tiny_http::{Header, Method, Response, Server, StatusCode};

/// Names of the per-run runtime artifacts the IF agent already knows
/// about. Skipped from the artifacts list so the IF agent doesn't try
/// to re-ingest them as user-facing files.
const RUNTIME_EXCLUDES: &[&str] = &[
    "history.md",
    "history.json",
    "opencode.json",
    "plan.md",
    "review.md",
    "response.md",
    "status.log",
];

const DEFAULT_PORT: u16 = 8000;
const DEFAULT_HOST: &str = "0.0.0.0";
const DEFAULT_OPENCODE_BIN: &str = "opencode";
const DEFAULT_TIMEOUT_SECONDS: u64 = 900;
const MAX_BODY_BYTES: usize = 8 * 1024 * 1024; // 8 MiB

// -----------------------------------------------------------------------------
// Wire types
// -----------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct OpencodeJobRequest {
    job_id: String,
    #[serde(default)]
    agent: Option<String>,
    model: String,
    prompt: String,
    session_dir: String,
    #[serde(default)]
    files: Vec<String>,
    #[serde(default)]
    timeout_seconds: Option<u64>,
    #[serde(default)]
    extra_env: HashMap<String, String>,
}

#[derive(Debug, Serialize)]
struct Artifact {
    path: String,
    name: String,
}

#[derive(Debug, Serialize)]
struct OpencodeJobResponse {
    job_id: String,
    status: String, // "ok" | "error" | "timeout"
    #[serde(skip_serializing_if = "Option::is_none")]
    returncode: Option<i32>,
    #[serde(default)]
    stdout: String,
    #[serde(default)]
    stderr: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_file: Option<String>,
    #[serde(default)]
    artifacts: Vec<Artifact>,
    #[serde(default)]
    message: String,
}

fn error_response(job_id: &str, message: &str) -> OpencodeJobResponse {
    OpencodeJobResponse {
        job_id: job_id.to_string(),
        status: "error".to_string(),
        returncode: None,
        stdout: String::new(),
        stderr: String::new(),
        response_file: None,
        artifacts: Vec::new(),
        message: message.to_string(),
    }
}

// -----------------------------------------------------------------------------
// main: bind, accept one request, exit
// -----------------------------------------------------------------------------

fn main() {
    let port: u16 = std::env::var("PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_PORT);
    let host = std::env::var("HOST").unwrap_or_else(|_| DEFAULT_HOST.to_string());
    let opencode_bin =
        std::env::var("OPENCODE_BIN").unwrap_or_else(|_| DEFAULT_OPENCODE_BIN.to_string());

    let bind_addr = format!("{}:{}", host, port);
    let server = Server::http(&bind_addr).unwrap_or_else(|e| {
        eprintln!("[opencode-runner] failed to bind {}: {}", bind_addr, e);
        std::process::exit(1);
    });
    eprintln!(
        "[opencode-runner] listening on {}, opencode={}",
        bind_addr, opencode_bin
    );

    // One-shot semantics: keep serving /health (and any 404s) so a
    // debug health probe never kills the pod mid-flight, but exit as
    // soon as a /v1/opencode/execute call completes. Fission's
    // newdeploy Deployment then scales back to minScale=0 and respawns
    // a fresh pod for the next job.
    for req in server.incoming_requests() {
        if handle_request(req, &opencode_bin) {
            break;
        }
    }
    eprintln!("[opencode-runner] opencode job completed, exiting");
}

// -----------------------------------------------------------------------------
// HTTP routing
// -----------------------------------------------------------------------------

/// Handle one request. Returns `true` if the server should now exit
/// (i.e. the request was a real /v1/opencode/execute job), `false` if
/// it was a health probe or 404 and the server should keep listening.
fn handle_request(mut req: tiny_http::Request, opencode_bin: &str) -> bool {
    let method = req.method().clone();
    let url = req.url().to_string();

    let response: OpencodeJobResponse = match (method.clone(), url.as_str()) {
        (Method::Get, "/health") | (Method::Get, "/healthz") => {
            // Health probes must not kill the pod mid-flight.
            let body = serde_json::json!({
                "status": "ok",
                "opencode_bin": opencode_bin,
            });
            let json = serde_json::to_string(&body).unwrap_or_else(|_| "{}".to_string());
            let resp = Response::from_string(json).with_header(json_header());
            let _ = req.respond(resp);
            return false;
        }
        (Method::Post, "/v1/opencode/execute") => match read_and_parse_job(&mut req) {
            Ok(job) => run_opencode(&job, opencode_bin),
            Err(msg) => {
                // Malformed job body: nothing the pod can do about it.
                // Send the error, then exit so a fresh pod can take
                // the next (hopefully valid) call.
                let body = serde_json::json!({
                    "status": "error",
                    "message": msg,
                });
                let json = serde_json::to_string(&body).unwrap_or_else(|_| "{}".to_string());
                let resp = Response::from_string(json)
                    .with_header(json_header())
                    .with_status_code(StatusCode(400));
                let _ = req.respond(resp);
                return true;
            }
        },
        _ => {
            // Anything else: stay alive in case a stray probe lands.
            let body = serde_json::json!({
                "status": "error",
                "message": format!("not found: {} {}", method, url),
            });
            let json = serde_json::to_string(&body).unwrap_or_else(|_| "{}".to_string());
            let resp = Response::from_string(json)
                .with_header(json_header())
                .with_status_code(StatusCode(404));
            let _ = req.respond(resp);
            return false;
        }
    };

    // Real opencode job — done, send the response, and signal the main
    // loop to exit so the Fission Deployment can scale to zero.
    let status = if response.status == "ok" {
        StatusCode(200)
    } else {
        StatusCode(500)
    };
    let json = serde_json::to_string(&response).unwrap_or_else(|_| "{}".to_string());
    let resp = Response::from_string(json)
        .with_header(json_header())
        .with_status_code(status);
    let _ = req.respond(resp);
    true
}

fn json_header() -> Header {
    Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..])
        .expect("static header is valid")
}

fn read_and_parse_job(req: &mut tiny_http::Request) -> Result<OpencodeJobRequest, String> {
    let mut buf = Vec::new();
    let reader = req.as_reader();
    let mut chunk = [0u8; 8192];
    loop {
        let n = reader
            .read(&mut chunk)
            .map_err(|e| format!("failed to read body: {}", e))?;
        if n == 0 {
            break;
        }
        if buf.len() + n > MAX_BODY_BYTES {
            return Err(format!("request body exceeds {} bytes", MAX_BODY_BYTES));
        }
        buf.extend_from_slice(&chunk[..n]);
    }
    if buf.is_empty() {
        return Err("empty request body".to_string());
    }
    serde_json::from_slice(&buf).map_err(|e| format!("invalid JSON body: {}", e))
}

// -----------------------------------------------------------------------------
// OpenCode execution
// -----------------------------------------------------------------------------

const STREAM_LIMIT_BYTES: usize = 50 * 1024 * 1024; // 50 MiB per stream

fn run_opencode(job: &OpencodeJobRequest, opencode_bin: &str) -> OpencodeJobResponse {
    // 1. Verify the workspace is writable on the shared PVC. If this
    //    fails the Fission function pod landed somewhere that can't see
    //    the agent's PVCs — fail fast and tell the caller.
    let session_dir = PathBuf::from(&job.session_dir);
    if let Err(e) = std::fs::create_dir_all(&session_dir) {
        return error_response(
            &job.job_id,
            &format!("failed to create session_dir {}: {}", session_dir.display(), e),
        );
    }
    let probe = session_dir.join(".opencode-runner-write-probe");
    if let Err(e) = std::fs::write(&probe, "ok\n") {
        return error_response(
            &job.job_id,
            &format!("workspace {} is not writable: {}", session_dir.display(), e),
        );
    }
    let _ = std::fs::remove_file(&probe);

    // 2. Build the opencode command. Match the flags the IF agent uses
    //    for in-process runs (see app/src/flow/opencode.py).
    let model_arg = if job.model.contains('/') {
        format!("openrouter/{}", job.model)
    } else {
        job.model.clone()
    };
    let agent = job.agent.as_deref().unwrap_or("build");

    let mut cmd = Command::new(opencode_bin);
    cmd.arg("run")
        .arg("--agent")
        .arg(agent)
        .arg("--model")
        .arg(&model_arg)
        .arg("--dangerously-skip-permissions")
        .arg("--thinking")
        .arg("--dir")
        .arg(&session_dir);
    for file in &job.files {
        cmd.arg("--file").arg(file);
    }
    cmd.arg(&job.prompt);

    cmd.env("OPENCODE_EXPERIMENTAL", "1")
        .env("OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS", "1")
        .env("OPENCODE_EXPERIMENTAL_PARALLEL", "1")
        .env("OPENCODE_EXPERIMENTAL_LSP_TOOL", "1")
        .env("OPENCODE_EXPERIMENTAL_LSP_TY", "1");
    for (k, v) in &job.extra_env {
        cmd.env(k, v);
    }
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    eprintln!(
        "[opencode-runner] starting job={} agent={} model={} dir={}",
        job.job_id,
        agent,
        model_arg,
        session_dir.display()
    );

    // 3. Spawn. Holding the Child in scope here means Drop will send
    //    SIGKILL if we early-return on an error path — no zombie
    //    opencode processes.
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return error_response(
                &job.job_id,
                &format!("failed to spawn opencode: {}", e),
            )
        }
    };
    let stdout = child.stdout.take().expect("stdout piped above");
    let stderr = child.stderr.take().expect("stderr piped above");

    // 4. Stream stdout/stderr to the pod log line-by-line and
    //    accumulate into a bounded String for the response. Each stream
    //    gets its own thread; both are joined before we return.
    let stdout_handle = thread::spawn(move || stream_to_log_and_buf(stdout, "stdout"));
    let stderr_handle = thread::spawn(move || stream_to_log_and_buf(stderr, "stderr"));

    // 5. Wait with a deadline. try_wait lets us apply the timeout
    //    without spawning yet another thread for the wait itself.
    let timeout = Duration::from_secs(job.timeout_seconds.unwrap_or(DEFAULT_TIMEOUT_SECONDS));
    let start = Instant::now();
    let wait_result = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => {
                if start.elapsed() >= timeout {
                    let _ = child.kill();
                    break Err(format!(
                        "opencode timed out after {}s",
                        job.timeout_seconds.unwrap_or(DEFAULT_TIMEOUT_SECONDS)
                    ));
                }
                thread::sleep(Duration::from_millis(200));
            }
            Err(e) => {
                let _ = child.kill();
                break Err(format!("waitpid failed: {}", e));
            }
        }
    };
    // Reap the zombie (best effort; child.kill() above guarantees exit).
    let _ = child.wait();

    let stdout_text = stdout_handle.join().unwrap_or_default();
    let stderr_text = stderr_handle.join().unwrap_or_default();

    // 6. Build the response. On success, locate response.md and the
    //    session-dir artifacts the IF agent may want to ingest.
    let (status_str, returncode, message) = match wait_result {
        Ok(s) => {
            let code = s.code();
            let st = if code == Some(0) { "ok" } else { "error" };
            (st.to_string(), code, String::new())
        }
        Err(msg) => ("timeout".to_string(), None, msg),
    };

    let response_file = session_dir.join("response.md");
    let response_file_str = if response_file.is_file() {
        Some(response_file.to_string_lossy().into_owned())
    } else {
        None
    };

    let artifacts = list_artifacts(&session_dir);

    OpencodeJobResponse {
        job_id: job.job_id.clone(),
        status: status_str,
        returncode,
        stdout: stdout_text,
        stderr: stderr_text,
        response_file: response_file_str,
        artifacts,
        message,
    }
}

fn stream_to_log_and_buf<R: Read + Send + 'static>(
    reader: R,
    label: &'static str,
) -> String {
    let mut buf = String::new();
    let mut truncated = false;
    for line in BufReader::new(reader).lines() {
        let Ok(line) = line else { break };
        eprintln!("[opencode|{}] {}", label, line);
        if !truncated {
            if buf.len() + line.len() + 1 > STREAM_LIMIT_BYTES {
                eprintln!(
                    "[opencode|{}] output truncated at {} bytes",
                    label, STREAM_LIMIT_BYTES
                );
                truncated = true;
            } else {
                buf.push_str(&line);
                buf.push('\n');
            }
        }
    }
    buf
}

fn list_artifacts(session_dir: &Path) -> Vec<Artifact> {
    fn walk(dir: &Path, out: &mut Vec<Artifact>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk(&path, out);
            } else if path.is_file() {
                let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
                    continue;
                };
                if RUNTIME_EXCLUDES.contains(&name) {
                    continue;
                }
                out.push(Artifact {
                    path: path.to_string_lossy().into_owned(),
                    name: name.to_string(),
                });
            }
        }
    }
    let mut out = Vec::new();
    walk(session_dir, &mut out);
    out
}


