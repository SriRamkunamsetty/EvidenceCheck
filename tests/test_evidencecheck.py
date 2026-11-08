from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    EntailmentStatus,
    ResponseVerificationRequest,
    RiskTier,
    SourceDocument,
)
from app.verifier import verify_response

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "evidencecheck"}


def test_benchmark_dataset_endpoint():
    res = client.get("/api/benchmark-dataset")
    assert res.status_code == 200
    data = res.json()
    assert "cases" in data
    assert len(data["cases"]) >= 3


def test_supported_claim_verification():
    req = ResponseVerificationRequest(
        query="What is photosynthesis?",
        chatbot_response="Photosynthesis is the biological process where chlorophyll pigments convert sunlight into chemical energy.",
        sources=[
            SourceDocument(
                doc_id="bio-1",
                title="Biology Handbook",
                snippet_text="Photosynthesis is a biological process where chlorophyll pigments absorb sunlight to produce chemical energy.",
                is_trusted=True,
            )
        ],
    )
    report = verify_response(req)
    assert report.total_claims == 1
    assert report.supported_claims == 1
    assert report.grounding_ratio == 1.0
    assert report.hallucination_risk == RiskTier.LOW
    assert report.claims[0].status == EntailmentStatus.SUPPORTED


def test_contradicted_claim_polarity():
    req = ResponseVerificationRequest(
        query="Is this compound safe?",
        chatbot_response="Clinical trials confirmed the experimental compound is completely safe for human consumption.",
        sources=[
            SourceDocument(
                doc_id="med-1",
                title="Clinical Toxicology Report",
                snippet_text="Clinical trials revealed the experimental compound is highly dangerous and toxic for human consumption.",
                is_trusted=True,
            )
        ],
    )
    report = verify_response(req)
    assert report.contradicted_claims >= 1
    assert report.claims[0].status == EntailmentStatus.CONTRADICTED
    assert report.hallucination_risk in [RiskTier.HIGH, RiskTier.CRITICAL]


def test_unverified_claim():
    req = ResponseVerificationRequest(
        query="What is quantum computing?",
        chatbot_response="Quantum computers exploit superposition and entanglement to perform complex computations. Abraham Lincoln secretly funded the first prototype.",
        sources=[
            SourceDocument(
                doc_id="qc-1",
                title="Quantum Physics Primer",
                snippet_text="Quantum computers exploit quantum mechanical phenomena such as superposition and entanglement to execute operations.",
                is_trusted=True,
            )
        ],
    )
    report = verify_response(req)
    assert report.total_claims == 2
    assert report.supported_claims == 1
    assert report.unverified_claims == 1
    assert report.claims[1].status == EntailmentStatus.UNVERIFIED


def test_api_verify_and_markdown():
    payload = {
        "query": "Test Query",
        "chatbot_response": "The sun rises in the east [s-1]. The moon orbits the earth.",
        "sources": [
            {
                "doc_id": "s-1",
                "title": "Astronomy 101",
                "url": "https://astronomy.edu",
                "snippet_text": "Because of Earth's eastward spin, the sun rises in the east and sets in the west.",
                "is_trusted": True,
            }
        ],
    }

    verify_res = client.post("/api/verify", json=payload)
    assert verify_res.status_code == 200
    report = verify_res.json()
    assert report["total_claims"] == 2
    assert "grounding_ratio" in report

    md_res = client.post("/api/reports/markdown", json=payload)
    assert md_res.status_code == 200
    assert "# EvidenceCheck - Claim Grounding & Citation Audit" in md_res.text
