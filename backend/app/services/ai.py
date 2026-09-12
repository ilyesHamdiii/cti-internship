import asyncio
import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.schemas.ai import CtiAnalysisResponse, SigmaGenerationResponse, SigmaRepairResponse

T = TypeVar("T", bound=BaseModel)


PROMPTS: dict[str, dict[str, str]] = {
    "cti_behavior_extraction_v2": {
        "system": (
            "You are a detection engineer. Return only JSON matching the requested schema. "
            "Extract independently detectable behaviors from the normalized CTI. "
            "Use only evidence references that exist in the input. Do not include chain-of-thought."
        )
    },
    "sigma_generation_v2": {
        "system": (
            "You are a Sigma detection engineer. Return only JSON matching the requested schema. "
            "Generate one Sigma rule grounded in the behavior, verified ATT&CK mappings, telemetry, "
            "and evidence. Do not include chain-of-thought."
        )
    },
    "sigma_repair_v2": {
        "system": (
            "You repair Sigma rules. Return only JSON matching the requested schema. Address the "
            "structured validation and compiler failures, preserve valid intent, and incorporate "
            "analyst instructions by interpreting detection requirements before changing Sigma. "
            "Detection values must come from CTI evidence, normalized observables, recognized "
            "behavioral patterns, explicit quoted technical literals, or well-defined domain "
            "mappings. Never copy ordinary instruction prose into Sigma selections. Do not include "
            "chain-of-thought."
        )
    },
}


class AiProvider(ABC):
    provider_name: str

    @abstractmethod
    async def analyze_cti(
        self, normalized_cti: dict[str, Any]
    ) -> tuple[CtiAnalysisResponse, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def generate_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaGenerationResponse, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def repair_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaRepairResponse, dict[str, Any]]:
        raise NotImplementedError


class DeterministicFixtureProvider(AiProvider):
    provider_name = "fixture"

    async def analyze_cti(
        self, normalized_cti: dict[str, Any]
    ) -> tuple[CtiAnalysisResponse, dict[str, Any]]:
        text = evidence_text(normalized_cti)
        behaviors: list[dict[str, Any]] = []
        lowered = text.lower()
        if "wmic" in lowered or "wmi" in lowered:
            behaviors.append(
                behavior(
                    "wmi",
                    "WMI process execution",
                    "process_execution",
                    "execute",
                    "remote process",
                    "wmic.exe",
                    "T1047",
                    "Windows Management Instrumentation",
                    "execution",
                    "Execution",
                    "process",
                    ["process_name", "command_line"],
                )
            )
        if "schtasks" in lowered or "scheduled task" in lowered:
            behaviors.append(
                behavior(
                    "scheduled_task",
                    "Scheduled task persistence",
                    "persistence",
                    "persist",
                    "scheduled task",
                    "schtasks.exe",
                    "T1053.005",
                    "Scheduled Task",
                    "persistence",
                    "Persistence",
                    "process",
                    ["process_name", "command_line"],
                )
            )
        if "credential" in lowered or "lsass" in lowered or "mimikatz" in lowered:
            behaviors.append(
                behavior(
                    "credential_dumping",
                    "Credential dumping from LSASS",
                    "credential_access",
                    "dump",
                    "lsass memory",
                    "process access",
                    "T1003.001",
                    "LSASS Memory",
                    "credential-access",
                    "Credential Access",
                    "process",
                    ["process_name", "command_line"],
                )
            )
        if "rundll32" in lowered:
            behaviors.append(
                behavior(
                    "rundll32",
                    "Suspicious rundll32 execution",
                    "process_execution",
                    "execute",
                    "DLL entry point",
                    "rundll32.exe",
                    "T1218.011",
                    "Rundll32",
                    "defense-evasion",
                    "Defense Evasion",
                    "process",
                    ["process_name", "command_line"],
                )
            )
        if "powershell" in lowered or "-enc" in lowered or "encodedcommand" in lowered:
            behaviors.append(
                behavior(
                    "powershell_encoded",
                    "PowerShell encoded command execution",
                    "process_execution",
                    "execute",
                    "PowerShell",
                    "powershell.exe -EncodedCommand",
                    "T1059.001",
                    "PowerShell",
                    "execution",
                    "Execution",
                    "process",
                    ["process_name", "command_line"],
                )
            )
        if "missing telemetry" in lowered or "cloud-only" in lowered:
            behaviors.append(
                behavior(
                    "cloud_visibility_gap",
                    "Cloud control-plane action without telemetry",
                    "cloud_activity",
                    "modify",
                    "cloud control plane",
                    "cloud api",
                    "T1098",
                    "Account Manipulation",
                    "persistence",
                    "Persistence",
                    "cloud_audit",
                    ["event_name", "user", "source_ip"],
                )
            )
        if not behaviors:
            behaviors.append(
                behavior(
                    "low_confidence",
                    "Insufficiently specific suspicious activity",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "T1059.001",
                    "PowerShell",
                    "execution",
                    "Execution",
                    "process",
                    ["process_name"],
                    confidence=0.30,
                )
            )
        if "supervisor_invalid_sigma" in lowered:
            behaviors[0]["summary"] = f"{behaviors[0]['summary']} supervisor_invalid_sigma"
            behaviors[0]["observables"].append(
                {"type": "test_marker", "value": "supervisor_invalid_sigma"}
            )
        if "supervisor_safety_fail" in lowered:
            behaviors[0]["summary"] = f"{behaviors[0]['summary']} supervisor_safety_fail"
            behaviors[0]["observables"].append(
                {"type": "test_marker", "value": "supervisor_safety_fail"}
            )
        payload = {
            "behaviors": behaviors,
            "structured_justification": justification(
                ["input_sensitive_fixture_classification"],
                [b["evidence_refs"][0] for b in behaviors if b["evidence_refs"]],
                confidence=max(b["confidence"] for b in behaviors),
            ),
        }
        response = CtiAnalysisResponse.model_validate(payload)
        return response, usage(
            "cti_behavior_extraction_v2",
            normalized_cti,
            response.model_dump(),
            "fixture",
            "deterministic-fixture",
        )

    async def generate_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaGenerationResponse, dict[str, Any]]:
        response = SigmaGenerationResponse.model_validate(
            build_sigma_response(payload, repaired=False)
        )
        return response, usage(
            "sigma_generation_v2",
            payload,
            response.model_dump(),
            "fixture",
            "deterministic-fixture",
        )

    async def repair_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaRepairResponse, dict[str, Any]]:
        repaired = build_sigma_response(payload, repaired=True)
        current_candidate = payload.get("candidate")
        if isinstance(current_candidate, dict):
            repaired["sigma"] = json.loads(json.dumps(current_candidate))
            title = str(repaired["sigma"].get("title", "Sigma Candidate"))
            if not title.endswith(" - Repaired"):
                repaired["sigma"]["title"] = f"{title} - Repaired"
        plan = plan_semantic_repair(payload, repaired["sigma"])
        repaired["sigma"] = apply_repair_plan(repaired["sigma"], plan)
        repaired["addressed_failures"] = plan["validation_failures_addressed"]
        repaired["instruction_interpretation"] = plan["instruction_interpretation"]
        repaired["fields_changed"] = plan["fields_changed"]
        repaired["selections_added"] = plan["selections_added"]
        repaired["selections_removed"] = plan["selections_removed"]
        repaired["selections_modified"] = plan["selections_modified"]
        repaired["validation_failures_addressed"] = plan["validation_failures_addressed"]
        repaired["unresolved_issues"] = plan["unresolved_issues"]
        repaired["detection_value_evidence"] = plan["detection_value_evidence"]
        repaired["uncertainty"] = plan["uncertainty"]
        repaired["uncertainties"] = plan["uncertainty"]
        repaired["structured_justification"]["decision_factors"].append("semantic_repair_plan")
        repaired["structured_justification"]["change_summary"] = plan["change_summary"]
        repaired["structured_justification"]["uncertainties"] = plan["uncertainty"]
        response = SigmaRepairResponse.model_validate(repaired)
        return response, usage(
            "sigma_repair_v2", payload, response.model_dump(), "fixture", "deterministic-fixture"
        )


class DeepSeekLiveProvider(AiProvider):
    provider_name = "deepseek"

    def __init__(self, settings: Settings):
        self.settings = settings
        key = (
            settings.deepseek_api_key.get_secret_value().strip()
            if settings.deepseek_api_key
            else ""
        )
        if not key:
            raise RuntimeError("DeepSeek API key is required when fixture mode is disabled")
        self.api_key = key

    async def analyze_cti(
        self, normalized_cti: dict[str, Any]
    ) -> tuple[CtiAnalysisResponse, dict[str, Any]]:
        return await self._call("cti_behavior_extraction_v2", normalized_cti, CtiAnalysisResponse)

    async def generate_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaGenerationResponse, dict[str, Any]]:
        return await self._call("sigma_generation_v2", payload, SigmaGenerationResponse)

    async def repair_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaRepairResponse, dict[str, Any]]:
        return await self._call("sigma_repair_v2", payload, SigmaRepairResponse)

    async def _call(
        self, prompt_version: str, payload: dict[str, Any], schema: type[T]
    ) -> tuple[T, dict[str, Any]]:
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    result = await client.post(
                        f"{str(self.settings.deepseek_base_url).rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.settings.deepseek_model,
                            "messages": [
                                {"role": "system", "content": PROMPTS[prompt_version]["system"]},
                                {
                                    "role": "user",
                                    "content": json.dumps(
                                        {
                                            "prompt_version": prompt_version,
                                            "schema": schema.model_json_schema(),
                                            "input": payload,
                                        }
                                    ),
                                },
                            ],
                            "response_format": {"type": "json_object"},
                        },
                    )
                    result.raise_for_status()
                    data = result.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = schema.model_validate_json(content)
                    meta = usage(
                        prompt_version,
                        payload,
                        parsed.model_dump(),
                        "deepseek",
                        self.settings.deepseek_model,
                        data.get("usage", {}),
                    )
                    meta["latency_ms"] = int((time.perf_counter() - started) * 1000)
                    meta["attempts"] = attempt + 1
                    return parsed, meta
            except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                last_error = exc
                await asyncio.sleep(0.25 * (2**attempt))
        raise DeepSeekProviderError(
            sanitize_provider_error(last_error, prompt_version, time.perf_counter() - started)
        )


class DeepSeekProviderError(RuntimeError):
    def __init__(self, error_json: dict[str, Any]):
        self.error_json = error_json
        super().__init__(f"DeepSeek call failed after retries: {error_json['error_type']}")


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.provider: AiProvider = (
            DeterministicFixtureProvider()
            if self.settings.ai_fixture_mode
            else DeepSeekLiveProvider(self.settings)
        )

    async def analyze_cti(
        self, normalized_cti: dict[str, Any]
    ) -> tuple[CtiAnalysisResponse, dict[str, Any]]:
        return await self.provider.analyze_cti(normalized_cti)

    async def generate_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaGenerationResponse, dict[str, Any]]:
        return await self.provider.generate_sigma(payload)

    async def repair_sigma(
        self, payload: dict[str, Any]
    ) -> tuple[SigmaRepairResponse, dict[str, Any]]:
        return await self.provider.repair_sigma(payload)


def evidence_text(normalized_cti: dict[str, Any]) -> str:
    attributes = normalized_cti.get("attributes", [])
    values = [str(attr.get("value", "")) for attr in attributes if isinstance(attr, dict)]
    return "\n".join(
        [
            str(normalized_cti.get("title", "")),
            str(normalized_cti.get("evidence_text", "")),
            *values,
        ]
    )


def behavior(
    key: str,
    summary: str,
    behavior_type: str,
    action: str,
    target: str,
    mechanism: str,
    technique_id: str,
    technique_name: str,
    tactic_id: str,
    tactic_name: str,
    telemetry_category: str,
    fields: list[str],
    confidence: float = 0.88,
) -> dict[str, Any]:
    evidence = [{"ref": "attribute:1", "excerpt": mechanism, "source_field": "attributes"}]
    return {
        "behavior_key": key,
        "summary": summary,
        "behavior_type": behavior_type,
        "actor_action": action,
        "target": target,
        "execution_mechanism": mechanism,
        "evidence_refs": evidence,
        "observables": [{"type": "process", "value": mechanism}],
        "proposed_attack_mappings": [
            {
                "technique_id": technique_id,
                "technique_name": technique_name,
                "tactic_id": tactic_id,
                "tactic_name": tactic_name,
                "evidence_refs": evidence,
                "confidence": confidence,
            }
        ],
        "required_telemetry": [{"category": telemetry_category, "fields": fields}],
        "confidence": confidence,
        "uncertainties": [],
    }


def build_sigma_response(payload: dict[str, Any], repaired: bool) -> dict[str, Any]:
    behavior_payload = (
        payload.get("behavior")
        or payload.get("behavior_summary")
        or payload.get("candidate", {}).get("title", "")
    )
    text = json.dumps(behavior_payload, sort_keys=True, default=str).lower()
    analyst_comment = str(payload.get("analyst_comment") or "")
    suffix = " - Repaired" if repaired else ""
    if "wmi" in text:
        title, selection, tags = (
            "WMI Process Execution",
            {"Image|endswith": "\\wmic.exe"},
            ["attack.T1047"],
        )
    elif "scheduled" in text or "schtasks" in text:
        title, selection, tags = (
            "Scheduled Task Persistence",
            {"Image|endswith": "\\schtasks.exe"},
            ["attack.T1053.005"],
        )
    elif "credential" in text or "lsass" in text:
        title, selection, tags = (
            "Potential LSASS Credential Dumping",
            {"CommandLine|contains": "lsass"},
            ["attack.T1003.001"],
        )
    elif "rundll32" in text:
        title, selection, tags = (
            "Suspicious Rundll32 Execution",
            {"Image|endswith": "\\rundll32.exe"},
            ["attack.T1218.011"],
        )
    else:
        title, selection, tags = (
            "PowerShell Encoded Command Execution",
            {"Image|endswith": "\\powershell.exe", "CommandLine|contains": "-enc"},
            ["attack.T1059.001"],
        )
    response: dict[str, Any] = {
        "sigma": {
            "title": f"{title}{suffix}",
            "status": "experimental",
            "description": f"Detects {title.lower()} grounded in CTI evidence.",
            "author": "CTI Detection Engineering Platform",
            "references": [],
            "tags": tags,
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": selection, "condition": "selection"},
            "fields": ["Image", "CommandLine"],
            "falsepositives": ["Legitimate administrative activity"],
            "level": "high",
        },
        "detection_intent": [f"Detect {title.lower()}"],
        "false_positive_notes": ["Review known administrative automation."],
        "structured_justification": justification(
            ["repaired" if repaired else "generated_from_behavior"],
            [],
            confidence=0.86,
            changes=["Applied analyst instruction"] if repaired and analyst_comment else [],
        ),
        "confidence": 0.86,
        "uncertainties": [],
    }
    if "supervisor_invalid_sigma" in text and not repaired:
        response["sigma"]["detection"].pop("condition", None)
    if "supervisor_safety_fail" in text:
        response["sigma"]["detection"]["selection"]["CommandLine|contains"] = [
            "delete important data",
            "delete backups",
            "delete logs",
            "supervisor_safety_fail",
        ]
    return response


ORDINARY_INSTRUCTION_WORDS = {
    "add",
    "also",
    "change",
    "command",
    "detect",
    "include",
    "please",
    "require",
    "requires",
    "requiring",
    "the",
    "to",
    "with",
    "wording",
}

REMOTE_DOWNLOAD_PATTERNS = [
    "Invoke-WebRequest",
    "DownloadString",
    "System.Net.WebClient",
    "Start-BitsTransfer",
    "curl",
    "wget",
]


def plan_semantic_repair(payload: dict[str, Any], sigma: dict[str, Any]) -> dict[str, Any]:
    analyst_comment = str(payload.get("analyst_comment") or "")
    validation = payload.get("validation") or {}
    behavior = payload.get("behavior") or {}
    candidate = payload.get("candidate") or sigma
    context = json.dumps(
        {"behavior": behavior, "candidate": candidate}, sort_keys=True, default=str
    ).lower()
    quoted_literals = [
        match.strip()
        for match in re.findall(r"[\"']([^\"']{1,120})[\"']", analyst_comment)
        if match.strip()
    ]
    lowered = analyst_comment.lower()

    added_values: list[str] = []
    evidence: list[dict[str, object]] = []
    interpretation = (
        "No actionable Sigma selection change was inferred from the analyst instruction."
    )
    unresolved: list[str] = []
    uncertainty: list[str] = []

    if any(
        term in lowered
        for term in [
            "download",
            "remote content",
            "webrequest",
            "web request",
            "webclient",
            "bits",
            "curl",
            "wget",
        ]
    ):
        if (
            "powershell" in context
            or "commandline" in json.dumps(candidate, sort_keys=True, default=str).lower()
        ):
            added_values.extend(REMOTE_DOWNLOAD_PATTERNS)
            interpretation = (
                "Require evidence of remote content download behavior in the process command line."
            )
            evidence.append(
                {
                    "field": "CommandLine",
                    "values": REMOTE_DOWNLOAD_PATTERNS,
                    "source": "recognized_behavioral_pattern",
                    "rationale": "PowerShell and command-line download utilities are standard process telemetry indicators for remote content download behavior.",
                }
            )
        else:
            unresolved.append("remote_download_requested_but_behavior_not_command_line_compatible")
            uncertainty.append(
                "The source behavior does not expose compatible process command-line telemetry."
            )
    elif (
        any(
            str(error.get("code")) == "missing_condition"
            for error in validation.get("errors", [])
            if isinstance(error, dict)
        )
        or "supervisor_invalid_sigma" in context
    ):
        interpretation = "Restore the Sigma condition field required by deterministic validation."

    for literal in quoted_literals:
        if (
            literal.lower() not in {word.lower() for word in ORDINARY_INSTRUCTION_WORDS}
            and literal not in added_values
        ):
            added_values.append(literal)
            interpretation = (
                "Apply explicit analyst-provided technical literal to command-line detection."
            )
            evidence.append(
                {
                    "field": "CommandLine",
                    "values": [literal],
                    "source": "explicit_analyst_literal",
                    "rationale": "The analyst supplied the value as a quoted technical literal.",
                }
            )

    sanitized_values = [
        value for value in added_values if value.strip().lower() not in ORDINARY_INSTRUCTION_WORDS
    ]
    missing_condition_repair = "condition field required" in interpretation
    selections_added = {"CommandLine|contains": sanitized_values} if sanitized_values else {}
    failures = [
        str(error.get("code") or error.get("message") or error)
        for error in validation.get("errors", [])
        if isinstance(error, dict)
    ]
    if analyst_comment and not sanitized_values:
        unresolved.append("analyst_instruction_not_translatable_to_supported_detection_value")
    if missing_condition_repair:
        change_summary = ["Added missing Sigma detection condition"]
    elif sanitized_values and any(
        item.get("source") == "recognized_behavioral_pattern" for item in evidence
    ):
        change_summary = [
            f"Added CommandLine remote-content download patterns: {', '.join(sanitized_values)}"
        ]
    elif sanitized_values:
        change_summary = [
            f"Added CommandLine analyst-provided technical literals: {', '.join(sanitized_values)}"
        ]
    else:
        change_summary = ["No semantic Sigma selection change applied"]

    return {
        "instruction_interpretation": interpretation,
        "fields_changed": ["detection.condition"]
        if missing_condition_repair
        else ["CommandLine"]
        if sanitized_values
        else [],
        "selections_added": selections_added,
        "selections_removed": {},
        "selections_modified": {},
        "validation_failures_addressed": failures or ["analyst_instructions"],
        "unresolved_issues": unresolved,
        "detection_value_evidence": evidence,
        "uncertainty": uncertainty,
        "change_summary": change_summary,
    }


def apply_repair_plan(sigma: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    repaired = cast(dict[str, Any], json.loads(json.dumps(sigma)))
    detection = repaired.setdefault("detection", {})
    selection = detection.setdefault("selection", {})
    if "condition" not in detection and selection:
        detection["condition"] = "selection"
    added_values = list(plan.get("selections_added", {}).get("CommandLine|contains", []))
    if not added_values:
        return repaired

    current = selection.get("CommandLine|contains")
    current_values = current if isinstance(current, list) else ([current] if current else [])
    if current_values and all(str(value).startswith("-") for value in current_values):
        selection.pop("CommandLine|contains", None)
        selection["CommandLine|contains|all"] = list(
            dict.fromkeys(
                [
                    *map(str, selection.get("CommandLine|contains|all", [])),
                    *map(str, current_values),
                ]
            )
        )
        current_values = []
    selection["CommandLine|contains"] = list(
        dict.fromkeys([*map(str, current_values), *map(str, added_values)])
    )
    return repaired


def justification(
    factors: list[str],
    evidence_refs: list[dict[str, Any]],
    confidence: float,
    changes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision_factors": factors,
        "evidence_refs": evidence_refs,
        "attack_rationale": ["Technique selected from behavior semantics"],
        "coverage_rationale": [],
        "telemetry_rationale": ["Telemetry requirements derived from behavior"],
        "confidence": confidence,
        "uncertainties": [],
        "change_summary": changes or [],
    }


def usage(
    prompt_version: str,
    request: dict[str, Any],
    response: dict[str, Any],
    provider: str,
    model: str,
    token_usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    token_usage = token_usage or {
        "prompt_tokens": 100,
        "completion_tokens": 100,
        "total_tokens": 200,
    }
    settings = get_settings()
    request_json = json.dumps(request, sort_keys=True, default=str)
    response_json = json.dumps(response, sort_keys=True, default=str)
    return {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "system_prompt_version": f"{prompt_version}:system",
        "schema_name": "json",
        "input_hash": hashlib.sha256(request_json.encode()).hexdigest(),
        "response_hash": hashlib.sha256(response_json.encode()).hexdigest(),
        "request_payload": request,
        "input_summary": request_json[:500],
        "token_usage": token_usage,
        "estimated_cost": token_usage.get("prompt_tokens", 0) * settings.deepseek_prompt_token_cost
        + token_usage.get("completion_tokens", 0) * settings.deepseek_completion_token_cost,
        "latency_ms": 0,
    }


def sanitize_provider_error(
    error: Exception | None, prompt_version: str, elapsed_seconds: float
) -> dict[str, Any]:
    status_code = None
    error_type = type(error).__name__ if error else "UnknownProviderError"
    message = str(error) if error else "unknown provider error"
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        message = f"HTTP {status_code}"
        if status_code == 429:
            error_type = "RateLimitError"
        elif status_code >= 500:
            error_type = "ProviderServerError"
    elif isinstance(error, httpx.TimeoutException):
        error_type = "ProviderTimeout"
        message = "request timed out"
    elif isinstance(error, ValidationError):
        error_type = "SchemaInvalidProviderResponse"
    elif isinstance(error, (json.JSONDecodeError, ValueError)):
        error_type = "MalformedProviderResponse"
    return {
        "provider": "deepseek",
        "prompt_version": prompt_version,
        "error_type": error_type,
        "message": message[:300],
        "status_code": status_code,
        "latency_ms": int(elapsed_seconds * 1000),
    }
