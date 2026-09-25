use crate::telemetry::Telemetry;
use sysinfo::System;

pub trait SystemInfo {
    fn total_memory(&self) -> u64;
    fn used_memory(&self) -> u64;
    fn cpu_count(&self) -> usize;
    fn global_cpu_usage(&self) -> f32;
}

impl SystemInfo for System {
    fn total_memory(&self) -> u64 {
        System::total_memory(self)
    }

    fn used_memory(&self) -> u64 {
        System::used_memory(self)
    }

    fn cpu_count(&self) -> usize {
        self.cpus().len()
    }

    fn global_cpu_usage(&self) -> f32 {
        self.global_cpu_usage()
    }
}

pub fn get_system() -> System {
    System::new_all()
}

pub fn read_telemetry(sys: &impl SystemInfo) -> Telemetry {
    Telemetry {
        total_memory: sys.total_memory(),
        used_memory: sys.used_memory(),
        cpu_count: sys.cpu_count(),
        global_cpu_usage: sys.global_cpu_usage(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FakeSystem {
        total_memory: u64,
        used_memory: u64,
        cpu_count: usize,
        global_cpu_usage: f32,
    }

    impl SystemInfo for FakeSystem {
        fn total_memory(&self) -> u64 {
            self.total_memory
        }

        fn used_memory(&self) -> u64 {
            self.used_memory
        }

        fn cpu_count(&self) -> usize {
            self.cpu_count
        }

        fn global_cpu_usage(&self) -> f32 {
            self.global_cpu_usage
        }
    }

    #[test]
    fn maps_fields_without_mixing_them_up() {
        let fake = FakeSystem {
            total_memory: 111,
            used_memory: 222,
            cpu_count: 4,
            global_cpu_usage: 46.3,
        };

        let telemetry = read_telemetry(&fake);

        assert_eq!(telemetry.total_memory, 111);
        assert_eq!(telemetry.used_memory, 222);
        assert_eq!(telemetry.cpu_count, 4);
        assert_eq!(telemetry.global_cpu_usage, 46.3);
    }
}
