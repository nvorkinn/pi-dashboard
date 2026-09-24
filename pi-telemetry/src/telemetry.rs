use serde_json::json;

pub struct Telemetry {
    pub total_memory: u64,
    pub used_memory: u64,
    pub cpu_count: usize,
    pub global_cpu_usage: f32,
}

pub fn state_topic(device_id: &str) -> String {
    format!("pi-telemetry/{device_id}/state")
}

pub fn build_payload(telemetry: &Telemetry, is_alive: bool) -> String {
    json!({
        "total_memory": telemetry.total_memory,
        "used_memory": telemetry.used_memory,
        "cpu_count": telemetry.cpu_count,
        "global_cpu_usage": telemetry.global_cpu_usage,
        "is_alive": is_alive,
    })
    .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn builds_json_payload() {
        let telemetry = Telemetry {
            total_memory: 100,
            used_memory: 50,
            cpu_count: 4,
            global_cpu_usage: 46.5,
        };

        let payload: Value = serde_json::from_str(&build_payload(&telemetry, true)).unwrap();

        assert_eq!(
            payload,
            json!({
                "total_memory": 100,
                "used_memory": 50,
                "cpu_count": 4,
                "global_cpu_usage": 46.5,
                "is_alive": true,
            })
        );
    }

    #[test]
    fn state_topic_includes_device_id() {
        assert_eq!(state_topic("sister-hat"), "pi-telemetry/sister-hat/state");
    }
}
