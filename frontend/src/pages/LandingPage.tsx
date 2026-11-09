import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

import { EvidenceUpload } from "../components/EvidenceUpload";
import { HealthStatus } from "../components/HealthStatus";
import { askCaseAssistant, casePdfReportUrl, classifyDocument, createCase, getCase, getCaseComparison, getCaseCustody, getCaseEntities, getCaseMethodology, getCaseReport, getCaseTimeline, getDashboard, getHealth, getStandards, loadDemoCase, login, register, searchCase, uploadCaseDocument, verifyCaseDocument } from "../services/api";
import type { DashboardResponse, InvestigationCase } from "../types/investigation";

type ConnectionState = "loading" | "online" | "offline";

interface LandingPageProps {
  onUpload: (file: File) => Promise<void>;
}

export function LandingPage({ onUpload }: LandingPageProps) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("loading");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [caseName, setCaseName] = useState("");
  const [selectedCase, setSelectedCase] = useState<InvestigationCase | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<string | null>(null);
  const [assistantAnswer, setAssistantAnswer] = useState<string | null>(null);
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [governance, setGovernance] = useState<{ custody: number; methodology: number; standards: number } | null>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [classification, setClassification] = useState<string | null>(null);
  const [language, setLanguage] = useState("en");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<string | null>(null);
  const [timelineCount, setTimelineCount] = useState(0);
  const [entityCount, setEntityCount] = useState(0);

  useEffect(() => {
    let active = true;

    Promise.all([getHealth(), getDashboard(), getStandards()])
      .then(([, data, standards]) => {
        if (active) {
          setConnectionState("online");
          setDashboard(data);
          setGovernance({ custody: 0, methodology: 0, standards: standards.length });
        }
      })
      .catch(() => active && setConnectionState("offline"));

    return () => {
      active = false;
    };
  }, []);

  async function handleCreateCase() {
    if (!caseName.trim()) return;
    setCaseError(null);
    try {
      const created = await createCase({ name: caseName, category: "general" });
      setSelectedCase(created);
      setCaseName("");
      setDashboard(await getDashboard());
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to create case.");
    }

  }

  async function handleDemo() {
    setCaseError(null);
    try {
      const demo = await loadDemoCase();
      setSelectedCase(demo);
      setDashboard(await getDashboard());
      const [timeline, entities] = await Promise.all([getCaseTimeline(demo.id), getCaseEntities(demo.id)]);
      setTimelineCount(timeline.length);
      setEntityCount(entities.nodes.length);
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to load demo case.");
    }

  }

  async function handleAuth(mode: "login" | "register") {
    setAuthMessage(null);
    try {
      const result = mode === "login"
        ? await login(authEmail, authPassword)
        : await register(authEmail, authPassword, authEmail.split("@")[0] || "Investigator");
      if (typeof result.access_token === "string") localStorage.setItem("proofmesh_access_token", result.access_token);
      setAuthMessage(mode === "login" ? "Signed in successfully." : "Account created and signed in.");
    } catch (error) {
      setAuthMessage(error instanceof Error ? error.message : "Authentication failed.");
    }
  }

  async function handleCaseFiles(event: ChangeEvent<HTMLInputElement>) {
    if (!selectedCase || !event.target.files?.length) return;
    setCaseError(null);
    try {
      for (const file of Array.from(event.target.files)) {
        await uploadCaseDocument(selectedCase.id, file);
      }

      const refreshed = await getDashboard();
      setDashboard(refreshed);
      setSelectedCase(await getCase(selectedCase.id));
      const [custody, methodology] = await Promise.all([getCaseCustody(selectedCase.id), getCaseMethodology(selectedCase.id)]);
      setGovernance((current) => ({ standards: current?.standards ?? 0, custody: custody.length, methodology: methodology.length }));
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to attach documents.");
    }
  }

  async function handleCompare() {
    if (!selectedCase) return;
    try {
      const result = await getCaseComparison(selectedCase.id);
      setComparison(result.comparisons.map((item) => `${item.left_document} ↔ ${item.right_document}: ${item.status} — ${item.explanation}`).join("\n") || "Add at least two documents to compare.");
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to compare documents.");
    }
  }

  async function handleReport() {
    if (!selectedCase) return;
    const report = await getCaseReport(selectedCase.id);
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `proofmesh-case-${selectedCase.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function handleAssistant() {
    if (!selectedCase || !assistantQuestion.trim()) return;
    try {
      const result = await askCaseAssistant(selectedCase.id, assistantQuestion, language);
      setAssistantAnswer(result.answer);
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to query the assistant.");
    }

  }

  async function handleClassify(documentId: string) {
    if (!selectedCase) return;
    try {
      const result = await classifyDocument(selectedCase.id, documentId);
      setClassification(`${result.classification} (${Math.round(result.confidence * 100)}%): ${result.explanation}`);
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to classify document.");
    }

  }

  async function handleIntegrity(documentId: string) {
    if (!selectedCase) return;
    try {
      const result = await verifyCaseDocument(selectedCase.id, documentId);
      setClassification(result.verified ? "Integrity verified: stored SHA-256 matches the current original." : "Integrity warning: SHA-256 mismatch requires review.");
    } catch (error) {
      setCaseError(error instanceof Error ? error.message : "Unable to verify integrity.");
    }
  }

  async function handleSearch() {
    if (!selectedCase || !searchQuery.trim()) return;
    const results = await searchCase(selectedCase.id, searchQuery);
    setSearchResult(results.length ? results.map((item) => `${item.filename} (${Math.round(item.score * 100)}%): ${item.snippet}`).join("\n") : "No evidence matched that search.");
  }

  return (
    <main className="min-h-screen overflow-hidden px-5 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto max-w-7xl">
        <nav className="flex items-center justify-between border-b border-slate-800/80 pb-6">
          <div className="flex items-center gap-3">
            <span className="brand-mark">P</span>
            <span className="text-lg font-bold tracking-tight text-white">ProofMesh</span>
          </div>
          <HealthStatus state={connectionState} />
        </nav>
        <section className="mt-6 flex flex-wrap items-center justify-end gap-2 text-xs">
          <input value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} placeholder="email" type="email" className="w-40 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200 outline-none focus:border-[#5b8cff]" />
          <input value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} placeholder="password (8+)" type="password" className="w-32 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200 outline-none focus:border-[#5b8cff]" />
          <button onClick={() => handleAuth("login")} className="button-secondary">Sign in</button>
          <button onClick={() => handleAuth("register")} className="button-secondary">Register</button>
          {authMessage && <span className="text-emerald-300">{authMessage}</span>}
        </section>
        <div className="grid items-center gap-12 py-16 lg:grid-cols-[1.05fr_.95fr] lg:py-24">
          <section>
            <p className="eyebrow">Document intelligence platform</p>
            <h1 className="mt-5 max-w-3xl text-5xl font-bold leading-[1.05] tracking-tight text-white sm:text-7xl">
              Beyond OCR. <span className="text-gradient">Into evidence intelligence.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300">
              Preserve, inspect, and explain digital evidence with transparent forensic signals.
              Every observation remains traceable to the original file—not a black-box verdict.
            </p>
            <EvidenceUpload onUpload={onUpload} />
            <div className="mt-7 flex flex-wrap gap-3 text-xs text-slate-400">
              {["SHA-256 integrity", "Metadata & OCR", "Image forensics", "Explainable scoring"].map((item) => (
                <span key={item} className="pill">{item}</span>
              ))}
            </div>
          </section>
          <section className="dashboard-preview">
            <div className="flex items-center justify-between border-b border-slate-700/70 pb-4">
              <div>
                <p className="text-xs uppercase tracking-[.18em] text-slate-500">Live workspace</p>
                <p className="mt-1 font-semibold text-white">Evidence overview</p>
              </div>
              <span className="status-dot">Pipeline ready</span>
            </div>
            <div className="mt-4 rounded-xl border border-slate-700/70 bg-slate-950/50 p-4">
              <div className="flex items-center justify-between text-xs text-slate-400"><span>Analysis pipeline</span><span>Traceable by design</span></div>
              <div className="mt-4 space-y-3">
                {["Evidence fingerprint", "Visual forensics", "Context & explanation"].map((label, index) => (
                  <div key={label} className="flex items-center gap-3 text-sm text-slate-300">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300">✓</span>
                    <span>{label}</span>
                    <span className="ml-auto text-xs text-slate-500">{index === 0 ? "verified" : "complete"}</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="mt-5 text-xs leading-5 text-slate-500">Illustrative preview. Scores are calculated from the uploaded evidence during analysis.</p>
          </section>
        </div>
        <section className="grid gap-4 border-t border-slate-800/80 py-10 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["01", "Preserve", "Fingerprint the original file before analysis."],
            ["02", "Measure", "Combine metadata, image, copy-move, and OCR signals."],
            ["03", "Explain", "Connect each finding to evidence and confidence."],
            ["04", "Review", "Keep a human investigator in the loop."],
          ].map(([number, title, copy]) => (
            <div key={number} className="feature-card"><span>{number}</span><h2>{title}</h2><p>{copy}</p></div>
          ))}
        </section>
        <section className="panel mb-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><p className="eyebrow">Persistent workspace</p><h2 className="mt-1 text-xl font-semibold text-white">Investigation cases</h2><p className="mt-1 text-sm text-slate-400">Create a case and attach multiple documents with duplicate detection and an audit trail.</p></div>
            <div className="flex flex-wrap gap-2"><input value={caseName} onChange={(event) => setCaseName(event.target.value)} placeholder="Case name" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-[#5b8cff]" /><button onClick={handleCreateCase} className="button-primary">Create case</button><button onClick={handleDemo} className="button-secondary">Load synthetic demo</button></div>
          </div>
          {selectedCase && <div className="mt-5 rounded-xl border border-[#5b8cff]/40 bg-[#5b8cff]/10 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold text-white">{selectedCase.name}</p><p className="text-xs text-slate-400">{selectedCase.documents.length} documents attached · {timelineCount} timeline events · {entityCount} graph nodes</p></div><div className="flex flex-wrap gap-2"><label className="button-secondary cursor-pointer">Attach documents<input type="file" multiple accept=".png,.jpg,.jpeg,.pdf" className="hidden" onChange={handleCaseFiles} /></label><button onClick={handleCompare} className="button-secondary">Compare</button><button onClick={handleReport} className="button-secondary">Export JSON</button><a href={casePdfReportUrl(selectedCase.id)} className="button-secondary">Export PDF</a></div></div><div className="mt-4 space-y-2">{selectedCase.documents.map((document) => <div key={document.id} className="flex items-center justify-between rounded-lg bg-slate-950/50 px-3 py-2 text-xs text-slate-300"><span className="truncate">{document.filename}</span><span className="flex gap-3"><button onClick={() => handleClassify(document.id)} className="text-[#8bb0ff] hover:text-white">Classify</button><button onClick={() => handleIntegrity(document.id)} className="text-emerald-300 hover:text-white">Verify hash</button></span></div>)}</div>{classification && <p className="mt-3 rounded-lg bg-slate-950/70 p-3 text-sm text-slate-300">{classification}</p>}<div className="mt-4 flex gap-2"><select value={language} onChange={(event) => setLanguage(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-300"><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option></select><input value={assistantQuestion} onChange={(event) => setAssistantQuestion(event.target.value)} placeholder="Ask about this case…" className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-[#5b8cff]" /><button onClick={handleAssistant} className="button-primary">Ask</button></div>{assistantAnswer && <p className="mt-3 rounded-lg bg-slate-950/70 p-3 text-sm leading-6 text-slate-300">{assistantAnswer}</p>}<div className="mt-4 flex gap-2"><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search evidence text…" className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-[#5b8cff]" /><button onClick={handleSearch} className="button-secondary">Search</button></div>{searchResult && <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-950/70 p-3 text-xs leading-5 text-slate-300">{searchResult}</pre>}{comparison && <pre className="mt-4 whitespace-pre-wrap rounded-lg bg-slate-950/70 p-3 text-xs leading-5 text-slate-300">{comparison}</pre>}</div>}
          {caseError && <p className="mt-3 text-sm text-rose-300">{caseError}</p>}
          {dashboard && <div className="mt-5 grid gap-3 sm:grid-cols-4"><div className="metric-card"><span>Cases</span><strong>{dashboard.total_investigations}</strong><small>persistent</small></div><div className="metric-card"><span>Documents</span><strong>{dashboard.total_documents}</strong><small>stored securely</small></div><div className="metric-card"><span>Pending</span><strong>{dashboard.pending_investigations}</strong><small>in review</small></div><div className="metric-card"><span>Complete</span><strong>{dashboard.completed_investigations}</strong><small>processed</small></div></div>}
          {governance && <div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="metric-card"><span>Custody events</span><strong>{governance.custody}</strong><small>chain of custody</small></div><div className="metric-card"><span>Analysis runs</span><strong>{governance.methodology}</strong><small>reproducibility records</small></div><div className="metric-card"><span>Mapped controls</span><strong>{governance.standards}</strong><small>standards intelligence</small></div></div>}
        </section>
      </div>
    </main>
  );
}
