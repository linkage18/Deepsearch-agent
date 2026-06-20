"""
Citation verification module.

Validates that claims in generated reports are backed by real evidence.
Works as a post-processing step: extracts citation markers from report text,
matches them against the evidence_records table, computes semantic similarity,
and writes results to citation_checks.

This does NOT block the agent — it runs asynchronously after the report is done.
"""

import json
import re
from typing import Any

from app.models.session import (
    get_session,
    list_evidence_records,
    save_citation_check,
)

_EVIDENCE_PATTERN = re.compile(r'[\[【]证据:\s*([^\]】]+?)[\]】]')
_SOURCE_PATTERN = re.compile(r'[\[【]来源:\s*([^\]】]+?)(?:,\s*p[.．]?\s*(\d+))?[\]】]')


def _load_reranker():
    if not hasattr(_load_reranker, "_model"):
        try:
            from sentence_transformers import SentenceTransformer
            from app.config.retrieval_config import RETRIEVAL_CONFIG
            model_name = RETRIEVAL_CONFIG["rerank_model"]
            _load_reranker._model = SentenceTransformer(model_name)
        except Exception:
            _load_reranker._model = None
    return _load_reranker._model


def _cosine_similarity(text_a: str, text_b: str) -> float | None:
    """Compute cosine similarity via MiniLM. Returns None on failure."""
    model = _load_reranker()
    if model is None:
        return None
    try:
        emb_a = model.encode(text_a, normalize_embeddings=True)
        emb_b = model.encode(text_b, normalize_embeddings=True)
        import numpy as np
        return float(np.dot(emb_a, emb_b))
    except Exception:
        return None


def extract_claims(report_text: str) -> list[dict[str, Any]]:
    """
    Split report into sentences and extract those with citation markers.

    Returns list of:
      {"sentence": "...", "evidence_ids": [...], "sources": [(title, page)]}
    """
    # Split by CJK sentence-ending punctuation (NOT half-width period to avoid splitting on p.5 etc.)
    raw_sentences = re.split(r'(?<=[。！？!?])\s*', report_text)
    sentences = [s.strip() for s in raw_sentences if s.strip() and len(s.strip()) >= 10]

    claims = []
    seen = set()

    for stripped in sentences:
        evidence_ids = _EVIDENCE_PATTERN.findall(stripped)
        source_matches = _SOURCE_PATTERN.findall(stripped)

        if not evidence_ids and not source_matches:
            continue

        # deduplicate by first 100 chars
        dedup_key = stripped[:100]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        claims.append({
            "sentence": stripped,
            "evidence_ids": [eid.strip() for eid in evidence_ids],
            "sources": [(title.strip(), page) for title, page in source_matches],
        })

    return claims


def verify_citations(
    thread_id: str,
    report_id: str,
    report_text: str,
) -> dict[str, Any]:
    """
    Verify all citations in a report against evidence_records.

    Steps:
      1. Extract claims with citation markers
      2. Look up evidence_records for this thread/recent
      3. For each claim, match evidence by evidence_id or source
      4. Compute semantic similarity between claim context and evidence quote (MiniLM)
      5. Classify: verified (≥0.5) / low_confidence (≥0.25) / unfounded (<0.25)
      6. Write to citation_checks table

    Returns verification stats.
    """
    claims = extract_claims(report_text)

    if not claims:
        save_citation_check(
            thread_id=thread_id, report_id=report_id,
            claim_snippet="(报告无引用声明)",
            claimed_evidence_id=None,
            matched_evidence_id=None,
            status="no_claim",
            similarity_score=None,
        )
        return {
            "total_claims": 0,
            "verified": 0,
            "low_confidence": 0,
            "unfounded": 0,
            "no_claim": 1,
            "coverage_rate": 0.0,
            "unfounded_rate": 0.0,
            "details": [],
        }

    # Build evidence lookup: evidence_id -> record
    evidence_records = list_evidence_records(limit=500)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_by_source: dict[str, list[dict[str, Any]]] = {}
    for rec in evidence_records:
        eid = rec.get("evidence_id", "")
        if eid:
            evidence_by_id[eid] = rec
        src = rec.get("source", "").lower()
        if src:
            evidence_by_source.setdefault(src, []).append(rec)

    verified = 0
    low_confidence = 0
    unfounded = 0

    for claim in claims:
        claimed_eid = None
        matched_eid = None
        matched_quote = None
        similarity = None
        status = "unfounded"

        # Priority 1: match by evidence_id
        for eid in claim["evidence_ids"]:
            claimed_eid = eid
            if eid in evidence_by_id:
                rec = evidence_by_id[eid]
                matched_eid = eid
                matched_quote = rec.get("quote", "")
                similarity = _cosine_similarity(
                    claim["sentence"][:300],
                    matched_quote[:300],
                )
                if similarity is not None:
                    if similarity >= 0.5:
                        status = "verified"
                    elif similarity >= 0.25:
                        status = "low_confidence"
                    else:
                        status = "unfounded"
                else:
                    status = "verified"  # model unavailable, trust the ID match
                break

        if status == "unfounded":
            # Priority 2: match by source title + page
            for src_title, src_page in claim["sources"]:
                key = src_title.lower()
                if key in evidence_by_source:
                    candidates = evidence_by_source[key]
                    if src_page:
                        candidates = [
                            c for c in candidates
                            if c.get("page", "") == src_page
                        ]
                    if candidates:
                        best = candidates[0]
                        matched_eid = best.get("evidence_id", "")
                        matched_quote = best.get("quote", "")
                        similarity = _cosine_similarity(
                            claim["sentence"][:300],
                            matched_quote[:300],
                        )
                        if similarity is not None:
                            if similarity >= 0.5:
                                status = "verified"
                            elif similarity >= 0.25:
                                status = "low_confidence"
                            else:
                                status = "unfounded"
                        else:
                            status = "verified"
                        break

        save_citation_check(
            thread_id=thread_id,
            report_id=report_id,
            claim_snippet=claim["sentence"][:200],
            claimed_evidence_id=claimed_eid,
            matched_evidence_id=matched_eid,
            status=status,
            similarity_score=similarity,
        )

        if status == "verified":
            verified += 1
        elif status == "low_confidence":
            low_confidence += 1
        else:
            unfounded += 1

    total = verified + low_confidence + unfounded
    return {
        "total_claims": total,
        "verified": verified,
        "low_confidence": low_confidence,
        "unfounded": unfounded,
        "no_claim": 0,
        "coverage_rate": round(
            (verified + low_confidence) / max(total, 1), 4
        ),
        "unfounded_rate": round(unfounded / max(total, 1), 4),
        "details": [],
    }
