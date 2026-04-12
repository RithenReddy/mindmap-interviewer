from __future__ import annotations

import json
import os
import re
import time

from groq import Groq
import requests

from agent.concept_extractor import extract_concepts_from_response
from agent.gap_finder import suggest_next_gap
from agent.prompts import INTERVIEWER_PROMPT, JD_PARSER_PROMPT
from graph.builder import ConceptGraph

GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODELS = [
    "claude-3-7-sonnet-latest",
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]


class InterviewAgent:
    def __init__(
        self,
        job_description: str,
        experience_level: str,
        api_key: str,
        provider: str = "groq",
        candidate_context: str = "",
        interview_domain: str = "software_engineering",
    ):
        self.provider = provider
        self.groq_client = None
        self.anthropic_client = None
        self.gumloop_api_key = ""
        self.gumloop_user_id = ""
        self.gumloop_agent_id = ""
        if self.provider == "groq":
            self.groq_client = Groq(api_key=api_key)
        elif self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ModuleNotFoundError as exc:
                raise ValueError(
                    "Anthropic provider requires the anthropic package. Install with: pip install anthropic"
                ) from exc
            self.anthropic_client = Anthropic(api_key=api_key)
        elif self.provider == "gumloop":
            self.gumloop_api_key = (api_key or "").strip() or os.getenv("GUMLOOP_API_KEY", "").strip()
            self.gumloop_user_id = os.getenv("GUMLOOP_USER_ID", "").strip()
            self.gumloop_agent_id = os.getenv("GUMLOOP_INTERVIEW_AGENT_ID", "").strip() or os.getenv(
                "GUMLOOP_REPORT_AGENT_ID", ""
            ).strip()
            if not self.gumloop_api_key or not self.gumloop_user_id or not self.gumloop_agent_id:
                raise ValueError(
                    "Gumloop provider requires GUMLOOP_API_KEY, GUMLOOP_USER_ID, and GUMLOOP_INTERVIEW_AGENT_ID."
                )
        else:
            raise ValueError("Unsupported provider. Choose 'groq', 'anthropic', or 'gumloop'.")

        self.jd = job_description
        self.experience_level = experience_level
        self.candidate_context = candidate_context.strip()
        self.interview_domain = interview_domain
        self.graph = ConceptGraph()
        self.conversation_history: list[dict] = []
        self.session_data: list[dict] = []
        self.last_target_concept: str | None = None
        self.session_complete = False
        self.role_title = "the role"
        self._opening_stage = 0
        self._pending_acknowledgement = ""
        self._last_ack_turn = -1

    def _candidate_name(self) -> str:
        text = self.candidate_context or ""
        for line in text.splitlines():
            if line.lower().startswith("name:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    return value.split()[0]
        match = re.search(r"\b([A-Z][a-z]+)\s+[A-Z][a-zA-Z\-]+\b", text)
        if match:
            return match.group(1)
        return "there"

    def _profile_signal(self) -> str:
        text = self.candidate_context or ""
        for prefix in ["Title:", "Headline:"]:
            for line in text.splitlines():
                if line.startswith(prefix):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        return value
        for line in text.splitlines():
            if line.strip().startswith("- ") and "@" in line:
                return line.strip()[2:]
        return "your background"

    def _opening_prompt_message(self) -> str:
        first_name = self._candidate_name()
        return (
            f"Hey {first_name}, great to meet you. You're in a strong place for this conversation.\n\n"
            "Before we dive in, how has your prep been, and is there anything specific you want me to "
            "highlight or evaluate as we go?"
        )

    def _profile_bridge_message(self) -> str:
        signal = self._profile_signal()
        return (
            f"I noticed {signal} on your profile. Let's use that as a starting point.\n\n"
            "Can you walk me through one concrete decision you made there, what trade-offs you evaluated, "
            "and what outcome you measured?"
        )

    @staticmethod
    def _safe_parse_json(content: str | None) -> dict:
        if not content:
            return {}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _extract_json_from_text(content: str | None) -> dict:
        if not content:
            return {}
        parsed = InterviewAgent._safe_parse_json(content)
        if parsed:
            return parsed

        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            snippet = content[start : end + 1]
            return InterviewAgent._safe_parse_json(snippet)
        return {}

    @staticmethod
    def _normalize_concepts(raw_concepts: object) -> list[dict]:
        if not isinstance(raw_concepts, list):
            return []
        normalized: list[dict] = []
        for item in raw_concepts:
            if not isinstance(item, dict):
                continue
            concept_id = item.get("id")
            name = item.get("name")
            category = item.get("category")
            importance = item.get("importance")
            if not all(
                isinstance(value, str) and value.strip()
                for value in [concept_id, name, category, importance]
            ):
                continue
            normalized.append(
                {
                    "id": concept_id.strip(),
                    "name": name.strip(),
                    "category": category.strip(),
                    "importance": importance.strip(),
                    "parent_id": item.get("parent_id"),
                }
            )
        return normalized

    def _chat_json(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        system_prompt: str | None = None,
    ) -> dict:
        if self.provider == "groq":
            payload = []
            if system_prompt:
                payload.append({"role": "system", "content": system_prompt})
            payload.extend(messages)
            response = self.groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=payload,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return self._safe_parse_json(response.choices[0].message.content)
        if self.provider == "gumloop":
            text = self._gumloop_chat(
                system_prompt=system_prompt or "",
                messages=messages,
                require_json=True,
            )
            return self._extract_json_from_text(text)

        system = system_prompt or ""
        system += "\nReturn ONLY a valid JSON object, with no extra prose."
        response = self._anthropic_messages_create(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text_blocks = [
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ]
        combined = "\n".join(text_blocks)
        return self._extract_json_from_text(combined)

    def _chat_text(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        system_prompt: str | None = None,
    ) -> str:
        if self.provider == "groq":
            payload = []
            if system_prompt:
                payload.append({"role": "system", "content": system_prompt})
            payload.extend(messages)
            response = self.groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=payload,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        if self.provider == "gumloop":
            return self._gumloop_chat(
                system_prompt=system_prompt or "",
                messages=messages,
                require_json=False,
            )

        response = self._anthropic_messages_create(
            system=system_prompt or "",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text_blocks = [
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ]
        return "\n".join(text_blocks).strip()

    def _anthropic_messages_create(
        self, system: str, messages: list[dict], temperature: float, max_tokens: int
    ):
        last_error = None
        for model in ANTHROPIC_MODELS:
            try:
                return self.anthropic_client.messages.create(
                    model=model,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                last_error = exc
                err_text = str(exc).lower()
                if "not_found_error" in err_text or "model" in err_text:
                    continue
                raise
        raise ValueError(
            f"Anthropic request failed after trying models: {', '.join(ANTHROPIC_MODELS)}. Last error: {last_error}"
        )

    def _gumloop_chat(self, system_prompt: str, messages: list[dict], require_json: bool) -> str:
        serialized = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            serialized.append(f"{role.upper()}: {content}")
        instruction = (
            "Return ONLY a valid JSON object with no markdown fences."
            if require_json
            else "Return plain text only."
        )
        composed_message = (
            "You are executing an interview-runtime subtask.\n\n"
            f"SYSTEM PROMPT:\n{system_prompt}\n\n"
            f"TASK INSTRUCTION:\n{instruction}\n\n"
            "CONVERSATION:\n"
            + "\n".join(serialized)
        )

        headers = {
            "Authorization": f"Bearer {self.gumloop_api_key}",
            "Content-Type": "application/json",
        }
        try:
            start = requests.post(
                "https://api.gumloop.com/api/v1/start_agent",
                headers=headers,
                json={
                    "gummie_id": self.gumloop_agent_id,
                    "message": composed_message,
                    "user_id": self.gumloop_user_id,
                },
                timeout=45,
            )
            start.raise_for_status()
            interaction_id = str(start.json().get("interaction_id", "")).strip()
            if not interaction_id:
                raise ValueError("Gumloop returned no interaction_id.")
        except Exception as exc:
            raise ValueError(f"Gumloop start_agent failed: {exc}") from exc

        started_at = time.time()
        while time.time() - started_at < 150:
            time.sleep(2)
            try:
                status = requests.get(
                    f"https://api.gumloop.com/api/v1/agent_status/{interaction_id}",
                    headers={"Authorization": f"Bearer {self.gumloop_api_key}"},
                    params={"user_id": self.gumloop_user_id},
                    timeout=45,
                )
                status.raise_for_status()
                payload = status.json()
            except Exception as exc:
                raise ValueError(f"Gumloop agent_status failed: {exc}") from exc

            state = str(payload.get("state", "")).upper()
            if state == "COMPLETED":
                response = payload.get("response")
                if isinstance(response, str) and response.strip():
                    return response.strip()
                return json.dumps(payload)
            if state == "FAILED":
                raise ValueError(str(payload.get("error_message", "Gumloop interaction failed.")))
        raise ValueError("Gumloop interaction timed out.")

    def initialize(self) -> dict:
        parsed = self._chat_json(
            messages=[
                {
                    "role": "user",
                    "content": JD_PARSER_PROMPT.format(job_description=self.jd),
                }
            ],
            temperature=0.3,
            max_tokens=1600,
        )

        concepts = self._normalize_concepts(parsed.get("concepts"))
        if len(concepts) == 0:
            raise ValueError("JD parsing returned no concepts.")

        role_title = parsed.get("role_title")
        self.role_title = role_title.strip() if isinstance(role_title, str) else "the role"
        self.graph.build_from_jd_parse(concepts)
        return parsed

    def generate_question(self, extra_context: str = "") -> dict:
        if self._opening_stage == 0:
            self._opening_stage = 1
            message = self._opening_prompt_message()
            self.conversation_history.append({"role": "assistant", "content": message})
            return {
                "message": message,
                "target_concept_id": self.last_target_concept,
                "question_number": 1,
                "reasoning": "Open with confidence and candidate-aligned context setting.",
                "evidence_anchor": "Personalized interview warm-up",
            }

        if self._opening_stage == 1 and len(self.session_data) >= 1:
            self._opening_stage = 2
            message = self._profile_bridge_message()
            self.conversation_history.append({"role": "assistant", "content": message})
            return {
                "message": message,
                "target_concept_id": self.last_target_concept,
                "question_number": max(2, len(self.session_data) + 1),
                "reasoning": "Bridge from warm-up into profile-grounded behavioral depth.",
                "evidence_anchor": self._profile_signal(),
            }

        concept_map = [
            {
                "id": c.id,
                "name": c.name,
                "category": c.category,
                "importance": c.importance,
                "parent_id": c.parent_id,
            }
            for c in self.graph.concepts.values()
        ]
        graph_state = self.graph.get_state_summary()

        suggestion = suggest_next_gap(self.graph, self.last_target_concept)
        suggested_id = suggestion.get("suggested_concept_id")
        suggested_name = suggestion.get("suggested_concept_name")
        suggested_reason = suggestion.get("reason")

        prompt = INTERVIEWER_PROMPT.format(
            role_title=self.role_title,
            experience_level=self.experience_level,
            interview_domain=self.interview_domain,
            candidate_context=self.candidate_context or "Not provided.",
            parallel_context=(extra_context or "None."),
            concept_map=json.dumps(concept_map, indent=2),
            graph_state=graph_state,
            last_target_concept=self.last_target_concept or "None yet",
            suggested_next_concept_id=suggested_id or "none",
            suggested_next_concept_name=suggested_name or "none",
            suggested_reason=suggested_reason or "No suggestion available.",
        )

        messages = list(self.conversation_history[-6:])
        messages.append(
            {"role": "user", "content": "Generate the next interview question."}
        )

        result = self._chat_json(
            messages=messages,
            temperature=0.7,
            max_tokens=450,
            system_prompt=prompt,
        )

        target_id = result.get("target_concept_id")
        if target_id not in self.graph.concepts:
            target_id = suggested_id
            result["target_concept_id"] = target_id

        if not result.get("question_number"):
            result["question_number"] = len(self.session_data) + 1

        if not result.get("message"):
            fallback_name = (
                self.graph.concepts[target_id].name
                if target_id and target_id in self.graph.concepts
                else "your previous answer"
            )
            result["message"] = (
                f"Can you go deeper on {fallback_name} with concrete trade-offs?"
            )

        if self._pending_acknowledgement:
            result["message"] = f"{self._pending_acknowledgement}\n\n{result['message']}"
            self._pending_acknowledgement = ""

        self.last_target_concept = target_id
        self.conversation_history.append({"role": "assistant", "content": result["message"]})

        if result.get("question_number", 0) >= 8:
            self.session_complete = True

        return result

    def process_response(self, candidate_response: str) -> dict:
        self.conversation_history.append({"role": "user", "content": candidate_response})
        concept_map = [
            {"id": c.id, "name": c.name, "category": c.category}
            for c in self.graph.concepts.values()
        ]

        last_question = ""
        for message in reversed(self.conversation_history):
            if message["role"] == "assistant":
                last_question = message["content"]
                break

        extraction = extract_concepts_from_response(
            request_json=self._chat_json,
            question=last_question,
            response_text=candidate_response,
            experience_level=self.experience_level,
            interview_domain=self.interview_domain,
            concept_map=concept_map,
        )

        concepts_assessed = extraction.get("concepts_assessed", [])
        valid_assessments = [
            item
            for item in concepts_assessed
            if isinstance(item, dict) and item.get("concept_id") in self.graph.concepts
        ]
        self.graph.update_scores(valid_assessments)

        self.session_data.append(
            {
                "question": last_question,
                "response": candidate_response,
                "target_concept": self.last_target_concept,
                "concepts_assessed": valid_assessments,
                "quality": extraction.get("overall_response_quality", "unknown"),
                "notable_insight": extraction.get("notable_insight"),
            }
        )

        response_quality = str(extraction.get("overall_response_quality", "")).lower()
        strong_concepts = [
            item
            for item in valid_assessments
            if isinstance(item, dict) and int(item.get("depth_score", 0)) >= 2
        ]
        turn_index = len(self.session_data)
        should_acknowledge = (
            response_quality == "strong"
            and len(strong_concepts) >= 1
            and turn_index - self._last_ack_turn >= 2
            and turn_index >= 2
        )
        if should_acknowledge:
            self._pending_acknowledgement = (
                "That was a strong answer - clear structure and concrete trade-offs."
            )
            self._last_ack_turn = turn_index

        if len(self.session_data) >= 8:
            self.session_complete = True

        return extraction
