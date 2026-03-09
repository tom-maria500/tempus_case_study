"""Meeting outcome logging: CRM update, priority recalc, ChromaDB re-index."""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from models import OutcomeLog, OutcomeRequest, OutcomeResponse
from rag import (
    _call_llm_for_brief,
    _find_physician_row,
    _get_chroma_persist_dir,
    _init_vector_index,
    _load_market_dataframe,
)
from ingest import _parse_crm_block

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHROMA_COLLECTION_NAME = "tempus_physicians"

OUTCOME_ADJUSTMENTS = {
    "committed_to_pilot": 1.5,
    "positive_followup": 0.5,
    "neutral_evaluating": 0.0,
    "negative_not_interested": -2.0,
    "no_show": -0.3,
}

KNOWN_CONCERNS = frozenset([
    "turnaround_time", "cost_reimbursement", "competitor_loyalty",
    "emr_integration", "staff_bandwidth", "ai_skepticism", "no_concern"
])


def _load_env() -> None:
    load_dotenv(override=False)


def _objection_type(concern: str) -> str:
    """Classify concern as known or unknown for scoring."""
    normalized = concern.lower().replace(" ", "_").replace("/", "_")
    return "known_objection" if normalized in KNOWN_CONCERNS else "unknown_objection"


def _get_objection_adjustment(concern: str) -> float:
    if _objection_type(concern) == "known_objection":
        return 0.2
    return -0.2


def recalculate_priority(current_score: float, outcome: str, main_concern: str) -> float:
    delta = OUTCOME_ADJUSTMENTS.get(outcome, 0.0)
    delta += _get_objection_adjustment(main_concern)
    new_score = current_score + delta
    return round(max(0.0, min(10.0, new_score)), 1)


def _append_meeting_log_to_crm(physician_id: str, req: OutcomeRequest) -> None:
    """Append MEETING_LOG block to physician's record in crm_notes.txt."""
    path = DATA_DIR / "crm_notes.txt"
    raw = path.read_text(encoding="utf-8")
    blocks = raw.split("---")
    meeting_date = req.meeting_date or date.today().isoformat()

    new_entry = (
        f"\nMEETING_LOG: {meeting_date}\n"
        f"OUTCOME: {req.outcome}\n"
        f"MAIN_CONCERN: {req.main_concern}"
        + (f" ({req.concern_detail})" if req.concern_detail else "")
        + f"\nNEXT_STEPS: {req.next_step}\n"
    )

    updated = False
    for i, block in enumerate(blocks):
        parsed = _parse_crm_block(block)
        bid = parsed.get("physician_id", "")
        if str(bid) == str(physician_id):
            blocks[i] = block.rstrip() + new_entry
            updated = True
            break

    if not updated:
        raise ValueError(f"Physician {physician_id} not found in CRM notes")

    path.write_text("---".join(blocks), encoding="utf-8")


def _update_market_csv(physician_id: str, new_score: float) -> None:
    """Update priority_score for physician in market_data.csv."""
    path = DATA_DIR / "market_data.csv"
    df = pd.read_csv(path)
    mask = df["physician_id"].astype(str) == str(physician_id)
    if not mask.any():
        raise ValueError(f"Physician {physician_id} not found in market_data")
    df.loc[mask, "priority_score"] = new_score
    df.to_csv(path, index=False)


def _reindex_physician_in_chromadb(physician_id: str) -> None:
    """Replace CRM doc for this physician with updated content."""
    index, _ = _init_vector_index()
    crm_id = f"crm-{physician_id}"
    crm_path = DATA_DIR / "crm_notes.txt"
    raw = crm_path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in raw.split("---") if b.strip()]
    for block in blocks:
        parsed = _parse_crm_block(block)
        bid = parsed.get("physician_id")
        if str(bid) != str(physician_id):
            continue
        name = parsed.get("name", "Unknown")
        text = (
            f"CRM notes for {name} ({physician_id}). "
            f"Date: {parsed.get('date','N/A')}. "
            f"Rep notes: {parsed.get('rep_notes','')} "
            f"Objections: {parsed.get('objections','')} "
            f"Interests: {parsed.get('interests','')} "
            f"Next steps: {parsed.get('next_steps','')}"
        )
        if "MEETING_LOG:" in block:
            ml_match = re.search(
                r"MEETING_LOG:\s*([^\n]+)\nOUTCOME:\s*([^\n]+)\nMAIN_CONCERN:\s*([^\n]+)\nNEXT_STEPS:\s*([^\n]+)",
                block,
                re.DOTALL,
            )
            if ml_match:
                text += (
                    f" Latest meeting: {ml_match.group(2)}, "
                    f"concern: {ml_match.group(3)}, next: {ml_match.group(4)}"
                )
        metadata = {
            "source": "crm_notes",
            "physician_id": physician_id,
            "name": name,
            "objections": parsed.get("objections", ""),
            "interests": parsed.get("interests", ""),
        }
        from llama_index.core import Document

        doc = Document(text=text, metadata=metadata, doc_id=crm_id)
        try:
            index.update_ref_doc(doc, delete_kwargs={})
        except Exception:
            index.insert(doc)
        break


def _generate_suggested_next_action(
    physician_name: str,
    outcome: str,
    main_concern: str,
    next_step: str,
    cancer_focus: str,
    new_score: float,
) -> str:
    prompt = f"""You are a Tempus sales coach. Given this meeting outcome for {physician_name}:
- Result: {outcome}
- Main concern: {main_concern}
- Rep's next step: {next_step}
- Their cancer focus: {cancer_focus}
- Current priority score: {new_score}

Suggest one specific, actionable next step the rep should take in the next 48 hours.
One sentence. Be specific — reference actual Tempus assets (e.g. "Send the xT NSCLC de-identified report with TMB/PD-L1 highlighted") not generic advice.

Respond with JSON only: {{"response": "your one-sentence suggestion"}}"""

    try:
        raw = _call_llm_for_brief(prompt)
        return str(raw.get("response", next_step)).strip()[:500]
    except Exception:
        return next_step


def log_outcome(request: OutcomeRequest) -> OutcomeResponse:
    """Log meeting outcome, update CRM, recalc priority, re-index, suggest action."""
    df = _load_market_dataframe()
    row = _find_physician_row(df, None, request.physician_id)
    if row is None:
        raise ValueError(f"Physician {request.physician_id} not found")

    current_score = float(row["priority_score"])
    new_score = recalculate_priority(
        current_score, request.outcome, request.main_concern
    )
    score_delta = round(new_score - current_score, 1)

    _append_meeting_log_to_crm(request.physician_id, request)
    _update_market_csv(request.physician_id, new_score)
    _reindex_physician_in_chromadb(request.physician_id)

    cancer = str(row.get("primary_cancer_focus", ""))
    suggested = _generate_suggested_next_action(
        physician_name=str(row["name"]),
        outcome=request.outcome,
        main_concern=request.main_concern,
        next_step=request.next_step,
        cancer_focus=cancer,
        new_score=new_score,
    )

    return OutcomeResponse(
        physician_id=request.physician_id,
        new_priority_score=new_score,
        score_delta=score_delta,
        suggested_next_action=suggested,
        updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def get_outcome_history(physician_id: str) -> list[OutcomeLog]:
    """Return all meeting logs for a physician from crm_notes."""
    path = DATA_DIR / "crm_notes.txt"
    raw = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in raw.split("---") if b.strip()]
    logs: list[OutcomeLog] = []

    df = _load_market_dataframe()
    row = _find_physician_row(df, None, physician_id)
    current_score = float(row["priority_score"]) if row is not None else 0.0

    for block in blocks:
        parsed = _parse_crm_block(block)
        if str(parsed.get("physician_id")) != str(physician_id):
            continue
        m = re.findall(
            r"MEETING_LOG:\s*([^\n]+)\nOUTCOME:\s*([^\n]+)\nMAIN_CONCERN:\s*([^\n]+)\nNEXT_STEPS:\s*([^\n]+)",
            block
        )
        for md, out, con, nxt in m:
            logs.append(
                OutcomeLog(
                    meeting_date=md.strip(),
                    outcome=out.strip(),
                    main_concern=con.strip(),
                    next_step=nxt.strip(),
                    priority_score=current_score,
                    score_delta=0.0,
                )
            )
    return logs
