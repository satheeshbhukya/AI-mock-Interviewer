import { useState, useRef, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL || "https://happy4040-mock-technical-interviewer.hf.space";

function Markdown({ text }) {
  const html = (text || "")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`{3}[\w]*\n?([\s\S]*?)`{3}/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^---$/gm, "<hr/>")
    .replace(/^\*   (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>");
  return <div className="md-body" dangerouslySetInnerHTML={{ __html: `<p>${html}</p>` }} />;
}

function Whiteboard({ onCapture }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const lastPos = useRef(null);
  const [color, setColor] = useState("#f0f4ff");
  const [lineWidth, setLineWidth] = useState(3);
  const [eraser, setEraser] = useState(false);

  const getPos = (e, canvas) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    if (e.touches) return { x: (e.touches[0].clientX - rect.left) * scaleX, y: (e.touches[0].clientY - rect.top) * scaleY };
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY };
  };

  const startDraw = (e) => { e.preventDefault(); drawing.current = true; lastPos.current = getPos(e, canvasRef.current); };
  const draw = (e) => {
    e.preventDefault();
    if (!drawing.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const pos = getPos(e, canvas);
    ctx.beginPath(); ctx.moveTo(lastPos.current.x, lastPos.current.y); ctx.lineTo(pos.x, pos.y);
    ctx.strokeStyle = eraser ? "#0e1117" : color; ctx.lineWidth = eraser ? 20 : lineWidth;
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke();
    lastPos.current = pos;
  };
  const stopDraw = () => { drawing.current = false; };
  const clear = () => {
    const canvas = canvasRef.current; const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0e1117"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  };
  useEffect(() => { clear(); }, []);
  const capture = () => { const b64 = canvasRef.current.toDataURL("image/png").split(",")[1]; onCapture(b64); };

  return (
    <div className="whiteboard-wrap">
      <div className="wb-toolbar">
        <span className="wb-label">Whiteboard</span>
        <div className="color-swatches">
          {["#f0f4ff","#7ee8a2","#ffd166","#ef476f","#06d6a0","#ffffff"].map(c => (
            <button key={c} className={`swatch${color === c && !eraser ? " active" : ""}`}
              style={{ background: c }} onClick={() => { setColor(c); setEraser(false); }} />
          ))}
        </div>
        <input type="range" min="1" max="12" value={lineWidth} onChange={e => setLineWidth(+e.target.value)} className="size-slider" title="Brush size" />
        <button className={`wb-btn${eraser ? " active" : ""}`} onClick={() => setEraser(!eraser)}>Erase</button>
        <button className="wb-btn" onClick={clear}>Clear</button>
        <button className="wb-btn send-wb" onClick={capture}>Send to AI</button>
      </div>
      <canvas ref={canvasRef} width={900} height={340} className="wb-canvas"
        onMouseDown={startDraw} onMouseMove={draw} onMouseUp={stopDraw} onMouseLeave={stopDraw}
        onTouchStart={startDraw} onTouchMove={draw} onTouchEnd={stopDraw} />
    </div>
  );
}

function Message({ role, text }) {
  return (
    <div className={`msg ${role}`}>
      <div className="msg-avatar">{role === "ai" ? "AI" : "You"}</div>
      <div className="msg-bubble">{role === "ai" ? <Markdown text={text} /> : <p>{text}</p>}</div>
    </div>
  );
}

function CodeEditor({ value, onChange }) {
  return (
    <div className="code-editor-wrap">
      <div className="code-editor-header">
        <span className="dot red"/><span className="dot yellow"/><span className="dot green"/>
        <span className="code-lang">Python</span>
      </div>
      <textarea className="code-editor" value={value} onChange={e => onChange(e.target.value)}
        spellCheck={false} placeholder="# Write your solution here..." />
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState("home");
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [problem, setProblem] = useState("");
  const [code, setCode] = useState("# Your solution here\n");
  const [codeChanged, setCodeChanged] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [finished, setFinished] = useState(false);
  const [report, setReport] = useState("");
  const [showWb, setShowWb] = useState(false);
  const [error, setError] = useState("");
  const chatEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const apiFetch = (path, opts = {}) =>
    fetch(`${API_URL}${path}`, {
      ...opts,
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    });

  const startSession = async () => {
    setError(""); setStarting(true);
    try {
      const res = await apiFetch("/api/session/start", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([{ role: "ai", text: data.message }]);
      setScreen("interview");
    } catch (e) {
      setError("Could not connect to the server. Please try again.");
    } finally { setStarting(false); }
  };

  const sendMessage = async (extraImageBase64 = null) => {
    if (!input.trim() && !codeChanged && !extraImageBase64) return;
    const userText = input.trim();
    setInput("");
    const userMsg = userText || (extraImageBase64 ? "[Whiteboard sent]" : "[Code updated]");
    setMessages(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);
    try {
      const body = { session_id: sessionId, message: userText, code, code_changed: codeChanged, image_base64: extraImageBase64 || null };
      setCodeChanged(false);
      const res = await apiFetch("/api/chat", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMessages(m => [...m, { role: "ai", text: data.message }]);
      if (data.problem && !data.problem.includes("not been selected")) setProblem(data.problem);
      if (data.code && data.code !== "# Your code here") setCode(data.code);
      if (data.finished) { setFinished(true); if (data.report) setReport(data.report); }
    } catch (e) {
      setMessages(m => [...m, { role: "ai", text: `Something went wrong. Please try again.` }]);
    } finally { setLoading(false); }
  };

  const handleWbCapture = (b64) => { setShowWb(false); sendMessage(b64); };
  const handleKeyDown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
  const downloadReport = () => {
    const blob = new Blob([report], { type: "text/markdown" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "interview_report.md"; a.click();
  };

  if (screen === "home") return (
    <div className="home-screen">
      <div className="home-card">
        <div className="logo-mark">⬡</div>
        <h1 className="home-title">Mock Technologie<br/><span>Interview Suite</span></h1>
        <p className="home-sub">Practice real technical interviews with an AI interviewer powered by Google Gemini. Get hints, use the whiteboard, write code, and receive a full evaluation report.</p>

        <div className="features-row">
          <div className="feat"><span>🧠</span><p>Gemini AI</p></div>
          <div className="feat"><span>🖊</span><p>Whiteboard</p></div>
          <div className="feat"><span>💻</span><p>Code Editor</p></div>
          <div className="feat"><span>📊</span><p>Report</p></div>
        </div>

        {error && <p className="err-msg">{error}</p>}

        <button className="start-btn" onClick={startSession} disabled={starting}>
          {starting ? <span className="spinner"/> : "Start Interview →"}
        </button>
      </div>
      <div className="home-bg">
        {Array.from({length:24}).map((_,i)=>(
          <div key={i} className="bg-orb" style={{animationDelay:`${i*0.3}s`, left:`${(i*41)%100}%`, top:`${(i*31)%100}%`}}/>
        ))}
      </div>
    </div>
  );

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-brand"><span className="header-logo">⬡</span><span>Mock Technologie Inc.</span></div>
        <div className="header-status">
          {finished
            ? <span className="badge done">✓ Complete</span>
            : <span className="badge live"><span className="pulse"/>Live</span>}
        </div>
        {finished && (
          <div className="header-actions">
            <button className="hdr-btn" onClick={downloadReport}>⬇ Download Report</button>
            <button className="hdr-btn accent" onClick={() => setScreen("report")}>View Report</button>
          </div>
        )}
      </header>

      <div className="layout">
        <div className="left-panel">
          <div className="problem-box">
            <div className="problem-header"><span>📋</span><span>Problem Statement</span></div>
            <div className="problem-body">
              {!problem || problem === "No problem selected yet." || problem === "Problem has not been selected yet"
                ? <p className="no-problem">A question will appear here once selected.</p>
                : <Markdown text={problem} />}
            </div>
          </div>

          <div className="chat-box">
            <div className="chat-messages">
              {messages.map((m, i) => <Message key={i} role={m.role} text={m.text} />)}
              {loading && (
                <div className="msg ai">
                  <div className="msg-avatar">AI</div>
                  <div className="msg-bubble typing"><span/><span/><span/></div>
                </div>
              )}
              <div ref={chatEndRef}/>
            </div>
            <div className="chat-input-row">
              <textarea className="chat-input" rows={3}
                placeholder="Type your message… (Enter to send, Shift+Enter for newline)"
                value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown} disabled={loading || finished} />
              <div className="chat-actions">
                <button className="icon-btn" title="Whiteboard" onClick={() => setShowWb(v => !v)} disabled={finished}>🖊</button>
                <button className="send-btn" onClick={() => sendMessage()}
                  disabled={loading || finished || (!input.trim() && !codeChanged)}>
                  {loading ? <span className="spinner sm"/> : "Send →"}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="right-panel">
          <div className="panel-header">
            <span>Code Editor</span>
            {codeChanged && <span className="changed-badge">● unsent changes</span>}
          </div>
          <CodeEditor value={code} onChange={v => { setCode(v); setCodeChanged(true); }}/>
          <button className="submit-code-btn" onClick={() => sendMessage()} disabled={loading || finished || !codeChanged}>
            Submit Code Update
          </button>
        </div>
      </div>

      {showWb && (
        <div className="wb-overlay">
          <div className="wb-modal">
            <div className="wb-modal-header">
              <span>Whiteboard — Draw your approach</span>
              <button className="close-btn" onClick={() => setShowWb(false)}>✕</button>
            </div>
            <Whiteboard onCapture={handleWbCapture}/>
          </div>
        </div>
      )}

      {screen === "report" && (
        <div className="report-overlay">
          <div className="report-modal">
            <div className="report-modal-header">
              <span>📊 Interview Evaluation Report</span>
              <div style={{display:"flex",gap:"8px"}}>
                <button className="hdr-btn" onClick={downloadReport}>⬇ Download</button>
                <button className="close-btn" onClick={() => setScreen("interview")}>✕</button>
              </div>
            </div>
            <div className="report-body"><Markdown text={report || "Generating report…"} /></div>
          </div>
        </div>
      )}
    </div>
  );
}