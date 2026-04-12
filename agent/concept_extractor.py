import json

from agent.prompts import CONCEPT_EXTRACTOR_PROMPT

def extract_concepts_from_response(
    request_json,
    question: str,
    response_text: str,
    experience_level: str,
    interview_domain: str,
    concept_map: list[dict],
) -> dict:
    prompt = CONCEPT_EXTRACTOR_PROMPT.format(
        question=question,
        response=response_text,
        experience_level=experience_level,
        interview_domain=interview_domain,
        concept_map=json.dumps(concept_map, indent=2),
    )

    result = request_json(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=700,
    )
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    if isinstance(result, list):
        return {"concepts_assessed": result}
    else:
        return {
            "concepts_assessed": [],
            "overall_response_quality": "partial",
            "notable_insight": None,
        }
