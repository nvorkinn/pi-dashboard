/// Lowercases and replaces anything outside `[a-z0-9_-]` with `-`, so the id is
/// safe to use as an MQTT topic level and an MQTT client id suffix.
fn sanitize(raw: &str) -> String {
    raw.trim()
        .chars()
        .map(|c| match c.to_ascii_lowercase() {
            c @ ('a'..='z' | '0'..='9' | '_' | '-') => c,
            _ => '-',
        })
        .collect()
}

/// Picks the id that distinguishes this host from other pi-telemetry hosts:
/// an explicit `DEVICE_ID` wins, otherwise the hostname.
pub fn resolve_device_id(
    configured: Option<String>,
    hostname: Option<String>,
) -> Result<String, String> {
    let (source, raw) = match (configured, hostname) {
        (Some(id), _) if !id.trim().is_empty() => ("DEVICE_ID", id),
        (_, Some(name)) if !name.trim().is_empty() => ("hostname", name),
        _ => return Err("DEVICE_ID is not set and the hostname could not be determined".into()),
    };

    let id = sanitize(&raw);
    if id.chars().all(|c| c == '-') {
        return Err(format!(
            "{source} {raw:?} has no usable characters for a device id"
        ));
    }
    Ok(id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_device_id_wins_over_hostname() {
        assert_eq!(
            resolve_device_id(Some("sister-hat".into()), Some("raspberrypi".into())),
            Ok("sister-hat".to_string())
        );
    }

    #[test]
    fn falls_back_to_hostname() {
        assert_eq!(
            resolve_device_id(None, Some("vorkin-rbpi-z2w".into())),
            Ok("vorkin-rbpi-z2w".to_string())
        );
    }

    #[test]
    fn blank_device_id_falls_back_to_hostname() {
        assert_eq!(
            resolve_device_id(Some("  ".into()), Some("pi".into())),
            Ok("pi".to_string())
        );
    }

    #[test]
    fn sanitizes_topic_unsafe_characters() {
        assert_eq!(
            resolve_device_id(Some("Living Room/HAT#1+".into()), None),
            Ok("living-room-hat-1-".to_string())
        );
    }

    #[test]
    fn errors_when_nothing_usable() {
        assert!(resolve_device_id(None, None).is_err());
        assert!(resolve_device_id(Some("///".into()), None).is_err());
    }
}
