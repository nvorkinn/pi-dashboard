use serde_json::{Value, json};

/// Entities go `unavailable` in HA after this long without state: two missed runs.
/// There's no last will, since the process exits after every publish.
const EXPIRE_AFTER_SECS: u64 = 180;

pub fn discovery_topic(device_name: &str) -> String {
    format!("homeassistant/device/{device_name}/config")
}

fn component(
    platform: &str,
    device_name: &str,
    key: &str,
    name: &str,
    state_topic: &str,
    value_template: &str,
    extra: Value,
) -> Value {
    let mut component = json!({
        "platform": platform,
        "unique_id": format!("pi_telemetry_{device_name}_{key}"),
        "name": name,
        "state_topic": state_topic,
        "value_template": value_template,
        "expire_after": EXPIRE_AFTER_SECS,
    });
    if let (Some(base), Value::Object(extra)) = (component.as_object_mut(), extra) {
        base.extend(extra);
    }
    component
}

/// Builds the device-based discovery message. Every component shares the same
/// `device.identifiers`, which is what makes HA group them under one device
/// per host.
pub fn build_discovery_payload(device_name: &str, state_topic: &str) -> String {
    let version = env!("CARGO_PKG_VERSION");
    let sensor = |key, name, template, extra| {
        component(
            "sensor",
            device_name,
            key,
            name,
            state_topic,
            template,
            extra,
        )
    };

    json!({
        "device": {
            "identifiers": [format!("pi_telemetry_{device_name}")],
            "name": device_name,
            "manufacturer": "pi-telemetry",
            "sw_version": version,
        },
        "origin": {
            "name": "pi-telemetry",
            "sw_version": version,
        },
        "components": {
            "total_memory": sensor("total_memory", "Total memory", "{{ value_json.total_memory }}", json!({
                "device_class": "data_size",
                "unit_of_measurement": "B",
                "suggested_unit_of_measurement": "MB",
                "suggested_display_precision": 0,
                "entity_category": "diagnostic",
            })),
            "used_memory": sensor("used_memory", "Used memory", "{{ value_json.used_memory }}", json!({
                "device_class": "data_size",
                "unit_of_measurement": "B",
                "suggested_unit_of_measurement": "MB",
                "suggested_display_precision": 0,
                "state_class": "measurement",
            })),
            "cpu_count": sensor("cpu_count", "CPU count", "{{ value_json.cpu_count }}", json!({
                "entity_category": "diagnostic",
            })),
            "global_cpu_usage": sensor("global_cpu_usage", "CPU usage", "{{ value_json.global_cpu_usage }}", json!({
                "unit_of_measurement": "%",
                "suggested_display_precision": 1,
                "state_class": "measurement",
            })),
            "is_alive": component(
                "binary_sensor",
                device_name,
                "is_alive",
                "HAT running",
                state_topic,
                "{{ 'ON' if value_json.is_alive else 'OFF' }}",
                json!({ "device_class": "running" }),
            ),
        },
    })
    .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn payload(device_name: &str) -> Value {
        let state_topic = format!("pi-telemetry/{device_name}/state");
        serde_json::from_str(&build_discovery_payload(device_name, &state_topic)).unwrap()
    }

    #[test]
    fn discovery_topic_includes_device_name() {
        assert_eq!(
            discovery_topic("sister-hat"),
            "homeassistant/device/sister-hat/config"
        );
    }

    #[test]
    fn all_components_read_the_state_topic() {
        let payload = payload("sister-hat");
        let components = payload["components"].as_object().unwrap();

        assert_eq!(components.len(), 5);
        for (key, component) in components {
            assert_eq!(
                component["state_topic"], "pi-telemetry/sister-hat/state",
                "component {key}"
            );
        }
    }

    #[test]
    fn unique_ids_are_distinct_per_host_and_metric() {
        let unique_ids = |device_name| -> Vec<String> {
            let payload = payload(device_name);
            let mut ids: Vec<String> = payload["components"]
                .as_object()
                .unwrap()
                .values()
                .map(|c| c["unique_id"].as_str().unwrap().to_string())
                .collect();
            ids.sort();
            ids
        };

        let a = unique_ids("host-a");
        let b = unique_ids("host-b");

        assert!(a.windows(2).all(|w| w[0] != w[1]));
        assert!(a.iter().all(|id| !b.contains(id)));
    }

    #[test]
    fn device_identifier_is_stable_per_host() {
        let payload = payload("sister-hat");
        assert_eq!(
            payload["device"]["identifiers"],
            json!(["pi_telemetry_sister-hat"])
        );
        assert_eq!(payload["device"]["name"], "sister-hat");
    }

    #[test]
    fn is_alive_is_a_binary_sensor() {
        let payload = payload("sister-hat");
        let is_alive = &payload["components"]["is_alive"];

        assert_eq!(is_alive["platform"], "binary_sensor");
        assert_eq!(is_alive["device_class"], "running");
    }
}
