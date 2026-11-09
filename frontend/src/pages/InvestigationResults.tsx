import { useEffect, useMemo } from "react";

import type { InvestigationResponse } from "../types/investigation";
import type { AnalysisResults } from "../types/analysis";
import type { EvidenceGraphResponse } from "../types/graph";

import { EvidenceInfo } from "../components/EvidenceInfo";
import { IntegrityScore } from "../components/IntegrityScore";
import { FindingsList } from "../components/FindingsList";
import { ForensicSignals } from "../components/ForensicSignals";
import { ImageViewer } from "../components/ImageViewer";
import { OCRPanel } from "../components/OCRPanel";
import { EvidenceGraph } from "../components/EvidenceGraph";
import { evidenceUrl } from "../services/api";

interface InvestigationResultsProps {
  investigation: {
    response: InvestigationResponse;
    file: File;
    results: AnalysisResults;
    graph: EvidenceGraphResponse | null;
    analysisErrors: string[];
  };
  onReset: () => void;
}

export function InvestigationResults({ investigation, onReset }: InvestigationResultsProps) {
  const { response, file, results, graph, analysisErrors } = investigation;

  const isImage = response.file_type.startsWith("image/");
  const previewUrl = useMemo(() => URL.createObjectURL(file), [file]);

  useEffect(() => () => URL.revokeObjectURL(previewUrl), [previewUrl]);

  function downloadReport() {
    const report = {
      report_type: "ProofMesh investigation dossier",
      generated_at: new Date().toISOString(),
      investigation: response,
      limitations: [
        "Signals are heuristic observations for investigative prioritization, not proof of fraud.",
        "OCR output must be manually verified against the original evidence.",
      ],
      analysis: results,
      graph,
      analysis_errors: analysisErrors,
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `proofmesh-${response.investigation_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen px-5 py-6 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
          <div className="flex items-center gap-3"><span className="brand-mark">P</span><div><p className="text-lg font-bold text-white">ProofMesh</p><p className="text-xs text-slate-500">Investigation workspace</p></div></div>
          <div className="flex gap-2">
            <button onClick={downloadReport} className="button-secondary">Export JSON dossier</button>
            <a href={evidenceUrl(response.investigation_id)} download={response.filename} className="button-secondary">Download original</a>
            <button onClick={onReset} className="button-primary">New investigation</button>
          </div>
        </header>
        <div className="mb-8 flex items-end justify-between gap-4">
          <div><p className="eyebrow">Case {response.investigation_id.slice(0, 8)}</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">Evidence review</h1><p className="mt-2 text-sm text-slate-400">Signals are observations for human review, not an automated fraud determination.</p></div>
          <span className="pill hidden sm:inline-flex">{response.file_type}</span>
        </div>

        {analysisErrors.length > 0 && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4">
            <h3 className="font-semibold text-rose-300">Analysis Warnings</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-rose-200">
              {analysisErrors.map((err, index) => (
                <li key={index}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        <EvidenceInfo response={response} />

        <IntegrityScore fusion={results.fusion} />

        <div className="grid gap-6 lg:grid-cols-[1.1fr_.9fr]">
          <section className="panel">
            <div className="flex items-center justify-between"><div><p className="eyebrow">Source evidence</p><h2 className="mt-1 text-lg font-semibold text-white">Original document</h2></div><span className="text-xs text-slate-500">read-only preview</span></div>
            <div className="mt-5 overflow-hidden rounded-xl border border-slate-700 bg-slate-950">
              {isImage ? <img src={previewUrl} alt={response.filename} className="max-h-[520px] w-full object-contain" /> : <iframe title="Original PDF evidence" src={previewUrl} className="h-[520px] w-full" />}
            </div>
          </section>
          <section className="panel">
            <p className="eyebrow">Extracted intelligence</p>
            <h2 className="mt-1 text-lg font-semibold text-white">OCR text & metadata</h2>
            {results.ocr ? <div className="mt-5"><div className="mb-3 flex justify-between text-xs text-slate-400"><span>{results.ocr.blocks.length} positioned blocks</span><span>{results.ocr.average_confidence.toFixed(1)}% average confidence</span></div><pre className="max-h-[300px] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-300">{results.ocr.text || "No OCR text returned."}</pre></div> : <p className="mt-4 text-sm text-slate-400">OCR results are unavailable.</p>}
            {results.metadata && <details className="mt-4 rounded-xl border border-slate-700 bg-slate-950/50 p-4"><summary className="cursor-pointer text-sm font-medium text-slate-300">View source metadata</summary><pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-slate-400">{JSON.stringify(results.metadata.metadata, null, 2)}</pre></details>}
          </section>
        </div>

        <FindingsList
          metadata={results.metadata}
          document={results.document}
          fusion={results.fusion}
          ocr={results.ocr}
        />

        <ForensicSignals
          metadata={results.metadata}
          image={results.image}
          copyMove={results.copyMove}
          ocr={results.ocr}
          document={results.document}
        />

        {isImage && (
          <ImageViewer
            file={file}
            imageResults={results.image}
            copyMoveResults={results.copyMove}
            ocrBlocks={results.ocr?.blocks}
          />
        )}

        {results.ocr && <OCRPanel ocr={results.ocr} />}

        {graph && <EvidenceGraph graph={graph} />}
      </div>
    </div>
  );
}
