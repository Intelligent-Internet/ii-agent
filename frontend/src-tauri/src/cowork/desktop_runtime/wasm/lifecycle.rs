//! Lifecycle management for the shared desktop [`WasmRuntime`].
//!
//! The engine + registry that back every `wasm_run` call are expensive
//! to set up (compile all built-in modules through cranelift) and
//! reasonably cheap to keep around idle, but we still want them dropped
//! eventually so an unused desktop session does not hold on to
//! ~5–10 MB of wasmtime state forever. This module implements that
//! policy:
//!
//! * **Lazy creation.** The runtime is `None` until the first caller
//!   asks for it. At that point we build a fresh [`WasmRuntime`],
//!   register the built-in modules, and record `last_used = now`.
//! * **In-flight counting.** Each caller leases the runtime via
//!   [`acquire_runtime`] which returns a [`RuntimeLease`] guard. The
//!   guard increments an in-flight counter on acquisition and
//!   decrements it when dropped. A lease holder keeps the runtime alive
//!   no matter how idle the app has been.
//! * **Idle reaper.** A single background thread wakes up on a fixed
//!   interval (see [`REAP_INTERVAL`]). When `in_flight == 0` and
//!   `now - last_used > IDLE_TIMEOUT`, it drops the runtime. The next
//!   caller will rebuild it lazily.
//!
//! The reaper never drops a runtime that has active leases — `Drop` on
//! [`RuntimeLease`] only *refreshes* `last_used`; it does not itself
//! trigger teardown. This means a long-running call (pdf extraction for
//! a large document) cannot have the engine pulled out from under it by
//! the reaper half-way through.

use super::WasmRuntime;
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

/// How long the runtime may stay idle before the reaper drops it.
///
/// Exposed as a module-level constant rather than a config value
/// because it is not something the LLM or the user should tune — it is
/// a direct trade-off between "keep lazy init latency away from the
/// user" and "do not hold RAM forever". Five minutes splits the
/// difference for typical cowork sessions.
pub const IDLE_TIMEOUT: Duration = Duration::from_secs(5 * 60);

/// How often the background reaper wakes up to check whether the
/// runtime should be torn down. Shorter means faster release after
/// idle; longer means less wake-up noise. 30 s is short enough to drop
/// within a minute of the timeout firing and long enough that the
/// reaper thread does not show up in CPU profiles.
pub const REAP_INTERVAL: Duration = Duration::from_secs(30);

/// Shared mutable state watched by the reaper. Guarded by a single
/// `Mutex` because every mutation (acquire, release, reap) is short
/// and non-blocking.
struct LifecycleState {
    runtime: Option<Arc<WasmRuntime>>,
    last_used: Instant,
    in_flight: u32,
    /// Timeout applied by the reaper. Exposed as state (rather than a
    /// constant) so tests can drive the reaper without waiting five
    /// minutes of real time.
    idle_timeout: Duration,
}

impl LifecycleState {
    fn new(idle_timeout: Duration) -> Self {
        Self {
            runtime: None,
            last_used: Instant::now(),
            in_flight: 0,
            idle_timeout,
        }
    }
}

/// Lazy container holding the global lifecycle state + the handle to
/// the reaper thread. The first [`acquire_runtime`] call constructs the
/// `Arc<Mutex<...>>` and spawns the reaper; subsequent calls just clone
/// the `Arc`.
static GLOBAL: OnceLock<Arc<Mutex<LifecycleState>>> = OnceLock::new();

fn global_state() -> Arc<Mutex<LifecycleState>> {
    GLOBAL
        .get_or_init(|| {
            let state = Arc::new(Mutex::new(LifecycleState::new(IDLE_TIMEOUT)));
            spawn_reaper(Arc::clone(&state), REAP_INTERVAL);
            state
        })
        .clone()
}

fn spawn_reaper(state: Arc<Mutex<LifecycleState>>, interval: Duration) {
    thread::spawn(move || loop {
        thread::sleep(interval);
        reap_once(&state);
    });
}

/// Drop the runtime if it has been idle for longer than the configured
/// timeout **and** no leases are outstanding. Factored out so tests can
/// drive it synchronously.
fn reap_once(state: &Arc<Mutex<LifecycleState>>) -> bool {
    let mut guard = lock_or_recover(state);
    if guard.runtime.is_none() {
        return false;
    }
    if guard.in_flight > 0 {
        return false;
    }
    if guard.last_used.elapsed() < guard.idle_timeout {
        return false;
    }
    guard.runtime = None;
    true
}

/// Acquire a lease on the global desktop WASM runtime.
///
/// Lazy-creates the runtime on first use. The returned [`RuntimeLease`]
/// keeps the runtime alive while it exists; drop it when the caller is
/// finished to let the idle reaper reclaim the engine eventually.
pub fn acquire_runtime() -> Result<RuntimeLease, super::WasmRunError> {
    let state = global_state();
    let runtime_arc = {
        let mut guard = lock_or_recover(&state);
        if guard.runtime.is_none() {
            let new_runtime = WasmRuntime::new()?;
            guard.runtime = Some(Arc::new(new_runtime));
        }
        guard.in_flight = guard.in_flight.saturating_add(1);
        guard.last_used = Instant::now();
        Arc::clone(guard.runtime.as_ref().unwrap_or_else(|| unreachable!()))
    };
    Ok(RuntimeLease {
        runtime: runtime_arc,
        state,
    })
}

/// RAII guard returned by [`acquire_runtime`]. Holds an `Arc` to the
/// runtime and to the lifecycle state so `Drop` can decrement the
/// in-flight counter and refresh `last_used`.
pub struct RuntimeLease {
    runtime: Arc<WasmRuntime>,
    state: Arc<Mutex<LifecycleState>>,
}

impl RuntimeLease {
    pub fn runtime(&self) -> &Arc<WasmRuntime> {
        &self.runtime
    }
}

impl std::ops::Deref for RuntimeLease {
    type Target = WasmRuntime;
    fn deref(&self) -> &Self::Target {
        &self.runtime
    }
}

impl Drop for RuntimeLease {
    fn drop(&mut self) {
        let mut guard = lock_or_recover(&self.state);
        guard.in_flight = guard.in_flight.saturating_sub(1);
        guard.last_used = Instant::now();
    }
}

fn lock_or_recover<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Test helper — build an isolated lifecycle state with a tunable
    /// timeout so we can drive the reaper without waiting five minutes.
    fn isolated_state(timeout: Duration) -> Arc<Mutex<LifecycleState>> {
        Arc::new(Mutex::new(LifecycleState::new(timeout)))
    }

    fn lease(
        state: &Arc<Mutex<LifecycleState>>,
    ) -> Result<RuntimeLease, super::super::WasmRunError> {
        let mut guard = state.lock().unwrap();
        if guard.runtime.is_none() {
            guard.runtime = Some(Arc::new(WasmRuntime::new()?));
        }
        guard.in_flight = guard.in_flight.saturating_add(1);
        guard.last_used = Instant::now();
        let runtime = Arc::clone(guard.runtime.as_ref().unwrap());
        drop(guard);
        Ok(RuntimeLease {
            runtime,
            state: Arc::clone(state),
        })
    }

    #[test]
    fn reaper_drops_idle_runtime() {
        let state = isolated_state(Duration::from_millis(50));

        // First call creates the runtime.
        let first_lease = lease(&state).expect("runtime builds");
        assert!(state.lock().unwrap().runtime.is_some());
        drop(first_lease);

        // Still within the timeout window.
        assert!(!reap_once(&state), "should not reap while still fresh");

        // Past the (tiny) idle timeout.
        std::thread::sleep(Duration::from_millis(80));
        assert!(reap_once(&state), "should reap after idle timeout");
        assert!(state.lock().unwrap().runtime.is_none());
    }

    #[test]
    fn reaper_respects_in_flight_lease() {
        let state = isolated_state(Duration::from_millis(10));

        let _hold = lease(&state).expect("runtime builds");
        std::thread::sleep(Duration::from_millis(50));

        // In-flight = 1, reaper must leave the runtime alone even though
        // the idle window has clearly elapsed.
        assert!(!reap_once(&state), "should never reap while leased");
        assert!(state.lock().unwrap().runtime.is_some());
    }

    #[test]
    fn lazy_creation_is_observable() {
        let state = isolated_state(Duration::from_secs(60));
        assert!(state.lock().unwrap().runtime.is_none());

        let lease1 = lease(&state).expect("runtime builds");
        assert!(state.lock().unwrap().runtime.is_some());
        assert_eq!(state.lock().unwrap().in_flight, 1);

        let lease2 = lease(&state).expect("runtime reused");
        assert_eq!(state.lock().unwrap().in_flight, 2);

        drop(lease1);
        assert_eq!(state.lock().unwrap().in_flight, 1);
        drop(lease2);
        assert_eq!(state.lock().unwrap().in_flight, 0);
    }
}
