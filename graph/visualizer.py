from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from graph.builder import ConceptGraph


def render_concept_graph(
    concept_graph: ConceptGraph,
    height: str = "500px",
    highlight_concept_id: str | None = None,
) -> str:
    net = Network(
        height=height,
        width="100%",
        bgcolor="#0E1117",
        font_color="white",
        directed=True,
    )

    depth_colors = {
        0: "#6B7280",
        1: "#EF4444",
        2: "#F59E0B",
        3: "#10B981",
    }
    importance_sizes = {"critical": 35, "important": 25, "nice_to_have": 18}
    category_shapes = {"technical": "dot", "behavioral": "diamond", "domain": "square"}
    depth_labels = {0: "Unexplored", 1: "Surface", 2: "Partial", 3: "Deep"}

    for concept_id, concept in concept_graph.concepts.items():
        color = depth_colors.get(concept.depth_score, "#6B7280")
        size = importance_sizes.get(concept.importance, 20)
        shape = category_shapes.get(concept.category, "dot")

        tooltip = (
            f"<b>{concept.name}</b><br>"
            f"Category: {concept.category}<br>"
            f"Importance: {concept.importance}<br>"
            f"Depth: {depth_labels[concept.depth_score]} ({concept.depth_score}/3)<br>"
        )
        if concept.evidence:
            tooltip += f"Evidence: {'; '.join(concept.evidence[-2:])}"

        net.add_node(
            concept_id,
            label=f"{concept.name}\n({concept.depth_score}/3)",
            color={
                "background": color,
                "border": "#FFFFFF",
                "highlight": {"background": color, "border": "#FFFFFF"},
            },
            size=size,
            shape=shape,
            title=tooltip,
            borderWidth=4 if highlight_concept_id == concept_id else 1,
            font={"size": 12, "color": "white"},
        )

    rendered_sibling_edges: set[tuple[str, str]] = set()
    for source, target in concept_graph.graph.edges():
        source_node = concept_graph.concepts[source]
        target_node = concept_graph.concepts[target]
        is_parent_child = (
            source_node.parent_id == target or target_node.parent_id == source
        )
        if is_parent_child:
            net.add_edge(source, target, color="#4B5563", width=2)
            continue

        undirected_key = tuple(sorted((source, target)))
        if undirected_key in rendered_sibling_edges:
            continue
        rendered_sibling_edges.add(undirected_key)
        net.add_edge(source, target, color="#374151", width=1, dashes=True)

    net.set_options(
        """
        {
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -50,
                    "centralGravity": 0.01,
                    "springLength": 120,
                    "springConstant": 0.08
                },
                "solver": "forceAtlas2Based",
                "stabilization": {"iterations": 100}
            },
            "interaction": {
                "hover": true,
                "tooltipDelay": 100
            }
        }
        """
    )

    return net.generate_html()


def display_graph_in_streamlit(
    concept_graph: ConceptGraph, height: int = 500, highlight_concept_id: str | None = None
) -> None:
    html = render_concept_graph(
        concept_graph, height=f"{height}px", highlight_concept_id=highlight_concept_id
    )
    components.html(html, height=height + 50, scrolling=False)


def render_legend() -> None:
    columns = st.columns(4)
    columns[0].markdown("⬤ :gray[Unexplored]")
    columns[1].markdown("⬤ :red[Surface]")
    columns[2].markdown("⬤ :orange[Partial]")
    columns[3].markdown("⬤ :green[Deep]")
