use sysinfo::System;

pub trait CountdownLiveness {
    fn is_alive(&self) -> bool;
}

impl CountdownLiveness for System {
    fn is_alive(&self) -> bool {
        for (_pid, process) in self.processes() {
            if process.cmd().iter().any(|arg| arg == "countdown") {
                return true;
            }
        }
        false
    }
}
