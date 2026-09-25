mod countdown_liveness;
mod device_id;
mod homeassistant;
mod system_value_retriever;
mod telemetry;

use crate::countdown_liveness::is_countdown_active;
use crate::device_id::resolve_device_id;
use crate::homeassistant::{build_discovery_payload, discovery_topic};
use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::thread;
use std::time::Duration;
use sysinfo::System;
use system_value_retriever::{get_system, read_telemetry};
use telemetry::{build_payload, state_topic};

#[tokio::main]
async fn main() {
    let mut sys = get_system();
    thread::sleep(sysinfo::MINIMUM_CPU_UPDATE_INTERVAL);
    sys.refresh_cpu_usage();
    let telemetry = read_telemetry(&sys);
    let is_alive = is_countdown_active();

    println!("Total memory: {} bytes", telemetry.total_memory);
    println!("Used memory: {} bytes", telemetry.used_memory);
    println!("Number of CPUs: {}", telemetry.cpu_count);
    println!("Global CPU usage: {}", telemetry.global_cpu_usage);
    println!("Is countdown alive: {}", is_alive);

    let device_id = resolve_device_id(std::env::var("DEVICE_ID").ok(), System::host_name())
        .unwrap_or_else(|e| {
            eprintln!("{e}");
            std::process::exit(1);
        });
    println!("Device id: {device_id}");

    let host = std::env::var("MQTT_BROKER_HOST").unwrap_or_else(|_| "localhost".to_string());
    let port: u16 = std::env::var("MQTT_BROKER_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(1883);

    let mut mqtt_options = MqttOptions::new(format!("pi-telemetry-{device_id}"), host, port);
    mqtt_options.set_keep_alive(Duration::from_secs(5));

    if let (Ok(username), Ok(password)) = (
        std::env::var("MQTT_BROKER_USERNAME"),
        std::env::var("MQTT_BROKER_PASSWORD"),
    ) {
        mqtt_options.set_credentials(username, password);
    }

    let (client, mut event_loop) = AsyncClient::new(mqtt_options, 10);

    // rumqttc only actually does network I/O while the event loop is being
    // polled, so we drive it on a background task for the life of the process.
    tokio::spawn(async move {
        loop {
            if let Err(e) = event_loop.poll().await {
                eprintln!("MQTT event loop error: {e:?}");
                break;
            }
        }
    });

    let state_topic = state_topic(&device_id);

    // Discovery is retained so HA picks the device up after a restart, and is
    // re-sent on every run so it self-heals if the broker's store is wiped.
    client
        .publish(
            discovery_topic(&device_id),
            QoS::AtLeastOnce,
            true,
            build_discovery_payload(&device_id, &state_topic),
        )
        .await
        .expect("failed to publish discovery config");

    client
        .publish(
            &state_topic,
            QoS::AtLeastOnce,
            false,
            build_payload(&telemetry, is_alive),
        )
        .await
        .expect("failed to publish telemetry");

    println!("Published telemetry to {state_topic}");

    // Give the event loop task a moment to actually flush the publish over
    // the socket before the process exits.
    tokio::time::sleep(Duration::from_secs(1)).await;
}
