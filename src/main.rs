mod system_value_retriever;
mod telemetry;

use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::time::Duration;
use system_value_retriever::{get_system, read_telemetry};
use telemetry::build_payload;

#[tokio::main]
async fn main() {
    let sys = get_system();
    let telemetry = read_telemetry(&sys);

    println!("Total memory: {} bytes", telemetry.total_memory);
    println!("Used memory: {} bytes", telemetry.used_memory);
    println!("Number of CPUs: {}", telemetry.cpu_count);

    let mut mqtt_options = MqttOptions::new("pi-telemetry", "localhost", 1883);
    mqtt_options.set_keep_alive(Duration::from_secs(5));

    let (client, mut eventloop) = AsyncClient::new(mqtt_options, 10);

    // rumqttc only actually does network I/O while the eventloop is being
    // polled, so we drive it on a background task for the life of the process.
    tokio::spawn(async move {
        loop {
            if let Err(e) = eventloop.poll().await {
                eprintln!("MQTT event loop error: {e:?}");
                break;
            }
        }
    });

    let payload = build_payload(&telemetry);

    client
        .publish("pi-telemetry/host", QoS::AtLeastOnce, false, payload)
        .await
        .expect("failed to publish telemetry");

    println!("Published telemetry to pi-telemetry/host");

    // Give the eventloop task a moment to actually flush the publish over
    // the socket before the process exits.
    tokio::time::sleep(Duration::from_secs(1)).await;
}
