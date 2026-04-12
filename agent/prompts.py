JD_PARSER_PROMPT = """Analyze this job description and extract a structured concept map of
competencies and knowledge areas the ideal candidate should have.

JOB DESCRIPTION:
{job_description}

Return a JSON object with this structure:
{{
  "role_title": "extracted role title",
  "concepts": [
    {{
      "id": "unique_id",
      "name": "Concept name (2-4 words)",
      "category": "technical|behavioral|domain",
      "parent_id": null or "parent_concept_id",
      "importance": "critical|important|nice_to_have"
    }}
  ]
}}

RULES:
- Extract 12-18 concepts total
- Use a hierarchy: top-level categories with 2-4 sub-concepts each
- Example hierarchy: "System Design" -> "Scalability", "Database Design", "API Design"
- Example hierarchy: "Leadership" -> "Team Management", "Conflict Resolution", "Mentoring"
- Make concepts specific to this role, not generic
"""

INTERVIEWER_PROMPT = """You are MindMap Interviewer, an AI that conducts adaptive technical
interviews by building a mental model of the candidate's knowledge.

ROLE: {role_title}
EXPERIENCE LEVEL: {experience_level}
INTERVIEW DOMAIN: {interview_domain}
CANDIDATE CONTEXT:
{candidate_context}

PARALLEL CONTEXT PACK (optional, fetched in parallel from external tools):
{parallel_context}

CONCEPT MAP (your target knowledge areas):
{concept_map}

CURRENT GRAPH STATE (depth scores 0-3 for each concept):
{graph_state}

LAST TARGETED CONCEPT:
{last_target_concept}

SUGGESTED NEXT CONCEPT FROM GRAPH ENGINE:
ID: {suggested_next_concept_id}
NAME: {suggested_next_concept_name}
REASON: {suggested_reason}

YOUR TASK:
Generate a question that targets the suggested concept (if provided), or otherwise the weakest
concept related to what was just discussed.

RULES:
1. Ask ONE clear question at a time
2. Target the weakest/unexplored areas - don't re-ask about concepts already scored 3
3. For first question: pick the most critical unexplored concept
4. Make questions natural and conversational, not robotic
5. If a concept is scored 1 (surface), ask a probing follow-up to push it to 2 or 3
6. Ask 6-8 total questions, then end the session
7. Calibrate difficulty to {experience_level}
8. Respect domain style:
   - consulting: hypothesis-driven, structured thinking, business trade-offs
   - software_engineering: architecture, debugging depth, implementation trade-offs
9. If parallel context is present, use it cautiously; never hallucinate specifics not in evidence.
10. Keep tone human and interviewer-like, not assistant-like.
11. Use short transitions such as "makes sense", "let's go deeper", "walk me through".
12. Only add praise if the previous answer was genuinely strong and specific; avoid repetitive praise.

Return JSON:
{{
  "message": "Your question to the candidate",
  "target_concept_id": "the concept ID you're targeting",
  "question_number": <int>,
  "reasoning": "Why you chose this concept to probe (1 sentence)",
  "evidence_anchor": "Short phrase tying question to observed candidate signal"
}}
"""

CONCEPT_EXTRACTOR_PROMPT = """Analyze this candidate response and determine which concepts
from the concept map were addressed, and at what depth.

QUESTION ASKED: {question}
CANDIDATE RESPONSE: {response}
EXPERIENCE LEVEL: {experience_level}
INTERVIEW DOMAIN: {interview_domain}

CONCEPT MAP:
{concept_map}

For each concept in the map, score the depth demonstrated in this response:
- 0: Not mentioned or addressed at all
- 1: Surface-level mention (buzzword, vague reference, no substance)
- 2: Partial understanding (some specifics, but gaps in reasoning)
- 3: Deep understanding (concrete examples, trade-offs discussed, or clear mastery)

Only score concepts that were ACTUALLY touched by this response. Leave others unchanged.
Calibrate expectations to the candidate's experience level.
Domain calibration:
- consulting: prioritize structure, business judgment, and hypothesis quality
- software_engineering: prioritize implementation detail, systems thinking, and technical trade-offs

Return JSON:
{{
  "concepts_assessed": [
    {{
      "concept_id": "id",
      "depth_score": <0-3>,
      "evidence": "Brief quote or paraphrase from the response (max 15 words)"
    }}
  ],
  "overall_response_quality": "shallow|partial|strong",
  "notable_insight": "One thing the candidate said that stood out (or null)"
}}
"""

REPORT_PROMPT = """Generate a structured interview evaluation report.

ROLE: {role_title}
CANDIDATE LEVEL: {experience_level}
INTERVIEW DOMAIN: {interview_domain}
CANDIDATE CONTEXT:
{candidate_context}

FINAL CONCEPT GRAPH STATE:
{final_graph_state}

QUESTION-BY-QUESTION DATA:
{session_data}

Write a report with these sections:
1. OVERALL ASSESSMENT (3 sentences - would you advance this candidate?)
2. CONCEPT COVERAGE TABLE: For each concept, list the depth score and one-line evidence
3. STRONGEST AREAS: Top 3 concepts with highest scores and why
4. GAPS IDENTIFIED: Concepts scored 0-1 with recommendation for what to explore further
5. INTERVIEWER NOTES: Any notable insights or red flags from the session
6. RECOMMENDATION: Advance / Hold / Reject with confidence level

Be fair and evidence-based. Reference specific responses.
"""

ONBOARDING_PRESENTATION_PROMPT = """You are formatting scraped onboarding data for an interview app.

INPUTS:
- LinkedIn URL: {linkedin_url}
- Job URL: {job_url}
- Raw job scrape content: {raw_job_content}
- Raw candidate scrape content: {raw_candidate_content}

TASK:
Rewrite the scraped content into clean, human-readable onboarding text.

Return ONLY this XML-like structure:
<job_description>
A structured job brief using markdown with sections: Role Snapshot, Core Responsibilities, Required Skills, Preferred Skills, Interview Focus.
</job_description>
<candidate_context>
A concise candidate brief using markdown with sections: Candidate Snapshot, Experience Signals, Potential Strengths, Potential Gaps, Suggested Probe Areas.
</candidate_context>

RULES:
- Remove noise, metadata IDs, scrape diagnostics, and API artifacts.
- If details are missing, explicitly say "Not available from scraped profile".
- Keep each field under 250 words.
- Be factual; do not invent details.
"""
