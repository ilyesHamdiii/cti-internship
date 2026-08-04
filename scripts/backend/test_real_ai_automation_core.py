import pytest

from app.graph.runner import DetectionEngineeringGraph
from app.services.ai import DeepSeekClient
from app.services.duplicates import DuplicateDetectionService
from app.services.sigma import SigmaValidationService


def test_detection_engineering_graph_is_compiled_langgraph() -> None:
    graph = DetectionEngineeringGraph(db=None)
    assert graph.compiled_graph is not None
    assert hasattr(graph.compiled_graph, "invoke")
    assert "policy_decision" in graph.nodes
    assert "repair_candidate" in graph.nodes


@pytest.mark.asyncio
async def test_fixture_behavior_extraction_is_input_sensitive() -> None:
    client = DeepSeekClient()
    powershell, _ = await client.analyze_cti({"attributes": [{"id": "1", "value": "powershell.exe -EncodedCommand AAA"}]})
    wmi, _ = await client.analyze_cti({"attributes": [{"id": "1", "value": "wmic process call create calc.exe"}]})
    rundll, _ = await client.analyze_cti({"attributes": [{"id": "1", "value": "rundll32.exe javascript dll execution"}]})

    summaries = {powershell.behaviors[0].summary, wmi.behaviors[0].summary, rundll.behaviors[0].summary}

    assert len(summaries) == 3


@pytest.mark.asyncio
async def test_fixture_sigma_generation_is_input_sensitive() -> None:
    client = DeepSeekClient()
    powershell, _ = await client.generate_sigma({"behavior": {"summary": "PowerShell encoded command execution"}})
    wmi, _ = await client.generate_sigma({"behavior": {"summary": "WMI process execution"}})

    assert powershell.sigma.title != wmi.sigma.title
    assert powershell.sigma.detection != wmi.sigma.detection


@pytest.mark.asyncio
async def test_fixture_semantic_repair_interprets_download_instruction_without_copying_prose() -> None:
    client = DeepSeekClient()
    original, _ = await client.generate_sigma({"behavior": {"summary": "PowerShell encoded command execution"}})

    repaired, _ = await client.repair_sigma(
        {
            "analyst_comment": "Require the command line to include remote content download wording",
            "candidate": original.sigma.model_dump(),
            "behavior": {"summary": "PowerShell encoded command execution", "observables": [{"type": "process", "value": "powershell.exe -EncodedCommand"}]},
            "validation": {"errors": []},
            "available_telemetry": [{"category": "process", "fields": ["Image", "CommandLine"]}],
        }
    )

    selection = repaired.sigma.detection["selection"]
    serialized_selection = str(selection).lower()

    assert "require" not in serialized_selection
    assert "'the'" not in serialized_selection
    assert "command']" not in serialized_selection
    assert selection["CommandLine|contains"] == [
        "Invoke-WebRequest",
        "DownloadString",
        "System.Net.WebClient",
        "Start-BitsTransfer",
        "curl",
        "wget",
    ]
    assert selection["CommandLine|contains|all"] == ["-enc"]
    assert repaired.instruction_interpretation == "Require evidence of remote content download behavior in the process command line."
    assert repaired.detection_value_evidence[0]["source"] == "recognized_behavioral_pattern"


@pytest.mark.asyncio
async def test_fixture_semantic_repair_allows_quoted_technical_literal_only() -> None:
    client = DeepSeekClient()
    original, _ = await client.generate_sigma({"behavior": {"summary": "PowerShell encoded command execution"}})

    repaired, _ = await client.repair_sigma(
        {
            "analyst_comment": "Please include \"FromBase64String\" in command line detection",
            "candidate": original.sigma.model_dump(),
            "behavior": {"summary": "PowerShell encoded command execution"},
            "validation": {"errors": []},
        }
    )

    values = repaired.sigma.detection["selection"]["CommandLine|contains"]
    serialized_selection = str(repaired.sigma.detection["selection"]).lower()

    assert values == ["FromBase64String"]
    assert "please" not in serialized_selection
    assert "include" not in serialized_selection
    assert repaired.detection_value_evidence[0]["source"] == "explicit_analyst_literal"


@pytest.mark.asyncio
async def test_fixture_repeated_semantic_repair_preserves_prior_selection_values() -> None:
    client = DeepSeekClient()
    original, _ = await client.generate_sigma({"behavior": {"summary": "Suspicious rundll32 execution"}})
    first, _ = await client.repair_sigma(
        {
            "analyst_comment": "Please include \"javascript:\" in command line detection",
            "candidate": original.sigma.model_dump(),
            "behavior": {"summary": "Suspicious rundll32 execution"},
            "validation": {"errors": []},
        }
    )
    second, _ = await client.repair_sigma(
        {
            "analyst_comment": "Please include \"mshtml\" in command line detection",
            "candidate": first.sigma.model_dump(),
            "behavior": {"summary": "Suspicious rundll32 execution"},
            "validation": {"errors": []},
        }
    )

    assert second.sigma.detection["selection"]["CommandLine|contains"] == ["javascript:", "mshtml"]


def test_pysigma_splunk_compiles_real_query() -> None:
    result = SigmaValidationService().validate(
        {
            "title": "PowerShell Encoded Command",
            "description": "Detects encoded PowerShell command execution.",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"Image|endswith": "\\powershell.exe", "CommandLine|contains": "-enc"},
                "condition": "selection",
            },
            "tags": ["attack.T1059.001"],
            "falsepositives": ["Administrative scripts"],
            "level": "high",
        },
        ["T1059.001"],
        ["Image", "CommandLine"],
    )

    assert result["valid"] is True
    assert "Image=" in result["compiled_outputs"]["query"]
    assert result["compiled_outputs"]["compiler"] == "pysigma-backend-splunk"


def test_unsupported_logsource_fails() -> None:
    result = SigmaValidationService().validate(
        {
            "title": "Unsupported",
            "description": "This should fail because the logsource is unsupported.",
            "logsource": {"product": "madeup_edr", "category": "not_real"},
            "detection": {"selection": {"Image": "x"}, "condition": "selection"},
            "tags": ["attack.T1059.001"],
            "falsepositives": ["None"],
            "level": "high",
        },
        ["T1059.001"],
        ["Image"],
    )

    assert result["valid"] is False
    assert any(error["code"] == "unsupported_logsource" for error in result["errors"])


def test_duplicate_detection_exact_match(dummy_db) -> None:
    candidate = {"title": "Same", "logsource": {"product": "windows"}, "detection": {"selection": {"Image": "x"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([candidate])).analyze(candidate, "Image=x")

    assert duplicate["status"] == "exact_duplicate"
    assert duplicate["recommended_action"] == "block_generation_or_mark_covered"


def test_duplicate_detection_near_duplicate(dummy_db) -> None:
    existing = {"title": "PowerShell Encoded", "detection": {"selection": {"Image": "powershell.exe", "CommandLine": "-enc"}, "condition": "selection"}, "compiled_outputs": {"query": "Image=powershell CommandLine=-encodedcommand"}}
    candidate = {"title": "PowerShell Encoded", "detection": {"selection": {"Image": "powershell.exe", "CommandLine": "-encodedcommand"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([existing])).analyze(candidate, "Image=powershell CommandLine=-encodedcommand")

    assert duplicate["status"] == "near_duplicate"
    assert duplicate["recommended_action"] == "allow_review_with_warning"


def test_duplicate_detection_overlapping(dummy_db) -> None:
    existing = {"title": "PowerShell Encoded", "detection": {"selection": {"Image": "powershell.exe", "CommandLine": "-enc"}, "condition": "selection"}, "compiled_outputs": {"query": "Image=powershell CommandLine=-enc ParentImage=cmd User=admin"}}
    candidate = {"title": "Suspicious PowerShell Download", "detection": {"selection": {"Image": "powershell.exe", "CommandLine": "DownloadString"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([existing])).analyze(candidate, "Image=powershell CommandLine=DownloadString ParentImage=cmd User=admin")

    assert duplicate["status"] == "overlapping"
    assert duplicate["recommended_action"] == "display_overlap_evidence"


def test_duplicate_detection_supersedes(dummy_db) -> None:
    candidate = {"title": "Replacement", "supersedes_detection_id": "det-1", "detection": {"selection": {"Image": "x"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([{"title": "Old", "detection": {"selection": {"Image": "old"}, "condition": "selection"}}])).analyze(candidate, "Image=x")

    assert duplicate["status"] == "supersedes"
    assert duplicate["matched_detection_id"] == "det-1"
    assert duplicate["recommended_action"] == "require_analyst_confirmation_before_replacement"


def test_duplicate_detection_unique(dummy_db) -> None:
    candidate = {"title": "Credential Dump", "detection": {"selection": {"CommandLine": "lsass"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([{"title": "WMI", "detection": {"selection": {"Image": "wmic.exe"}, "condition": "selection"}}])).analyze(candidate, "CommandLine=lsass")

    assert duplicate["status"] == "unique"
    assert duplicate["recommended_action"] == "allow_review"


def test_duplicate_detection_unknown_without_compiled_query(dummy_db) -> None:
    candidate = {"title": "Unknown", "detection": {"selection": {"Image": "x"}, "condition": "selection"}}
    duplicate = DuplicateDetectionService(dummy_db([])).analyze(candidate, None)

    assert duplicate["status"] == "unknown"
    assert duplicate["recommended_action"] == "allow_review_without_uniqueness_claim"


class Detection:
    def __init__(self, normalized_logic):
        self.id = "det-1"
        compiled_outputs = normalized_logic.get("compiled_outputs", {"query": "Image=x"}) if isinstance(normalized_logic, dict) else {"query": "Image=x"}
        self.normalized_logic = {"sigma": normalized_logic, "compiled_outputs": compiled_outputs}


class DummyScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class DummyDb:
    def __init__(self, rows):
        self.rows = [Detection(row) for row in rows]

    def scalars(self, _query):
        return DummyScalars(self.rows)


@pytest.fixture
def dummy_db():
    return DummyDb
