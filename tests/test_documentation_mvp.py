from __future__ import annotations

from backend.lumen_web.db import Base, SessionLocal, engine
from backend.lumen_web.documentation import (
    add_documentation_session_text,
    create_documentation_session,
    documentation_session_detail,
    generate_documentation_note,
    list_documentation_patient_sessions,
    list_documentation_patients,
    save_reviewed_documentation_note,
    update_documentation_session_text,
)
from backend.lumen_web.models import Tenant


SAMPLE_TEXT = (
    "Client reported ongoing sleep difficulties over the past week, especially trouble falling asleep and "
    "waking up earlier than intended. Client described feeling mentally activated in the evenings, often "
    "thinking about unfinished work tasks and recent tension with their partner. Therapist introduced and "
    "practiced a grounding exercise. Risk and safety concerns were not directly assessed during this session."
)


def test_documentation_fake_generator_preserves_extracted_text_provenance(monkeypatch) -> None:
    monkeypatch.setenv("NOTE_GENERATOR", "fake")
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        tenant = Tenant(id="test-documentation", name="Documentation Test", slug="test-documentation")
        session.add(tenant)
        session.flush()

        doc_session = create_documentation_session(
            session,
            tenant_id=tenant.id,
            title="Test Session",
            patient_label="Test Patient",
        )
        assert doc_session["patient_id"] is None
        assert doc_session["patient_label"] == "Test Patient"
        source_text = add_documentation_session_text(
            session,
            documentation_session_id=doc_session["id"],
            extracted_text=SAMPLE_TEXT,
        )
        updated_text = update_documentation_session_text(
            session,
            documentation_session_id=doc_session["id"],
            text_id=source_text["id"],
            extracted_text=f"{SAMPLE_TEXT}\nPlan: Client will practice grounding before bed.",
        )
        detail = documentation_session_detail(session, doc_session["id"])
        note = generate_documentation_note(session, documentation_session_id=doc_session["id"])
        patients = list_documentation_patients(session, tenant_id=tenant.id)
        patient_sessions = list_documentation_patient_sessions(
            session,
            patient_label="Test Patient",
            tenant_id=tenant.id,
        )

        draft = note["draft_json"]
        assert updated_text["raw_source_stored"] is False
        assert len(detail["texts"]) == 1
        assert "practice grounding" in detail["texts"][0]["extracted_text"]
        assert patients[0]["patient_label"] == "Test Patient"
        assert patients[0]["session_count"] == 1
        assert patient_sessions[0]["id"] == doc_session["id"]
        assert patient_sessions[0]["transcript_status"] == "transcript stored"
        assert patient_sessions[0]["note_status"] == "draft"
        assert draft["source_basis"] == {
            "raw_source_stored": False,
            "input_used": "extracted_session_text",
        }
        assert draft["risk_or_safety"]["status"] == "not_assessed"
        assert "anxiety" not in str(draft).lower()
        assert "no risk" not in str(draft).lower()

        reviewed = save_reviewed_documentation_note(
            session,
            note_id=note["id"],
            reviewed_json=draft,
            reviewer_id=None,
        )
        assert reviewed["status"] == "reviewed"
        assert reviewed["reviewed_json"]["version"] == "session_note_v0.1"
    finally:
        session.rollback()
        session.close()


def test_documentation_fake_generator_preserves_not_wanting_to_be_alive_language(monkeypatch) -> None:
    monkeypatch.setenv("NOTE_GENERATOR", "fake")
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        tenant = Tenant(id="test-documentation-risk", name="Documentation Risk Test", slug="test-documentation-risk")
        session.add(tenant)
        session.flush()
        doc_session = create_documentation_session(
            session,
            tenant_id=tenant.id,
            title="Risk Session",
            patient_label="Test Patient",
            therapist_label="Test Therapist",
        )
        add_documentation_session_text(
            session,
            documentation_session_id=doc_session["id"],
            extracted_text=(
                "Patient said they had moments of not wanting to be alive this week. "
                "Therapist completed a safety check and discussed supports."
            ),
        )

        note = generate_documentation_note(session, documentation_session_id=doc_session["id"])

        risk = note["draft_json"]["risk_or_safety"]
        assert risk["status"] == "mentioned"
        assert "not wanting to be alive" in risk["details"]
    finally:
        session.rollback()
        session.close()
