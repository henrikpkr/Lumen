import os
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

class PsychotherapyState(TypedDict):
    transcript: str
    extracted_facts: str
    draft_note: str
    review_feedback: str
    final_note: str
    revision_count: int

# Use the medium model defined in environment, default to a sensible local model
model_name = os.getenv("LUMEN_MEDIUM_MODEL", "qwen3:8b")
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

llm = ChatOllama(model=model_name, base_url=ollama_base_url)

def extraction_node(state: PsychotherapyState):
    prompt = (
        "You are an expert psychotherapy session analysis agent. Your job is to extract all key "
        "psychological and clinical information from this psychotherapy session transcript. "
        "Ignore small talk, greetings, and pleasantries. "
        "Focus on: patient mood, affect, cognitive distortions, behavioral patterns, "
        "therapeutic progress, emotional state, coping mechanisms, "
        "and the treatment plan for next steps.\n\n"
        f"Transcript:\n{state['transcript']}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"extracted_facts": response.content, "revision_count": state.get("revision_count", 0)}

def formatting_node(state: PsychotherapyState):
    feedback = state.get("review_feedback", "")
    feedback_prompt = f"Here is feedback from the reviewing agent to improve the previous draft:\n{feedback}\n\n" if feedback else ""
    
    prompt = (
        "You are an expert clinical documentation agent specializing in psychotherapy. "
        "Your job is to format the following extracted information into a "
        "structured, professional SOAP (Subjective, Objective, Assessment, Plan) clinical note for psychotherapy.\n"
        "Subjective: Patient's self-reported symptoms, mood, and concerns.\n"
        "Objective: Therapist's observations of patient's appearance, behavior, and affect.\n"
        "Assessment: Clinical impressions, diagnosis considerations, and progress evaluation.\n"
        "Plan: Treatment plan, therapeutic interventions, and next session goals.\n\n"
        "Ensure the language is clinical, objective, and uses appropriate mental health terminology.\n\n"
        f"{feedback_prompt}Extracted Information:\n{state['extracted_facts']}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"draft_note": response.content}

def review_node(state: PsychotherapyState):
    prompt = (
        "You are an expert psychotherapy clinical reviewer. Your job is to review this draft SOAP note against the original transcript. "
        "Ensure no critical information (like mood indicators, suicidal ideation, trauma responses, "
        "or specific therapeutic interventions) is missing. "
        "Verify that the note accurately reflects the patient's mental state and the therapist's clinical observations. "
        "Ensure no false information was hallucinated.\n\n"
        f"Transcript:\n{state['transcript']}\n\n"
        f"Draft Note:\n{state['draft_note']}\n\n"
        "If the draft accurately and completely reflects the transcript without hallucinations, reply exactly with 'APPROVED'. "
        "If it needs changes, provide specific feedback on what to fix. Do not provide the corrected note yourself, just the feedback."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()
    
    # If the LLM approved it, or if we have looped too many times, we accept it to prevent infinite loops.
    if "APPROVED" in content.upper() or state.get("revision_count", 0) >= 2:
        return {"final_note": state["draft_note"], "review_feedback": "APPROVED"}
    else:
        return {"review_feedback": content, "revision_count": state.get("revision_count", 0) + 1}

def route_review(state: PsychotherapyState):
    if state.get("review_feedback") == "APPROVED":
        return END
    return "formatter"

def build_psychotherapy_graph():
    graph = StateGraph(PsychotherapyState)
    graph.add_node("extractor", extraction_node)
    graph.add_node("formatter", formatting_node)
    graph.add_node("reviewer", review_node)
    
    graph.set_entry_point("extractor")
    graph.add_edge("extractor", "formatter")
    graph.add_edge("formatter", "reviewer")
    graph.add_conditional_edges("reviewer", route_review)
    
    return graph.compile()

def run_psychotherapy_pipeline(transcript: str) -> str:
    """Simplified pipeline that just formats the transcript directly."""
    from langchain_ollama import ChatOllama
    import os
    
    model_name = os.getenv("LUMEN_MEDIUM_MODEL", "phi3:latest")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model=model_name, base_url=ollama_base_url)
    
    prompt = (
        "You are an expert clinical documentation agent specializing in psychotherapy. "
        "Your job is to format the following transcript into a "
        "structured, professional SOAP (Subjective, Objective, Assessment, Plan) clinical note for psychotherapy.\n"
        "Subjective: Patient's self-reported symptoms, mood, and concerns.\n"
        "Objective: Therapist's observations of patient's appearance, behavior, and affect.\n"
        "Assessment: Clinical impressions, diagnosis considerations, and progress evaluation.\n"
        "Plan: Treatment plan, therapeutic interventions, and next session goals.\n\n"
        "Ensure the language is clinical, objective, and uses appropriate mental health terminology.\n\n"
        f"Transcript:\n{transcript}"
    )
    
    from langchain_core.messages import HumanMessage
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content

if __name__ == "__main__":
    # Small test script
    test_transcript = "Hi, how are you today? I've been feeling quite anxious lately, maybe a 7 out of 10 on the anxiety scale. Okay, let's discuss some coping strategies."
    print("Testing pipeline with a small transcript...")
    result = run_psychotherapy_pipeline(test_transcript)
    print("Resulting Note:\n", result)
