/// Lowercases and replaces anything outside `[a-z0-9_-]` with `-`, so the name is
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

/// The name configured for this host: `DEVICE_NAME`, or `DEVICE_ID` from an env
/// file an older install.sh wrote. Blank values don't count.
pub fn configured_device_name(
    device_name: Option<String>,
    device_id: Option<String>,
) -> Option<String> {
    [device_name, device_id]
        .into_iter()
        .flatten()
        .find(|value| !value.trim().is_empty())
}

/// Picks the name that distinguishes this host from other pi-telemetry hosts:
/// an explicit `DEVICE_NAME` wins, otherwise the hostname.
pub fn resolve_device_name(
    configured: Option<String>,
    hostname: Option<String>,
) -> Result<String, String> {
    let (source, raw) = match (configured, hostname) {
        (Some(name), _) if !name.trim().is_empty() => ("DEVICE_NAME", name),
        (_, Some(host)) if !host.trim().is_empty() => ("hostname", host),
        _ => {
            return Err("DEVICE_NAME is not set and the hostname could not be determined".into());
        }
    };

    let name = sanitize(&raw);
    if name.chars().all(|c| c == '-') {
        return Err(format!(
            "{source} {raw:?} has no usable characters for a device name"
        ));
    }
    Ok(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_device_name_wins_over_hostname() {
        assert_eq!(
            resolve_device_name(Some("sister-hat".into()), Some("raspberrypi".into())),
            Ok("sister-hat".to_string())
        );
    }

    #[test]
    fn falls_back_to_hostname() {
        assert_eq!(
            resolve_device_name(None, Some("vorkin-rbpi-z2w".into())),
            Ok("vorkin-rbpi-z2w".to_string())
        );
    }

    #[test]
    fn blank_device_name_falls_back_to_hostname() {
        assert_eq!(
            resolve_device_name(Some("  ".into()), Some("pi".into())),
            Ok("pi".to_string())
        );
    }

    #[test]
    fn sanitizes_topic_unsafe_characters() {
        assert_eq!(
            resolve_device_name(Some("Living Room/HAT#1+".into()), None),
            Ok("living-room-hat-1-".to_string())
        );
    }

    #[test]
    fn errors_when_nothing_usable() {
        assert!(resolve_device_name(None, None).is_err());
        assert!(resolve_device_name(Some("///".into()), None).is_err());
    }

    #[test]
    fn device_name_wins_over_device_id() {
        assert_eq!(
            configured_device_name(Some("new-name".into()), Some("old-name".into())),
            Some("new-name".to_string())
        );
    }

    #[test]
    fn falls_back_to_the_device_id_an_older_install_wrote() {
        assert_eq!(
            configured_device_name(None, Some("sister-hat".into())),
            Some("sister-hat".to_string())
        );
    }

    #[test]
    fn a_blank_device_name_falls_back_to_device_id() {
        assert_eq!(
            configured_device_name(Some("  ".into()), Some("sister-hat".into())),
            Some("sister-hat".to_string())
        );
    }

    #[test]
    fn nothing_configured_is_none() {
        assert_eq!(configured_device_name(None, None), None);
    }
}
