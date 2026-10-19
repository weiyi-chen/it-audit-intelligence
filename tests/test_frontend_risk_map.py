from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_process_risk_view_has_required_linked_layers():
    html = (ROOT / "frontend" / "it_understanding.html").read_text()

    required = [
        'id="risk-toggle"',
        'id="risk-svg"',
        "const PROCESS_STEPS",
        "const SUPPORT_NODES",
        "function drawRiskMap()",
        "function renderRiskPanel(step)",
        "Process risk points (PRPs)",
        "Knock-on systems",
        "PBC Agent",
        "Walkthrough Agent",
    ]
    for marker in required:
        assert marker in html


def test_pbc_accepts_context_from_risk_map():
    html = (ROOT / "frontend" / "pbc.html").read_text()

    assert 'contextParams.get("system")' in html
    assert 'contextParams.get("process")' in html
    assert 'accept=".xlsx"' in html
    assert "max 5 MB" in html
