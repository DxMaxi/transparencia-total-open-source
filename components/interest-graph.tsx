"use client";

import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { ExternalLinkIcon, ShieldCheckIcon } from "@/components/icons";
import type {
  InterestEdgeData,
  InterestGraphDataset,
  InterestNodeData,
} from "@/types/public-data";

type Selection =
  | { type: "edge"; id: string; data: InterestEdgeData }
  | { type: "node"; id: string; data: InterestNodeData };

const nodeLabels: Record<InterestNodeData["kind"], string> = {
  person: "Pessoa",
  public: "Entidade pública",
  company: "Organização",
  contract: "Contrato",
  party: "Partido",
  other: "Entidade",
};

function fallbackPosition(index: number) {
  return { x: (index % 3) * 285 + 35, y: Math.floor(index / 3) * 185 + 35 };
}

export function InterestGraph({ dataset }: { dataset: InterestGraphDataset }) {
  const nodes = useMemo<Node<InterestNodeData>[]>(
    () =>
      dataset.nodes.map((node, index) => ({
        ...node,
        position: node.position ?? fallbackPosition(index),
        className: `interest-node interest-node--${node.data.kind}`,
        ariaLabel: `${nodeLabels[node.data.kind]}: ${node.data.label}`,
      })),
    [dataset.nodes],
  );
  const edges = useMemo<Edge<InterestEdgeData>[]>(
    () =>
      dataset.edges.map((edge) => ({
        ...edge,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed, color: "#54706d" },
        style: { stroke: "#54706d", strokeWidth: 1.8 },
        labelStyle: { fill: "#344054", fontSize: 10, fontWeight: 700 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.94 },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 5,
      })),
    [dataset.edges],
  );
  const firstEdge = edges[0];
  const [selection, setSelection] = useState<Selection | null>(
    firstEdge
      ? { type: "edge", id: firstEdge.id, data: firstEdge.data as InterestEdgeData }
      : null,
  );

  const selectedExists = selection && (
    selection.type === "edge"
      ? edges.some((edge) => edge.id === selection.id)
      : nodes.some((node) => node.id === selection.id)
  );
  const activeSelection = selectedExists
    ? selection
    : firstEdge
      ? { type: "edge" as const, id: firstEdge.id, data: firstEdge.data as InterestEdgeData }
      : null;

  return (
    <section className="investigator-card investigator-card--graph" aria-labelledby="graph-title">
      <div className="investigator-card__heading">
        <div>
          <span className="eyebrow">Grafo de interesses</span>
          <h2 id="graph-title">Ligações documentadas, não insinuações</h2>
        </div>
        <span className="v2-demo-chip">{dataset.isDemonstration ? "Amostra fictícia" : "Dados publicados"}</span>
      </div>

      <div className="graph-layout">
        <div className="graph-canvas" aria-label="Mapa demonstrativo de relações verificáveis">
          <ReactFlow<Node<InterestNodeData>, Edge<InterestEdgeData>>
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.55}
            maxZoom={1.8}
            nodesConnectable={false}
            nodesDraggable={false}
            onNodeClick={(_event, node) =>
              setSelection({ type: "node", id: node.id, data: node.data })
            }
            onEdgeClick={(_event, edge) =>
              setSelection({
                type: "edge",
                id: edge.id,
                data: edge.data as InterestEdgeData,
              })
            }
          >
            <Background color="#d7e2e0" gap={22} size={1} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node) => {
                const kind = (node.data as InterestNodeData).kind;
                return kind === "person" ? "#0f766e" : kind === "contract" ? "#a15c00" : "#577087";
              }}
              maskColor="rgba(244,247,246,.75)"
            />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <aside className="graph-inspector" aria-live="polite">
          {activeSelection?.type === "edge" ? (
            <>
              <span className="graph-inspector__type">Relação selecionada</span>
              <h3>{activeSelection.data.label}</h3>
              <dl>
                <div><dt>Período</dt><dd>{activeSelection.data.period}</dd></div>
                <div><dt>Estado</dt><dd><ShieldCheckIcon /> {activeSelection.data.reviewState}</dd></div>
                <div><dt>Hash</dt><dd className="hash-value">{activeSelection.data.source.sha256}</dd></div>
              </dl>
              <a
                className="evidence-link"
                href={activeSelection.data.source.url}
                target="_blank"
                rel="noreferrer"
              >
                <span><b>{activeSelection.data.source.publisher}</b>{activeSelection.data.source.label}</span>
                <ExternalLinkIcon />
              </a>
              <p className="graph-legal-note">
                Uma ligação mostra apenas o que a fonte comprova. Não representa, por si, conflito de interesses ou ilícito.
              </p>
            </>
          ) : activeSelection?.type === "node" ? (
            <>
              <span className="graph-inspector__type">Nó selecionado</span>
              <h3>{activeSelection.data.label}</h3>
              <p>{activeSelection.data.subtitle}</p>
              <span className="verified-chip"><ShieldCheckIcon /> {dataset.isDemonstration ? "Exemplo revisto" : "Entidade verificada"}</span>
              <p className="graph-legal-note">
                Abra uma relação para consultar período, prova e impressão digital da fonte.
              </p>
            </>
          ) : <p className="graph-legal-note">Sem relações publicadas para inspecionar.</p>}
        </aside>
      </div>

      <div className="graph-relation-list" aria-label="Lista acessível de relações">
        {edges.map((edge) => (
          <button
            type="button"
            key={edge.id}
            className={activeSelection?.id === edge.id ? "is-active" : ""}
            onClick={() =>
              setSelection({ type: "edge", id: edge.id, data: edge.data as InterestEdgeData })
            }
          >
            <span>{edge.label}</span>
            <small>{(edge.data as InterestEdgeData).reviewState} · ver prova</small>
          </button>
        ))}
      </div>
    </section>
  );
}
