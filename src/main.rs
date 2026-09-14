use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::time::Duration;
use sysinfo::System;

#[tokio::main]
async fn main() {
    let mut sys = System::new_all();
    sys.refresh_all();

    let total_memory = sys.total_memory();
    println!("Total memory: {} bytes", total_memory);
    let used_memory = sys.used_memory();
    println!("Used memory: {} bytes", used_memory);
    let cpus = sys.cpus();
    println!("Number of CPUs: {}", cpus.len());

    let mut mqttoptions = MqttOptions::new("pi-telemetry", "localhost", 1883);
    mqttoptions.set_keep_alive(Duration::from_secs(5));

    let (client, mut eventloop) = AsyncClient::new(mqttoptions, 10);

    // rumqttc only actually does network I/O while the eventloop is being
    // polled, so we drive it on a background task for the life of the process.
    tokio::spawn(async move {
        loop {
            if let Err(e) = eventloop.poll().await {
                eprintln!("MQTT eventloop error: {e:?}");
                break;
            }
        }
    });

    let payload = format!(
        "{{\"total_memory\":{total_memory},\"used_memory\":{used_memory},\"cpu_count\":{}}}",
        cpus.len()
    );

    client
        .publish("pi-telemetry/host", QoS::AtLeastOnce, false, payload)
        .await
        .expect("failed to publish telemetry");

    println!("Published telemetry to pi-telemetry/host");

    // Give the eventloop task a moment to actually flush the publish over
    // the socket before the process exits.
    tokio::time::sleep(Duration::from_secs(1)).await;
}