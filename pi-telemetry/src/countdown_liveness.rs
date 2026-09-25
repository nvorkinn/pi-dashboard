use std::process::Command;

/// Whether the countdown app is running, asked of systemd rather than read off the
/// process list: its unit starts it by a full path to a Python script, so no argument
/// is ever exactly "countdown", and a name match could be fooled by anything else
/// that happens to mention it.
pub fn is_countdown_active() -> bool {
    is_unit_active("systemctl", "countdown")
}

/// `systemctl is-active --quiet <unit>` exits 0 only when the unit is active. Anything
/// else -- inactive, failed, unknown, or systemctl itself missing -- counts as not.
fn is_unit_active(systemctl: &str, unit: &str) -> bool {
    Command::new(systemctl)
        .args(["is-active", "--quiet", unit])
        .status()
        .is_ok_and(|status| status.success())
}

#[cfg(test)]
mod tests {
    use super::*;

    // `true` and `false` stand in for systemctl: they ignore their arguments and exit
    // 0 and 1, like `is-active` for an active and an inactive unit.
    #[test]
    fn an_active_unit_is_alive() {
        assert!(is_unit_active("true", "countdown"));
    }

    #[test]
    fn an_inactive_unit_is_not_alive() {
        assert!(!is_unit_active("false", "countdown"));
    }

    #[test]
    fn no_systemctl_means_not_alive() {
        assert!(!is_unit_active("/nonexistent/systemctl", "countdown"));
    }
}
