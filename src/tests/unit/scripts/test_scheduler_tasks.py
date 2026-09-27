from ii_agent.workers.cron import tasks


class FakeScheduler:
    def __init__(self):
        self.running = False
        self.jobs = []
        self.started = 0
        self.stopped = 0

    def add_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))

    def start(self):
        self.running = True
        self.started += 1

    def shutdown(self, wait=True):
        self.running = False
        self.stopped += 1

    def get_jobs(self):
        return self.jobs


def test_start_scheduler_registers_cleanup_jobs(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.start_scheduler()

    assert fake_scheduler.started == 1
    # Two cleanup jobs + one daily lifecycle-invariants probe
    assert len(fake_scheduler.jobs) == 3
    job_ids = [j[1]["id"] for j in fake_scheduler.jobs]
    assert "cleanup_stale_agent_run_tasks" in job_ids
    assert "cleanup_stale_chat_messages" in job_ids
    assert "run_purge_invariants_check" in job_ids


def test_shutdown_scheduler_is_idempotent(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 0

    fake_scheduler.running = True
    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 1


# ──────────────────────────────────────────────────────────────────────────────
# Host-class detection + misfire tuning
# ──────────────────────────────────────────────────────────────────────────────


def test_host_class_env_override_bare(monkeypatch):
    monkeypatch.setenv("IIA_CRON_HOST_CLASS", "bare")
    host_class, reason = tasks._detect_host_class()
    assert host_class == "bare"
    assert "IIA_CRON_HOST_CLASS" in reason


def test_host_class_env_override_vm(monkeypatch):
    monkeypatch.setenv("IIA_CRON_HOST_CLASS", "vm")
    host_class, reason = tasks._detect_host_class()
    assert host_class == "vm"
    assert "IIA_CRON_HOST_CLASS" in reason


def test_host_class_env_override_invalid_falls_through(monkeypatch, tmp_path):
    """Bogus override values must not short-circuit detection."""
    monkeypatch.setenv("IIA_CRON_HOST_CLASS", "garbage")
    fake_proc_version = tmp_path / "version"
    fake_proc_version.write_text("Linux version 5.15.0-generic (Ubuntu)")
    fake_cpuinfo = tmp_path / "cpuinfo"
    fake_cpuinfo.write_text("flags : fpu vme de pse tsc\n")
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, reason = tasks._detect_host_class()
    assert host_class == "bare"
    assert "no virtualisation" in reason.lower()


def test_host_class_detects_wsl(monkeypatch, tmp_path):
    monkeypatch.delenv("IIA_CRON_HOST_CLASS", raising=False)
    (tmp_path / "version").write_text(
        "Linux version 5.15.0-microsoft-standard-WSL2 (oe-user@oe-host)"
    )
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, reason = tasks._detect_host_class()
    assert host_class == "vm"
    assert "WSL" in reason


def test_host_class_detects_hypervisor_flag(monkeypatch, tmp_path):
    monkeypatch.delenv("IIA_CRON_HOST_CLASS", raising=False)
    (tmp_path / "version").write_text("Linux version 5.15.0-generic\n")
    (tmp_path / "cpuinfo").write_text(
        "processor : 0\n"
        "vendor_id : GenuineIntel\n"
        "flags     : fpu vme de pse tsc msr pae hypervisor lahf_lm\n"
    )
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, reason = tasks._detect_host_class()
    assert host_class == "vm"
    assert "hypervisor" in reason


def test_host_class_bare_metal(monkeypatch, tmp_path):
    monkeypatch.delenv("IIA_CRON_HOST_CLASS", raising=False)
    (tmp_path / "version").write_text("Linux version 5.15.0-generic\n")
    (tmp_path / "cpuinfo").write_text(
        "processor : 0\nvendor_id : GenuineIntel\nflags     : fpu vme de pse tsc msr pae lahf_lm\n"
    )
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, reason = tasks._detect_host_class()
    assert host_class == "bare"
    assert "no virtualisation" in reason.lower()


def test_host_class_handles_missing_proc_files(monkeypatch, tmp_path):
    """OSError on /proc reads must not crash detection."""
    monkeypatch.delenv("IIA_CRON_HOST_CLASS", raising=False)
    # tmp_path is empty → reads will OSError, function should treat as bare
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, _ = tasks._detect_host_class()
    assert host_class == "bare"


def test_hypervisor_substring_does_not_false_match(monkeypatch, tmp_path):
    """A flag named e.g. 'nothypervisor' must not match the ' hypervisor ' probe."""
    monkeypatch.delenv("IIA_CRON_HOST_CLASS", raising=False)
    (tmp_path / "version").write_text("Linux version 5.15.0-generic\n")
    (tmp_path / "cpuinfo").write_text("flags : fpu vme nothypervisor lahf_lm\n")
    monkeypatch.setattr(tasks, "Path", _path_factory(tmp_path))

    host_class, _ = tasks._detect_host_class()
    assert host_class == "bare"


def test_start_scheduler_applies_invariants_grace_for_vm(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)
    monkeypatch.setattr(tasks, "_HOST_CLASS", "vm")
    monkeypatch.setattr(tasks, "_HOST_CLASS_REASON", "test forced vm")

    tasks.start_scheduler()

    invariants_job = next(
        j for j in fake_scheduler.jobs if j[1]["id"] == "run_purge_invariants_check"
    )
    kwargs = invariants_job[1]
    # 6 hours of grace on a VM so an overnight host suspend doesn't drop the run
    assert kwargs["misfire_grace_time"] == 6 * 3600
    assert kwargs["coalesce"] is True


def test_start_scheduler_applies_invariants_grace_for_bare(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)
    monkeypatch.setattr(tasks, "_HOST_CLASS", "bare")
    monkeypatch.setattr(tasks, "_HOST_CLASS_REASON", "test forced bare")

    tasks.start_scheduler()

    invariants_job = next(
        j for j in fake_scheduler.jobs if j[1]["id"] == "run_purge_invariants_check"
    )
    kwargs = invariants_job[1]
    # 30 min on bare metal: tolerate transient stalls without hiding real ones
    assert kwargs["misfire_grace_time"] == 1800
    assert kwargs["coalesce"] is True


def test_job_defaults_shape():
    """Module-level job defaults must always carry coalesce + max_instances."""
    assert tasks._JOB_DEFAULTS["coalesce"] is True
    assert tasks._JOB_DEFAULTS["max_instances"] == 1
    assert tasks._JOB_DEFAULTS["misfire_grace_time"] in {60, 3600}


def _path_factory(base):
    """Build a Path stand-in that redirects /proc/* reads under ``base``.

    Returned callable mimics the ``Path`` constructor: when called with a path
    starting with ``/proc/`` it rewrites the lookup to ``base / <basename>``;
    other paths fall through to the real ``pathlib.Path``.
    """
    from pathlib import Path as _RealPath

    def _factory(p):
        s = str(p)
        if s.startswith("/proc/"):
            return base / _RealPath(s).name
        return _RealPath(p)

    return _factory
