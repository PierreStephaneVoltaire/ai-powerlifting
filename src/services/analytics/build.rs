use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let protoc = protoc_bin_vendored::protoc_bin_path()?;
    let include = protoc_bin_vendored::include_path()?;
    let include_dir = include.to_str().ok_or("include path is not utf-8")?;
    let descriptor = PathBuf::from(std::env::var("OUT_DIR")?).join("analytics_descriptor.bin");

    let mut server = tonic_prost_build::Config::new();
    server.protoc_executable(&protoc);
    server.file_descriptor_set_path(&descriptor);
    tonic_prost_build::configure()
        .build_client(true)
        .compile_with_config(server, &["proto/analytics.proto"], &["proto", include_dir])?;

    let mut client = tonic_prost_build::Config::new();
    client.protoc_executable(&protoc);
    tonic_prost_build::configure()
        .build_server(false)
        .compile_with_config(
            client,
            &["../analytics-ai/proto/reports.proto"],
            &["../analytics-ai/proto", include_dir],
        )?;

    println!("cargo:rerun-if-changed=proto/analytics.proto");
    println!("cargo:rerun-if-changed=../analytics-ai/proto/reports.proto");
    Ok(())
}
