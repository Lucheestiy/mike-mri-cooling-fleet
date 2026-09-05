from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scoreboard_exposes_service_identity_and_ram_journal_counts() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text()
    javascript = (ROOT / "dashboard/static/app.js").read_text()
    for element_id in ("serviceUserCount", "serviceUserDetail", "sensorHealthCount", "sensorHealthDetail", "probeMapCount", "probeMapDetail", "gpioMapCount", "gpioMapDetail", "runtimePolicyCount", "runtimePolicyDetail", "updateCount", "updateDetail", "osPostureCount", "osPostureDetail", "journalPilotCount", "optimizationDetail", "fieldDetail", "opsCoreDetail"):
        assert f'id="{element_id}"' in html
        assert f"$('#{element_id}')" in javascript
    assert "sensor_services_nonroot" in javascript
    assert "probe_mappings_aligned" in javascript
    assert "EXACT MAPPING ALIGNED" in javascript
    assert "runtime_policies_aligned" in javascript
    assert "packages_eligible_ready" in javascript
    assert "packages_eligible_held" in javascript
    assert "Current package cache:" in javascript
    assert "cached_eligible" in javascript
    assert "missing_candidate_names" in javascript
    assert "renderOsPosture" in javascript
    assert "OS LIFECYCLE" in javascript
    assert "renderServicePosture" in javascript
    assert "renderSensorHealth" in javascript
    assert "sensor_operational" in javascript
    assert "runtime · probes · service · live telemetry" in javascript
    assert "SENSOR SERVICE UNIT" in javascript
    assert "restart_policies_aligned" in javascript
    assert "restart_recovery_verified" in javascript
    assert "automatic recovery · VERIFIED" in javascript
    assert "renderWaves" in javascript
    assert "CRASH RECOVERY" in javascript
    assert "EFFECTIVE RUNTIME POLICY" in javascript
    assert "volatile_journal_pilots" in javascript
    assert "ram_budget_healthy" in javascript
    assert "ram_budget_assessed" in javascript
    assert "RAM safety budget" in javascript
    assert "no swap is acceptable with healthy headroom" in javascript
    assert "headless_canary_active" in javascript
    assert "rsyslog_ram_pilots" in javascript
    assert "camera_ram_workload_verified" in javascript
    assert "camera_observations_pending" in javascript
    assert "PRODUCTION CAMERA PROOF" in javascript
    assert "superseded_by_current_camera" in javascript
    assert "NEW BUILD PROOF PENDING" in javascript
    assert "REVIEWED CAMERA TARGET CONTRACT" in javascript
    assert "cameraConvergence.target_contract" in javascript
    assert "UPLOAD-DISABLED HARDWARE CANARY" in javascript
    assert "cameraCanary?.passed&&cameraCanary?.matches_current_camera" in javascript
    assert "CAMERA V3 DEPLOYMENT" in javascript
    assert "cameraDeployment?.passed&&cameraDeployment?.matches_current_camera" in javascript
    assert "renderWaves(data.maintenance_waves||[])" in javascript
    assert "OPERATOR DECISION" in javascript
    assert "privilege wrapper" in javascript
    assert "backup_export_ready" in javascript
    assert "backup_onboarding_complete" in javascript
    assert "backup_onboarding_prepared" in javascript
    assert "backup_restore_verifier_status" in javascript
    assert "backup_restore_sweep_status" in javascript
    assert "weekly sweep scheduled" in javascript
    assert "backup_restore_failed_repositories" in javascript
    assert "backup_batch_result" in javascript
    assert "backup_batch_completed_targets" in javascript
    assert "renderBackupBatch" in javascript
    assert "restore verifier needs hub sudo install" in javascript
    assert "field_priority" in javascript
    assert "facts?.route" in javascript
    assert "eligible / ${listed} listed" in javascript
    assert "PACKAGE MAINTENANCE" in javascript
    assert "ELIGIBLE / HELD" in javascript
    assert "DEFERRED / NOT FORCED" in javascript
    assert "eligiblePackageNames" in javascript
    assert "deferredPackageNames" in javascript
    assert "update_policy_assessment" in javascript
    assert "Automatic-update contract:" in javascript
    assert "automatic reboot" in javascript
    assert "HELD PACKAGES" in javascript


def test_operational_software_ledger_is_version_and_os_cohort_aware() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "dashboard/static/styles.css").read_text(encoding="utf-8")
    for element_id in ("softwareMatrixTitle", "softwareMatrixCount", "softwareMatrixDetail", "softwareLedger"):
        assert f'id="{element_id}"' in html
    assert "renderSoftwareMatrix" in javascript
    assert "operational_package_matrix" in javascript
    assert "os_cohorts" in javascript
    assert "same_cohort_spreads" in javascript
    assert "pkg.channels" in javascript
    assert "CHANNEL ·" in javascript
    assert "tailscaleChannel=ops.package_channels" in javascript
    assert "Tailscale channel:" in javascript
    assert "host_labels" in javascript
    assert "VERSION SPREAD" in javascript
    assert "MISSING" in javascript
    assert ".software-row" in stylesheet
    assert ".channel-chip" in stylesheet
    assert "prefers-reduced-motion" in stylesheet


def test_sensor_runtime_profiles_are_profile_aware_and_accessible() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "dashboard/static/styles.css").read_text(encoding="utf-8")
    for element_id in (
        "runtimeMatrixTitle",
        "runtimeMatrixCount",
        "runtimeMatrixDetail",
        "sensorRuntimeProfiles",
    ):
        assert f'id="{element_id}"' in html
    assert "renderSensorRuntime" in javascript
    assert "sensor_runtime_matrix" in javascript
    assert "sensorRuntime=f.sensor_runtime" in javascript
    assert "Active sensor virtualenv:" in javascript
    assert "profile.profile==='cv'" in javascript
    assert "profile.profile==='camera'" in javascript
    assert "installed camera environments complete" in javascript
    assert "Installed camera virtualenv:" in javascript
    assert "OS UPGRADE VERIFICATION" in javascript
    assert "COMPLETED / VERIFIED" in javascript
    assert "host_labels" in javascript
    assert ".runtime-profile-grid" in stylesheet
    assert ".runtime-profile.cv" in stylesheet


def test_history_evidence_strip_has_api_chart_and_accessible_labels() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "dashboard/static/styles.css").read_text(encoding="utf-8")
    for element_id in ("historyWindow", "availabilityChart", "writeChart", "writeLegend"):
        assert f'id="{element_id}"' in html
    assert "fetch('/api/history'" in javascript
    assert 'role="img"' in javascript
    assert "gaps mean reboot or invalid interval" in html
    assert ".evidence-grid" in stylesheet
    assert "/27" not in javascript


def test_incomplete_audit_is_visibly_disclosed() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "dashboard/static/styles.css").read_text(encoding="utf-8")
    assert 'id="auditWarning"' in html
    assert 'role="alert"' in html
    assert "Incomplete fleet audit" in javascript
    assert "must not authorize maintenance" in javascript
    assert ".audit-warning" in stylesheet


def test_portal_uses_local_fonts_and_declares_browser_security_headers() -> None:
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    stylesheet = (ROOT / "dashboard/static/styles.css").read_text(encoding="utf-8")
    application = (ROOT / "dashboard/app.py").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "src:local" in stylesheet
    for header in (
        "Content-Security-Policy",
        "Cross-Origin-Opener-Policy",
        "Permissions-Policy",
        "Referrer-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "X-Robots-Tag",
    ):
        assert f'"{header}"' in application
