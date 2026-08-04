from datetime import datetime
from importlib import metadata
from typing import Any

import yaml
from pydantic import ValidationError
from sigma.collection import SigmaCollection

from app.core.config import get_settings
from app.schemas.ai import SigmaCandidate


SUPPORTED_LOGSOURCES = {
    ("windows", "process_creation"),
    ("windows", "ps_script"),
    ("windows", "powershell"),
}
SUPPORTED_FIELDS = {
    "Image",
    "CommandLine",
    "ParentImage",
    "ParentCommandLine",
    "User",
    "OriginalFileName",
    "CurrentDirectory",
    "TargetFilename",
    "EventID",
}


class SigmaValidationService:
    def to_yaml(self, candidate: SigmaCandidate) -> str:
        return yaml.safe_dump(candidate.model_dump(exclude_none=True), sort_keys=False)

    def validate(self, payload: dict[str, Any], required_techniques: list[str], telemetry_fields: list[str] | None = None) -> dict[str, Any]:
        started = datetime.utcnow()
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        try:
            candidate = SigmaCandidate.model_validate(payload)
        except ValidationError as exc:
            return invalid("schema_invalid", str(exc), started)

        if "condition" not in candidate.detection:
            errors.append({"code": "missing_condition", "message": "Sigma detection condition is required"})
        if not any(key != "condition" for key in candidate.detection):
            errors.append({"code": "missing_detection_selection", "message": "At least one detection selection is required"})

        product = candidate.logsource.get("product", "")
        category = candidate.logsource.get("category", "")
        if (product, category) not in SUPPORTED_LOGSOURCES:
            errors.append({"code": "unsupported_logsource", "message": f"Unsupported logsource {product}/{category}"})

        tags = {tag.lower() for tag in candidate.tags}
        for technique_id in required_techniques:
            if f"attack.{technique_id.lower()}" not in tags and technique_id.lower() not in tags:
                errors.append({"code": "attack_tag_missing", "message": f"Missing ATT&CK tag {technique_id}"})

        candidate_fields = selection_fields(candidate)
        unsupported = sorted(field for field in candidate_fields if field not in SUPPORTED_FIELDS)
        for field in unsupported:
            warnings.append({"code": "unsupported_field", "message": f"Field {field} is not in the configured field inventory"})
        if telemetry_fields:
            missing_telemetry = sorted(field for field in candidate_fields if field.lower() not in {f.lower() for f in telemetry_fields})
            for field in missing_telemetry:
                warnings.append({"code": "telemetry_field_not_declared", "message": f"Field {field} is not present in available telemetry requirements"})

        yaml_text = self.to_yaml(candidate)
        compiled_query: str | None = None
        compiler_error: str | None = None
        compiler_version = package_version("pysigma-backend-splunk")
        try:
            collection = SigmaCollection.from_yaml(yaml_text)
            compiled = self.compile(collection)
            compiled_query = "\n".join(compiled)
        except Exception as exc:
            compiler_error = str(exc)
            errors.append({"code": "pysigma_compile_failed", "message": compiler_error})

        quality = self.score(candidate, errors, warnings)
        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        return {
            "valid": not errors and quality >= get_settings().quality_threshold,
            "repairable": True,
            "candidate": candidate,
            "errors": errors,
            "warnings": warnings,
            "compiled_outputs": {
                "target": get_settings().sigma_target,
                "backend": "splunk",
                "compiler": "pysigma-backend-splunk",
                "compiler_version": compiler_version,
                "query": compiled_query,
                "compiler_errors": [compiler_error] if compiler_error else [],
                "validation_duration_ms": duration_ms,
            },
            "quality_score": quality,
        }

    def compile(self, collection: SigmaCollection) -> list[str]:
        if get_settings().sigma_target != "splunk":
            raise ValueError(f"Unsupported Sigma target {get_settings().sigma_target}")
        from sigma.backends.splunk import SplunkBackend

        return SplunkBackend().convert(collection)

    def health_probe(self) -> dict[str, Any]:
        candidate = {
            "title": "pySigma Health Probe",
            "description": "Minimal Windows process creation compile probe.",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {"Image|endswith": "\\cmd.exe"}, "condition": "selection"},
            "tags": ["attack.T1059"],
            "falsepositives": [],
            "level": "low",
        }
        result = self.validate(candidate, ["T1059"], ["Image"])
        return {"status": "available" if result["valid"] else "unhealthy", "details": result["compiled_outputs"] | {"errors": result["errors"], "warnings": result["warnings"]}}

    def score(self, candidate: SigmaCandidate, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> float:
        score = 100.0
        score -= len(errors) * 35
        score -= len(warnings) * 5
        if candidate.level in {"high", "critical"}:
            score += 2
        if len(candidate.description) < 20:
            score -= 10
        if not candidate.falsepositives:
            score -= 5
        return max(0.0, min(100.0, score))


def selection_fields(candidate: SigmaCandidate) -> set[str]:
    fields: set[str] = set()
    for key, value in candidate.detection.items():
        if key == "condition" or not isinstance(value, dict):
            continue
        for field_expr in value:
            fields.add(str(field_expr).split("|", 1)[0])
    return fields


def invalid(code: str, message: str, started: datetime) -> dict[str, Any]:
    return {
        "valid": False,
        "repairable": True,
        "candidate": None,
        "errors": [{"code": code, "message": message}],
        "warnings": [],
        "compiled_outputs": {"target": get_settings().sigma_target, "backend": "splunk", "query": None, "compiler_errors": [message], "validation_duration_ms": int((datetime.utcnow() - started).total_seconds() * 1000)},
        "quality_score": 0.0,
    }


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None
