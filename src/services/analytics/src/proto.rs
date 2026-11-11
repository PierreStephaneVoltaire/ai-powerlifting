pub mod analytics {
    tonic::include_proto!("powerlifting.analytics.v1");

    pub const DESCRIPTOR: &[u8] =
        include_bytes!(concat!(env!("OUT_DIR"), "/analytics_descriptor.bin"));
}

pub mod reports {
    tonic::include_proto!("powerlifting.analytics_ai.v1");
}
