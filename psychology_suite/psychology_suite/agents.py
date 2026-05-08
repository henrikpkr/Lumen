"""Agentic summarization helpers for psychotherapy sessions."""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from .config import load_settings


def _llm() -> ChatOllama:
    settings = load_settings()
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url)


def _extract(transcript: str) -> str:
    prompt = (
        "You are an expert psychotherapy session analysis agent. Extract only the factual, "
        "clinically relevant details that are explicitly present in the transcript. "
        "Do not infer, hypothesize, or add new information. "
        "Focus on: mood, affect, symptoms, coping, risks, functional impact, "
        "therapeutic interventions, and agreed next steps. "
        "If something is not stated, do not guess.\n\n"
        f"Transcript:\n{transcript}"
    )
    response = _llm().invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def _format_soap(extracted: str, feedback: str | None = None) -> str:
    feedback_block = (
        f"Reviewer feedback to address:\n{feedback}\n\n" if feedback else ""
    )
    prompt = (
        "You are an expert clinical documentation agent. "
        "Create a SOAP (Subjective, Objective, Assessment, Plan) psychotherapy note "
        "using ONLY the extracted facts. "
        "No new facts, no diagnoses unless explicitly stated. "
        "If required details are missing, state 'Not stated'. "
        "Keep language clinical and concise.\n\n"
        f"{feedback_block}Extracted facts:\n{extracted}"
    )
    response = _llm().invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def _review(transcript: str, draft: str) -> str:
    prompt = (
        "You are a clinical reviewer. Verify the SOAP note against the transcript. "
        "Flag any hallucinations or missing critical facts. "
        "If the note is accurate and complete, reply exactly with 'APPROVED'. "
        "Otherwise list precise corrections without rewriting the note.\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Draft SOAP note:\n{draft}"
    )
    response = _llm().invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def generate_soap_note(transcript: str) -> str:
    extracted = _extract(transcript)
    draft = _format_soap(extracted)
    feedback = _review(transcript, draft)
    if "APPROVED" in feedback.upper():
        return draft
    draft = _format_soap(extracted, feedback=feedback)
    feedback = _review(transcript, draft)
    return draft
