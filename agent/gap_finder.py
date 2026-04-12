from __future__ import annotations

from graph.builder import ConceptGraph


def suggest_next_gap(
    concept_graph: ConceptGraph, last_target_concept_id: str | None
) -> dict[str, str | None]:
    suggested_id = concept_graph.get_weakest_adjacent(last_target_concept_id)
    if suggested_id is None:
        return {
            "suggested_concept_id": None,
            "suggested_concept_name": None,
            "reason": "All concepts are fully covered.",
        }

    concept = concept_graph.concepts[suggested_id]
    if concept.depth_score == 0:
        reason = "This concept is currently unexplored and should be probed next."
    elif concept.depth_score == 1:
        reason = "This concept was touched only at a surface level and needs probing."
    else:
        reason = "This concept is adjacent to recent discussion and still not fully deep."

    return {
        "suggested_concept_id": suggested_id,
        "suggested_concept_name": concept.name,
        "reason": reason,
    }
