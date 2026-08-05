from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.enums import DetectionStatus, DetectionType, UserRole
from app.models.models import (
    AttackTechnique,
    DetectionAttackMapping,
    DetectionCatalog,
    Setting,
    TelemetrySource,
    User,
)
from app.services.fingerprinting import fingerprint_behavior


def seed_baseline(db: Session) -> None:
    settings = get_settings()
    if db.scalar(select(User).where(User.email == settings.seeded_admin_email)) is None:
        db.add(
            User(
                email=settings.seeded_admin_email,
                password_hash=hash_password(settings.seeded_admin_password.get_secret_value()),
                display_name="Local Admin",
                role=UserRole.admin,
            )
        )
    techniques = [
        (
            "T1566.001",
            "Spearphishing Attachment",
            "Adversaries may send spearphishing emails with malicious attachments.",
            ["initial-access"],
            ["Windows", "macOS", "Linux"],
            ["Email: Email Message"],
        ),
        (
            "T1204.002",
            "Malicious File",
            "Adversaries may rely on users opening a malicious file for execution.",
            ["execution"],
            ["Windows", "macOS", "Linux"],
            ["File: File Creation", "Process: Process Creation"],
        ),
        (
            "T1059.001",
            "PowerShell",
            "Command and scripting interpreter: PowerShell.",
            ["execution"],
            ["Windows"],
            ["Process: Process Creation"],
        ),
        (
            "T1059.003",
            "Windows Command Shell",
            "Adversaries may abuse cmd.exe to execute commands.",
            ["execution"],
            ["Windows"],
            ["Process: Process Creation"],
        ),
        (
            "T1047",
            "Windows Management Instrumentation",
            "Adversaries may abuse Windows Management Instrumentation to execute commands.",
            ["execution"],
            ["Windows"],
            ["Process: Process Creation"],
        ),
        (
            "T1053.005",
            "Scheduled Task",
            "Adversaries may abuse scheduled tasks for persistence.",
            ["persistence"],
            ["Windows"],
            ["Process: Process Creation", "Scheduled Job: Scheduled Job Creation"],
        ),
        (
            "T1547.001",
            "Registry Run Keys / Startup Folder",
            "Adversaries may use Run keys or startup folders to establish persistence.",
            ["persistence", "privilege-escalation"],
            ["Windows"],
            ["Windows Registry: Windows Registry Key Modification", "Process: Process Creation"],
        ),
        (
            "T1055",
            "Process Injection",
            "Adversaries may inject code into processes to evade defenses or elevate privileges.",
            ["defense-evasion", "privilege-escalation"],
            ["Windows", "macOS", "Linux"],
            ["Process: OS API Execution", "Process: Process Access"],
        ),
        (
            "T1562.001",
            "Disable or Modify Tools",
            "Adversaries may disable or modify security tools to avoid detection.",
            ["defense-evasion"],
            ["Windows", "macOS", "Linux", "IaaS"],
            ["Process: Process Creation", "Service: Service Modification"],
        ),
        (
            "T1027",
            "Obfuscated Files or Information",
            "Adversaries may obfuscate files, scripts, or command content.",
            ["defense-evasion"],
            ["Windows", "macOS", "Linux"],
            ["Command: Command Execution", "File: File Metadata"],
        ),
        (
            "T1003.001",
            "LSASS Memory",
            "Adversaries may dump LSASS memory for credentials.",
            ["credential-access"],
            ["Windows"],
            ["Process: Process Access"],
        ),
        (
            "T1218.011",
            "Rundll32",
            "Adversaries may abuse rundll32.exe to proxy execution.",
            ["defense-evasion"],
            ["Windows"],
            ["Process: Process Creation"],
        ),
        (
            "T1098",
            "Account Manipulation",
            "Adversaries may manipulate accounts for persistence.",
            ["persistence"],
            ["IaaS", "SaaS"],
            ["User Account: User Account Modification"],
        ),
        (
            "T1082",
            "System Information Discovery",
            "Adversaries may collect system information during discovery.",
            ["discovery"],
            ["Windows", "macOS", "Linux"],
            ["Process: Process Creation", "Command: Command Execution"],
        ),
        (
            "T1016",
            "System Network Configuration Discovery",
            "Adversaries may collect network configuration information.",
            ["discovery"],
            ["Windows", "macOS", "Linux"],
            ["Process: Process Creation", "Command: Command Execution"],
        ),
        (
            "T1105",
            "Ingress Tool Transfer",
            "Adversaries may transfer tools or files into a compromised environment.",
            ["command-and-control"],
            ["Windows", "macOS", "Linux"],
            ["Network Traffic: Network Connection", "File: File Creation"],
        ),
        (
            "T1071.001",
            "Web Protocols",
            "Adversaries may use HTTP or HTTPS for command and control.",
            ["command-and-control"],
            ["Windows", "macOS", "Linux"],
            ["Network Traffic: Network Connection"],
        ),
        (
            "T1041",
            "Exfiltration Over C2 Channel",
            "Adversaries may steal data over an existing command and control channel.",
            ["exfiltration"],
            ["Windows", "macOS", "Linux"],
            ["Network Traffic: Network Connection"],
        ),
        (
            "T1486",
            "Data Encrypted for Impact",
            "Adversaries may encrypt data to interrupt availability.",
            ["impact"],
            ["Windows", "macOS", "Linux", "IaaS"],
            ["File: File Modification", "Process: Process Creation"],
        ),
    ]
    for technique_id, name, description, tactics, platforms, data_sources in techniques:
        if db.get(AttackTechnique, technique_id) is None:
            db.add(
                AttackTechnique(
                    technique_id=technique_id,
                    name=name,
                    description=description,
                    revoked=False,
                    deprecated=False,
                    tactics=tactics,
                    platforms=platforms,
                    data_sources=data_sources,
                    version="fixture-attack-reference",
                )
            )
    existing = db.scalar(
        select(TelemetrySource).where(TelemetrySource.name == "Windows Process Creation")
    )
    if existing is None:
        db.add(
            TelemetrySource(
                name="Windows Process Creation",
                category="process",
                platform="windows",
                enabled=True,
                retention_days=30,
                fields=["process_name", "command_line", "parent_process_name"],
                owner="SOC",
            )
        )
    cloud_existing = db.scalar(
        select(TelemetrySource).where(TelemetrySource.name == "Cloud Audit Events")
    )
    if cloud_existing is None:
        db.add(
            TelemetrySource(
                name="Cloud Audit Events",
                category="cloud_audit",
                platform="cloud",
                enabled=False,
                retention_days=0,
                fields=["event_name", "user", "source_ip"],
                owner="Cloud",
            )
        )
    detection = db.scalar(
        select(DetectionCatalog).where(DetectionCatalog.name == "Existing WMI Process Execution")
    )
    if detection is None:
        normalized_logic = {
            "summary": "wmic process call create execution",
            "attack": ["T1047"],
            "telemetry": [{"category": "process", "fields": ["process_name", "command_line"]}],
        }
        detection = DetectionCatalog(
            name="Existing WMI Process Execution",
            detection_type=DetectionType.sigma,
            source="local_seed",
            content="title: Existing WMI Process Execution\nstatus: stable\n",
            normalized_logic=normalized_logic,
            behavior_fingerprint=fingerprint_behavior(normalized_logic),
            status=DetectionStatus.active,
        )
        db.add(detection)
        db.flush()
        db.add(
            DetectionAttackMapping(
                detection_id=detection.id, technique_id="T1047", tactic_id="execution"
            )
        )
    default_settings = {
        "ai.fixture_mode": settings.ai_fixture_mode,
        "ai.model": settings.deepseek_model,
        "misp.poll_interval_seconds": settings.misp_poll_interval_seconds,
        "sigma.target": settings.sigma_target,
        "validation.max_repair_attempts": settings.max_repair_attempts,
        "validation.quality_threshold": settings.quality_threshold,
        "secrets.deepseek_configured": bool(settings.deepseek_api_key),
        "secrets.misp_configured": bool(settings.misp_api_key),
    }
    for key, value in default_settings.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value={"value": value}))
    db.commit()
