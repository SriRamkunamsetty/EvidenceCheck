import re

from app.models import (
    ClaimVerification,
    EntailmentStatus,
    ResponseVerificationRequest,
    RiskTier,
    SourceDocument,
    VerificationReport,
)

CONTRADICTION_PAIRS = [
    ("increase", "decrease"),
    ("increased", "decreased"),
    ("rise", "fall"),
    ("grew", "shrank"),
    ("safe", "dangerous"),
    ("effective", "ineffective"),
    ("causes", "prevents"),
    ("proven", "unproven"),
    ("legal", "illegal"),
    ("cure", "no cure"),
]


def _extract_sentences(text: str) -> list[str]:
    # Split by period, exclamation, or newline while preserving numbers like 3.14
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n+", text)
    cleaned = []
    for s in raw_sentences:
        s = s.strip()
        # Remove markdown headers and list markers
        s = re.sub(r"^([#*\-•]|\d+\.)\s*", "", s)
        if len(s) > 15:
            cleaned.append(s)
    return cleaned


def _extract_citation_id(sentence: str, sources: list[SourceDocument]) -> str | None:
    # Check for [1], [doc-1], etc.
    match = re.search(r"\[(doc-?\d+|\d+|[a-zA-Z0-9_-]+)\]", sentence)
    if match:
        cid = match.group(1).lower()
        for doc in sources:
            if doc.doc_id.lower() == cid or f"doc-{cid}" == doc.doc_id.lower():
                return doc.doc_id
            if cid.isdigit() and doc.doc_id.endswith(cid):
                return doc.doc_id

    # Fallback: check if doc title or author matches
    for doc in sources:
        if doc.title.lower() in sentence.lower() or doc.doc_id.lower() in sentence.lower():
            return doc.doc_id

    return None


def _verify_claim(
    claim_text: str, cited_doc_id: str | None, sources: list[SourceDocument]
) -> tuple[EntailmentStatus, float, str | None, str]:
    clean_text = re.sub(r"\[.*?\]", "", claim_text).strip()
    words_claim = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", clean_text.lower()))

    # Determine target document(s)
    target_docs = (
        [d for d in sources if d.doc_id == cited_doc_id]
        if cited_doc_id
        else sources
    )

    best_status = EntailmentStatus.UNVERIFIED
    best_conf = 0.5
    best_snippet = None
    best_reason = "No matching evidence found in source documents."

    for doc in target_docs:
        snippet = doc.snippet_text
        words_source = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", snippet.lower()))

        overlap = words_claim.intersection(words_source)
        overlap_ratio = len(overlap) / len(words_claim) if words_claim else 0.0

        # Check for numeric contradiction
        claim_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", clean_text))
        source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", snippet))
        conflicting_numbers = claim_numbers - source_numbers

        # Check for semantic contradiction words
        has_semantic_contradiction = False
        contradiction_details = ""
        for w1, w2 in CONTRADICTION_PAIRS:
            if (w1 in clean_text.lower() and w2 in snippet.lower()) or (
                w2 in clean_text.lower() and w1 in snippet.lower()
            ):
                has_semantic_contradiction = True
                contradiction_details = f"Direct semantic polarity clash between '{w1}' and '{w2}'."
                break

        if has_semantic_contradiction:
            return (
                EntailmentStatus.CONTRADICTED,
                0.92,
                snippet[:250],
                f"Contradiction detected: {contradiction_details}",
            )

        # If claim asserts numbers not present in source when topic overlap is high
        if overlap_ratio >= 0.4 and claim_numbers and conflicting_numbers and not (claim_numbers & source_numbers):
            return (
                EntailmentStatus.CONTRADICTED,
                0.88,
                snippet[:250],
                f"Numeric contradiction: Claim stated {conflicting_numbers} but source reported {source_numbers}.",
            )

        # Check for support
        if overlap_ratio >= 0.45:
            conf = min(0.98, round(0.5 + (overlap_ratio * 0.5), 2))
            return (
                EntailmentStatus.SUPPORTED,
                conf,
                snippet[:250],
                f"Claim supported by source evidence with {round(overlap_ratio * 100)}% lexical alignment.",
            )
        elif overlap_ratio >= 0.25:
            best_status = EntailmentStatus.UNVERIFIED
            best_conf = 0.6
            best_snippet = snippet[:250]
            best_reason = "Partial topic overlap but source does not substantiate the specific claim."

    return (best_status, best_conf, best_snippet, best_reason)


def verify_response(req: ResponseVerificationRequest) -> VerificationReport:
    sentences = _extract_sentences(req.chatbot_response)
    if not sentences:
        sentences = [req.chatbot_response]

    verifications: list[ClaimVerification] = []
    for i, s in enumerate(sentences):
        cid = f"claim-{i + 1:02d}"
        cited_doc_id = _extract_citation_id(s, req.sources)
        status, conf, snippet, reason = _verify_claim(s, cited_doc_id, req.sources)

        verifications.append(
            ClaimVerification(
                claim_id=cid,
                claim_text=s,
                cited_doc_id=cited_doc_id,
                status=status,
                confidence=conf,
                evidence_snippet=snippet,
                reasoning=reason,
            )
        )

    total = len(verifications)
    supported = sum(1 for v in verifications if v.status == EntailmentStatus.SUPPORTED)
    contradicted = sum(1 for v in verifications if v.status == EntailmentStatus.CONTRADICTED)
    unverified = sum(1 for v in verifications if v.status == EntailmentStatus.UNVERIFIED)

    grounding_ratio = round(supported / total, 4) if total > 0 else 0.0

    cited_claims = [v for v in verifications if v.cited_doc_id is not None]
    citation_precision = (
        round(
            sum(1 for v in cited_claims if v.status == EntailmentStatus.SUPPORTED)
            / len(cited_claims),
            4,
        )
        if cited_claims
        else 1.0
    )

    if contradicted > 0:
        risk = RiskTier.CRITICAL if contradicted >= 2 else RiskTier.HIGH
    elif grounding_ratio < 0.5:
        risk = RiskTier.HIGH
    elif grounding_ratio < 0.8:
        risk = RiskTier.MEDIUM
    else:
        risk = RiskTier.LOW

    return VerificationReport(
        total_claims=total,
        supported_claims=supported,
        contradicted_claims=contradicted,
        unverified_claims=unverified,
        grounding_ratio=grounding_ratio,
        citation_precision=citation_precision,
        hallucination_risk=risk,
        claims=verifications,
    )
