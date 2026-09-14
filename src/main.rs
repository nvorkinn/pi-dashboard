use sysinfo::System;

fn main() {
    let mut sys = System::new_all();
    sys.refresh_all();

    let total_memory = sys.total_memory();
    println!("Total memory: {} bytes", total_memory);
    let used_memory = sys.used_memory();
    println!("Used memory: {} bytes", used_memory);
    let cpus = sys.cpus();
    println!("Number of CPUs: {}", cpus.len());
}