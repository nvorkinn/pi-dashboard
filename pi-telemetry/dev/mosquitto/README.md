# Dev MQTT broker

Throwaway Mosquitto broker for local development, until a real broker
(e.g. Home Assistant's) exists on the network. Anonymous access is enabled,
so only run this on localhost/dev machines.

```
docker compose -f dev/mosquitto/docker-compose.yml up -d
```

The app expects it at `localhost:1883` (see `MqttOptions` in `src/main.rs`).
