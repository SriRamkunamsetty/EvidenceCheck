from enum import Enum

from pydantic import BaseModel, Field


class EntailmentStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceDocument(BaseModel):
    doc_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(default="")
    domain: str = Field(default="")
    snippet_text: str = Field(min_length=1)
    is_trusted: bool = True


class ClaimVerification(BaseModel):
    claim_id: str
    claim_text: str
    cited_doc_id: str | None = None
    status: EntailmentStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str | None = None
    reasoning: str


class ResponseVerificationRequest(BaseModel):
    query: str = Field(default="")
    chatbot_response: str = Field(min_length=1, max_length=10000)
    sources: list[SourceDocument] = Field(min_length=1)


class VerificationReport(BaseModel):
    total_claims: int
    supported_claims: int
    contradicted_claims: int
    unverified_claims: int
    grounding_ratio: float
    citation_precision: float
    hallucination_risk: RiskTier
    claims: list[ClaimVerification]
