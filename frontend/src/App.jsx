import React,{useEffect,useRef,useState} from "react";
import cytoscape from "cytoscape";
const API=import.meta.env.VITE_API_BASE||"http://127.0.0.1:8000";
async function req(path,opts={}) {
  const r=await fetch(API+path,opts);
  const data=await r.json().catch(()=>({detail:"Unexpected server response"}));
  if(!r.ok) throw new Error(data.detail||"Request failed");
  return data;
}
function Graph({data}) {
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current)return;
    const cy=cytoscape({container:ref.current,elements:[...data.nodes,...data.edges],
      style:[
        {selector:"node",style:{"background-color":"#58d6c5","label":"data(label)","color":"#e8efff","font-size":10,"text-wrap":"wrap","text-max-width":90,"width":34,"height":34,"text-valign":"bottom","text-margin-y":7}},
        {selector:"edge",style:{"width":2,"line-color":"#56617e","target-arrow-color":"#56617e","target-arrow-shape":"triangle","curve-style":"bezier","label":"data(label)","font-size":8,"color":"#aab5ce","text-background-color":"#11182b","text-background-opacity":1}},
        {selector:"node[status = 'rejected']",style:{"background-color":"#ef6679"}},
        {selector:"node[status = 'approved']",style:{"background-color":"#65d69a"}}
      ],layout:{name:"cose",animate:false,padding:25},userZoomingEnabled:true});
    return ()=>cy.destroy();
  },[data]);
  return <div ref={ref} className="graph"/>;
}
export default function App(){
 const [tab,setTab]=useState("Overview"),[docs,setDocs]=useState([]),[entities,setEntities]=useState([]),[rels,setRels]=useState([]),[graph,setGraph]=useState({nodes:[],edges:[]}),[signals,setSignals]=useState([]),[health,setHealth]=useState(null),[busy,setBusy]=useState(false),[msg,setMsg]=useState(""),[summary,setSummary]=useState("");
 const [title,setTitle]=useState("New public source"),[source,setSource]=useState("Public/authorized source"),[content,setContent]=useState("");
 async function refresh(){
   try{const [d,e,r,g,s,h]=await Promise.all([req("/api/documents"),req("/api/entities"),req("/api/relations"),req("/api/graph"),req("/api/signals"),req("/api/health")]);setDocs(d);setEntities(e);setRels(r);setGraph(g);setSignals(s);setHealth(h)}catch(e){setMsg(e.message)}
 }
 useEffect(()=>{refresh()},[]);
 async function act(fn){setBusy(true);setMsg("");try{await fn();await refresh()}catch(e){setMsg(e.message)}finally{setBusy(false)}}
 async function addSource(e){e.preventDefault();await act(async()=>{await req("/api/documents",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title,source_label:source,content,language:"auto"})});setContent("");setMsg("Source saved.")})}
 async function analyze(id){await act(async()=>{const x=await req("/api/analyze/"+id,{method:"POST"});setSummary(x.summary||"");setMsg("Analysis complete. Review all candidate results before relying on them.")})}
 async function review(kind,id,status){await act(async()=>{await req(`/api/${kind}/${id}/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})})})}
 async function upload(e,kind){const f=e.target.files[0];if(!f)return;await act(async()=>{const fd=new FormData();fd.append("file",f);const path=kind==="audio"?"/api/audio/transcribe":"/api/documents/upload";const x=await req(path,{method:"POST",body:fd});setMsg(kind==="audio"?"Audio transcribed and saved as a source.":"Document uploaded and saved.");if(x.transcript)setSummary("Transcript: "+x.transcript)});e.target.value=""}
 const nav=["Overview","Sources","Entities","Graph","Signals","Verification"];
 return <div className="shell">
  <aside className="side"><div className="brand"><span className="logo">◈</span><div><b>FUSION</b><small>WORKBENCH</small></div></div><div className="nav">{nav.map(n=><button className={tab===n?"active":""} onClick={()=>setTab(n)} key={n}>{({Overview:"▦",Sources:"▤",Entities:"◎",Graph:"⌘",Signals:"⌁",Verification:"✓"})[n]} <span>{n}</span></button>)}</div><div className="sidefoot">ANALYST WORKSPACE<br/><span>Human review enabled</span></div></aside>
  <main className="main"><header><div><div className="eyebrow">MULTILINGUAL OPEN-SOURCE ANALYSIS</div><h1>{tab}</h1></div><div className="status"><i className={health?.sarvam_configured?"on":""}></i>{health?.sarvam_configured?"Sarvam connected":"Sarvam key not set"}</div></header>
  {msg&&<div className="notice">{msg}</div>}
  <div className="disclaimer">DEMO MODE · Process only public or explicitly authorized material. AI outputs are unverified leads, not facts.</div>
  {tab==="Overview"&&<><section className="welcome"><div><div className="eyebrow">INTELLIGENCE FUSION / MVP</div><h2>See connections.<br/><em>Verify the evidence.</em></h2><p>Bring authorized multilingual sources into one reviewable workspace.</p><button className="primary" onClick={()=>setTab("Sources")}>＋ Add intelligence source</button></div><div className="orb">◈<small>FUSION<br/>ENGINE</small></div></section>
   <section className="stats"><Stat label="SOURCE RECORDS" value={docs.length}/><Stat label="ENTITY CANDIDATES" value={entities.length}/><Stat label="RELATION CANDIDATES" value={rels.length}/><Stat label="SIGNALS TO REVIEW" value={signals.length}/></section>
   <div className="grid2"><section className="panel"><PanelTitle title="Recent sources" action="View all" click={()=>setTab("Sources")}/>{docs.slice(0,4).map(d=><div className="sourceRow" key={d.id}><span className="fileIcon">▤</span><div><b>{d.title}</b><small>{d.source_type} · {d.language||"language pending"}</small></div><button onClick={()=>analyze(d.id)}>Analyze</button></div>)}{!docs.length&&<Empty text="No sources yet. Load the fictional demo dataset or add a source."/>}</section><section className="panel"><PanelTitle title="Review queue" action="Open" click={()=>setTab("Verification")}/><div className="bigNum">{entities.filter(x=>x.status==="pending").length+rels.filter(x=>x.status==="pending").length}</div><p className="muted">Candidate items awaiting analyst verification.</p><div className="bar"><i style={{width:`${entities.length?entities.filter(x=>x.status==="approved").length/entities.length*100:0}%`}}/></div><small className="muted">Entity approvals</small></section></div>
  </>}
  {tab==="Sources"&&<><section className="panel"><PanelTitle title="Add a text source"/><form onSubmit={addSource}><label>Source title</label><input value={title} onChange={e=>setTitle(e.target.value)} required/><label>Provenance / source label</label><input value={source} onChange={e=>setSource(e.target.value)}/><label>Article or report text</label><textarea rows="6" value={content} onChange={e=>setContent(e.target.value)} placeholder="Paste a public article, public notice, or authorized report..." required/><button className="primary" disabled={busy}>Save source</button></form><div className="uploadrow"><label className="upload">Upload TXT / MD / PDF<input type="file" accept=".txt,.md,.pdf" onChange={e=>upload(e,"doc")}/></label><label className="upload">Transcribe demo / authorized audio<input type="file" accept=".wav,.mp3,.m4a,.ogg,.flac,.webm" onChange={e=>upload(e,"audio")}/></label></div><button className="secondary" onClick={()=>act(async()=>{const x=await req("/api/demo",{method:"POST"});setMsg(x.message)})}>Load fictional demo dataset</button></section><section className="panel"><PanelTitle title="Source register"/>{docs.map(d=><div className="sourceRow" key={d.id}><span className="fileIcon">▤</span><div><b>{d.title}</b><small>{d.source_label} · {d.language}</small></div><button onClick={()=>analyze(d.id)}>Analyze</button><button className="dangerText" onClick={()=>act(()=>req("/api/documents/"+d.id,{method:"DELETE"}))}>Delete</button></div>)}{!docs.length&&<Empty text="Your source register is empty."/>}</section></>}
  {tab==="Entities"&&<section className="panel"><PanelTitle title="Extracted entity candidates"/><p className="muted">Every item retains its source document and supporting quote. Approve or reject after checking the source.</p><ReviewTable items={entities} kind="entities" review={review}/></section>}
  {tab==="Graph"&&<section className="panel"><PanelTitle title="Cross-source knowledge graph"/><p className="muted">Only candidate links extracted from sources are shown. Node colors: teal pending, green approved, red rejected.</p><Graph data={graph}/><div className="legend">● Pending &nbsp; <span>● Approved</span> &nbsp; <b>● Rejected</b></div></section>}
  {tab==="Signals"&&<section className="panel"><PanelTitle title="Weak-signal review"/><p className="muted">Explainable heuristic: an entity must be approved in at least two distinct source records. Score is a review-priority indicator, not a probability or truth score.</p>{signals.map((s,i)=><div className="signal" key={i}><div className="signalTop"><b>{s.label}</b><strong>{s.score}/100</strong></div><div className="bar"><i style={{width:s.score+"%"}}/></div><p>{s.interpretation}</p><small>Independent source records: {s.source_count}</small>{s.sources?.map(x=><small className="evidence" key={x.id}>▤ {x.title}</small>)}</div>)}{!signals.length&&<Empty text="No repeated approved entities yet. Approve the same explicitly mentioned entity across two independent demo sources to see a signal."/>}</section>}
  {tab==="Verification"&&<><section className="panel"><PanelTitle title="Entity verification"/><p className="muted">AI suggestions remain pending until a human reviews the evidence.</p><ReviewTable items={entities} kind="entities" review={review}/></section><section className="panel"><PanelTitle title="Relationship verification"/><ReviewTable items={rels} kind="relations" review={review}/></section></>}
  {summary&&<section className="panel"><PanelTitle title="Latest AI analysis summary"/><p>{summary}</p></section>}
  <footer>OSINT FUSION WORKBENCH <span>Prototype v0.1 · Evidence first · Human in the loop</span></footer>
  </main></div>
}
function Stat({label,value}){return <div className="stat"><small>{label}</small><b>{value}</b></div>}
function PanelTitle({title,action,click}){return <div className="panelTitle"><h3>{title}</h3>{action&&<button onClick={click}>{action} →</button>}</div>}
function Empty({text}){return <div className="empty">{text}</div>}
function ReviewTable({items,kind,review}){if(!items.length)return <Empty text="No extracted candidates yet. Add a source and run AI analysis."/>;return <div className="reviewList">{items.map(x=><div className="reviewItem" key={x.id}><div className="reviewHead"><b>{kind==="entities"?x.name:`${x.source} → ${x.target}`}</b><span className={"pill "+x.status}>{x.status}</span></div><small>{kind==="entities"?x.entity_type:x.relation} · {x.source_title}</small><blockquote>{x.evidence||"No quote supplied"}</blockquote><div className="actions"><button onClick={()=>review(kind,x.id,"approved")}>✓ Approve</button><button onClick={()=>review(kind,x.id,"rejected")}>✕ Reject</button><button onClick={()=>review(kind,x.id,"pending")}>Reset</button></div></div>)}</div>}
