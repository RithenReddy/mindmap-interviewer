from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx


@dataclass
class ConceptNode:
    id: str
    name: str
    category: str
    parent_id: str | None
    importance: str
    depth_score: int = 0
    evidence: list[str] = field(default_factory=list)


class ConceptGraph:
    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.concepts: dict[str, ConceptNode] = {}

    def build_from_jd_parse(self, parsed_concepts: list[dict]) -> None:
        for concept in parsed_concepts:
            concept_id = concept["id"]
            if concept_id in self.concepts:
                continue

            node = ConceptNode(
                id=concept_id,
                name=concept["name"],
                category=concept["category"],
                parent_id=concept.get("parent_id"),
                importance=concept["importance"],
            )
            self.concepts[node.id] = node
            self.graph.add_node(
                node.id,
                name=node.name,
                category=node.category,
                importance=node.importance,
                depth_score=node.depth_score,
            )

        for node in self.concepts.values():
            if node.parent_id and node.parent_id in self.concepts:
                self.graph.add_edge(node.parent_id, node.id)

        siblings_by_parent: dict[str, list[str]] = {}
        for node in self.concepts.values():
            if node.parent_id and node.parent_id in self.concepts:
                siblings_by_parent.setdefault(node.parent_id, []).append(node.id)

        for siblings in siblings_by_parent.values():
            for i in range(len(siblings)):
                for j in range(i + 1, len(siblings)):
                    left = siblings[i]
                    right = siblings[j]
                    self.graph.add_edge(left, right)
                    self.graph.add_edge(right, left)

    def update_scores(self, assessments: list[dict]) -> None:
        for assessment in assessments:
            concept_id = assessment.get("concept_id")
            if concept_id not in self.concepts:
                continue

            depth_score = assessment.get("depth_score")
            if not isinstance(depth_score, int):
                continue
            depth_score = max(0, min(3, depth_score))

            concept = self.concepts[concept_id]
            if depth_score > concept.depth_score:
                concept.depth_score = depth_score
                self.graph.nodes[concept_id]["depth_score"] = depth_score

            evidence = assessment.get("evidence")
            if isinstance(evidence, str) and evidence.strip():
                concept.evidence.append(evidence.strip())

    def get_weakest_adjacent(self, last_concept_id: str | None = None) -> str | None:
        if last_concept_id is None or last_concept_id not in self.graph:
            critical_unexplored = [
                c
                for c in self.concepts.values()
                if c.importance == "critical" and c.depth_score == 0
            ]
            if critical_unexplored:
                return critical_unexplored[0].id

            any_unexplored = [c for c in self.concepts.values() if c.depth_score == 0]
            if any_unexplored:
                return any_unexplored[0].id

            return next((c.id for c in self.concepts.values() if c.depth_score < 3), None)

        importance_order = {"critical": 0, "important": 1, "nice_to_have": 2}
        neighbors = list(self.graph.neighbors(last_concept_id))
        candidates = neighbors + [last_concept_id]

        ranked: list[tuple[int, int, str]] = []
        for concept_id in candidates:
            concept = self.concepts.get(concept_id)
            if concept is None:
                continue
            ranked.append(
                (
                    concept.depth_score,
                    importance_order.get(concept.importance, 2),
                    concept.id,
                )
            )

        ranked.sort()
        for score, _importance, concept_id in ranked:
            if score < 3:
                return concept_id

        all_ranked = sorted(
            self.concepts.values(),
            key=lambda c: (c.depth_score, importance_order.get(c.importance, 2)),
        )
        for concept in all_ranked:
            if concept.depth_score < 3:
                return concept.id

        return None

    def get_state_summary(self) -> str:
        depth_labels = {0: "UNEXPLORED", 1: "SURFACE", 2: "PARTIAL", 3: "DEEP"}
        lines: list[str] = []
        for concept in self.concepts.values():
            lines.append(
                f"- {concept.name} [{concept.category}] ({concept.importance}): "
                f"{depth_labels[concept.depth_score]} ({concept.depth_score}/3)"
            )
        return "\n".join(lines)

    def get_stats(self) -> dict:
        total = len(self.concepts)
        if total == 0:
            return {
                "total": 0,
                "explored": 0,
                "deep": 0,
                "coverage_pct": 0,
                "deep_pct": 0,
                "avg_depth": 0,
            }

        scores = [concept.depth_score for concept in self.concepts.values()]
        explored = sum(1 for score in scores if score > 0)
        deep = sum(1 for score in scores if score >= 3)

        return {
            "total": total,
            "explored": explored,
            "deep": deep,
            "coverage_pct": round((explored / total) * 100),
            "deep_pct": round((deep / total) * 100),
            "avg_depth": round(sum(scores) / total, 2),
        }
