pub struct Telemetry {
    pub total_memory: u64,
    pub used_memory: u64,
    pub cpu_count: usize,
}

pub fn build_payload(telemetry: &Telemetry) -> String {
    format!(
        "{{\"total_memory\":{},\"used_memory\":{},\"cpu_count\":{}}}",
        telemetry.total_memory, telemetry.used_memory, telemetry.cpu_count
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_json_payload() {
        let telemetry = Telemetry {
            total_memory: 100,
            used_memory: 50,
            cpu_count: 4,
        };

        assert_eq!(
            build_payload(&telemetry),
            r#"{"total_memory":100,"used_memory":50,"cpu_count":4}"#
        );
    }
}
