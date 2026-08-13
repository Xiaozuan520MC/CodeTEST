const LEVEL_ORDER = ["beginner","elementary","intermediate","advanced","expert","practical"];
const LEVEL_NAMES = {beginner:"入门",elementary:"初级",intermediate:"中级",advanced:"高级",expert:"精通",practical:"实战"};
const LANG_NAMES = {python:"Python",c:"C",java:"Java",rust:"Rust",cpp:"C++"};

const state = {user:null,lang:null,level:"beginner",questions:[],current:null,progress:{passed:{},stats:{}}};
const $ = id => document.getElementById(id);

/* 账号 */
let authMode = "login";
function switchAuth(mode) {
  authMode = mode;
  $("tab-login").classList.toggle("active", mode==="login");
  $("tab-register").classList.toggle("active", mode==="register");
  $("auth-confirm").hidden = mode !== "register";
  $("auth-title").textContent = mode==="login" ? "欢迎回来" : "创建账号";
  $("auth-sub").textContent = mode==="login" ? "登录后继续你的挑战" : "注册新账号开始挑战";
  $("auth-submit").textContent = mode==="login" ? "登 录" : "注 册";
  $("auth-msg").textContent = "";
}
async function submitAuth(e) {
  e.preventDefault();
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;
  if (authMode==="register" && password !== $("auth-confirm").value) {
    $("auth-msg").textContent = "密码不一致"; return;
  }
  const res = await fetch(authMode==="login"?"/api/login":"/api/register", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({username,password})
  });
  const data = await res.json();
  if (!res.ok) { $("auth-msg").textContent = data.error || "失败"; return; }
  state.user = data.username;
  enterApp();
}
async function logout() {
  await fetch("/api/logout",{method:"POST"});
  state.user = null;
  $("auth-view").classList.remove("hidden");
  $("main-view").classList.add("hidden");
  switchAuth("login");
}

/* 启动 */
async function init() {
  try {
    const res = await fetch("/api/me");
    const data = await res.json();
    if (data.user) { state.user = data.user.username; enterApp(); }
    else $("auth-view").classList.remove("hidden");
  } catch { $("auth-view").classList.remove("hidden"); }
}
async function enterApp() {
  $("auth-view").classList.add("hidden");
  $("main-view").classList.remove("hidden");
  $("user-name").textContent = state.user;
  await loadProgress();
}
async function loadProgress() {
  const res = await fetch("/api/progress");
  const data = await res.json();
  state.progress = data;
  updateStats();
}
function updateStats() {
  const totals = state.progress.totals || {};
  for (const lang of Object.keys(LANG_NAMES)) {
    const n = state.progress.stats[lang] || 0;
    const t = totals[lang] || 0;
    $("stat-"+lang).textContent = `完成 ${n} / ${t}`;
    $("bar-"+lang).style.width = (t ? n/t*100 : 0)+"%";
  }
}

/* 语言 */
async function enterLang(lang) {
  state.lang = lang; state.level = "beginner"; state.current = null;
  $("quiz-lang-title").textContent = LANG_NAMES[lang];
  $("home-view").classList.add("hidden");
  $("quiz-view").classList.remove("hidden");
  renderLevelTabs(); await loadQuestions();
}
function backHome() {
  $("quiz-view").classList.add("hidden");
  $("home-view").classList.remove("hidden");
}
function renderLevelTabs() {
  const box = $("level-tabs"); box.innerHTML = "";
  for (const lv of LEVEL_ORDER) {
    const b = document.createElement("button");
    b.className = "level-tab" + (lv===state.level?" active":"");
    b.textContent = LEVEL_NAMES[lv];
    b.onclick = () => { state.level = lv; renderLevelTabs(); loadQuestions(); };
    box.appendChild(b);
  }
}

/* 题目列表 */
async function loadQuestions() {
  const res = await fetch(`/api/questions?lang=${state.lang}&level=${state.level}`);
  const data = await res.json();
  state.questions = data.items;
  renderQuestionList();
  if (data.items.length) selectQuestion(data.items[0].id);
}
function renderQuestionList() {
  const box = $("q-list"); box.innerHTML = "";
  for (const q of state.questions) {
    const div = document.createElement("div");
    const num = q.id.split("-")[1];
    const passed = !!state.progress.passed[q.id];
    div.className = "q-item" + (q.id===state.current?" active":"");
    div.innerHTML = `<span class="num">${num}</span><span>${q.title}</span><span class="dot ${passed?"passed":""}"></span>`;
    div.onclick = () => selectQuestion(q.id);
    box.appendChild(div);
  }
}

/* 题目详情 */
async function selectQuestion(qid) {
  state.current = qid; renderQuestionList();
  const res = await fetch("/api/questions/"+qid);
  const q = await res.json();
  $("q-title").textContent = `#${qid.split("-")[1]} ${q.title}`;
  $("q-meta").innerHTML = `<span class="tag">${q.lang_name}</span><span class="tag">${q.level_name}</span>` +
    (q.stdin ? `<span class="tag">输入: ${q.stdin.replace(/\n/g,"↵")}</span>` : "");
  $("q-desc").textContent = q.desc;
  $("editor-lang-name").textContent = fileName(q.lang);
  $("editor").value = loadDraft(qid) ?? starter(q.lang);
  updateLines();
  $("result").classList.add("hidden");
}
function fileName(l) { return {python:"main.py",c:"main.c",java:"Main.java",rust:"main.rs",cpp:"main.cpp"}[l]; }
function starter(l) {
  if (l==="java") return "public class Main {\n    public static void main(String[] args) {\n        \n    }\n}";
  if (l==="rust") return "fn main() {\n    \n}";
  if (l==="c") return "#include <stdio.h>\nint main() {\n    return 0;\n}";
  if (l==="cpp") return "#include <iostream>\nint main() {\n    return 0;\n}";
  return "";
}
function loadDraft(qid) { try { return localStorage.getItem("draft:"+state.user+":"+qid); } catch { return null; } }

/* 行号 */
function updateLines() {
  const n = $("editor").value.split("\n").length;
  $("editor-lines").innerHTML = Array.from({length:Math.max(n,8)},(_,i)=>i+1).join("\n");
}
$("editor").addEventListener("input", updateLines);

/* 评测 */
async function submitCode() {
  const code = $("editor").value;
  if (!code.trim()) return;
  const btn = $("judge-btn");
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 评测中';
  $("result").classList.add("hidden");
  try {
    localStorage.setItem("draft:"+state.user+":"+state.current, code);
    const res = await fetch("/api/judge", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({question_id:state.current, code})
    });
    const data = await res.json();
    if (res.status===401) { location.reload(); return; }
    if (!res.ok) { alert(data.error || "失败"); return; }
    showResult(data);
    if (data.passed) {
      state.progress.passed[state.current] = true;
      await loadProgress(); renderQuestionList();
    }
  } catch { alert("网络错误"); }
  finally { btn.disabled=false; btn.textContent = "提交评测"; }
}
function showResult(data) {
  const box = $("result");
  box.classList.remove("hidden","pass","fail");
  if (data.error) {
    box.classList.add("fail");
    box.innerHTML = `<div class="r-head">✗ 错误</div><div class="r-label">信息</div><pre></pre>`;
    box.querySelector("pre").textContent = data.error;
    return;
  }
  if (data.passed) {
    box.classList.add("pass");
    box.innerHTML = `<div class="r-head">✓ 通过</div><div class="r-label">输出</div><pre></pre><div class="r-label">解析</div><pre></pre>`;
    const p = box.querySelectorAll("pre");
    p[0].textContent = data.output.trimEnd(); p[1].textContent = data.explain||"";
  } else {
    box.classList.add("fail");
    box.innerHTML = `<div class="r-head">✗ 未通过</div><div class="r-label">你的输出</div><pre></pre><div class="r-label">期望输出</div><pre></pre>`;
    const p = box.querySelectorAll("pre");
    p[0].textContent = data.output.trimEnd(); p[1].textContent = data.expected.trimEnd();
  }
  box.scrollIntoView({behavior:"smooth",block:"nearest"});
}

/* 编辑器 */
$("editor").addEventListener("keydown", e => {
  if (e.key==="Tab") {
    e.preventDefault();
    const el = e.target, s = el.selectionStart, en = el.selectionEnd;
    el.value = el.value.slice(0,s)+"    "+el.value.slice(en);
    el.selectionStart = el.selectionEnd = s+4; updateLines();
  }
  if ((e.ctrlKey||e.metaKey) && e.key==="Enter") submitCode();
});
$("editor").addEventListener("scroll", () => { $("editor-lines").scrollTop = $("editor").scrollTop; });

init();
