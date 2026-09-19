mod system_value_retriever;
mod telemetry;
mod countdown_liveness;

use std::thread;
use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::time::Duration;
use system_value_retriever::{get_system, read_telemetry};
use telemetry::build_payload;
use crate::countdown_liveness::CountdownLiveness;

#[tokio::main]
async fn main() {
    let mut sys = get_system();
    thread::sleep(sysinfo::MINIMUM_CPU_UPDATE_INTERVAL);
    sys.refresh_cpu_usage();
    let telemetry = read_telemetry(&sys);
    let is_alive = sys.is_alive();

    println!("Total memory: {} bytes", telemetry.total_memory);
    println!("Used memory: {} bytes", telemetry.used_memory);
    println!("Number of CPUs: {}", telemetry.cpu_count);
    println!("Global CPU usage: {}", telemetry.global_cpu_usage);
    println!("Is countdown alive: {}", is_alive);

    let host = std::env::var("MQTT_BROKER_HOST").unwrap_or_else(|_| "localhost".to_string());
    let port: u16 = std::env::var("MQTT_BROKER_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(1883);

    let mut mqtt_options = MqttOptions::new("pi-telemetry", host, port);
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

    let payload = build_payload(&telemetry, is_alive);

    client
        .publish("pi-telemetry/host", QoS::AtLeastOnce, false, payload)
        .await
        .expect("failed to publish telemetry");

    println!("Published telemetry to pi-telemetry/host");

    // Give the event loop task a moment to actually flush the publish over
    // the socket before the process exits.
    tokio::time::sleep(Duration::from_secs(1)).await;
}
