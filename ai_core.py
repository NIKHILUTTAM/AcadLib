import os, sys, re, uuid, json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from models import DatasetStack, DatasetEntry, ResultMeta, ExecutionReport, WorkflowStep
from database import QueryLibrary, AuditLog

class ConversationMemory:
    MAX_TURNS = 60; COMPRESS_AT = 20
    def __init__(self): self._turns = []; self._summaries = []; self._workflow_history = []
    def add_turn(self, role: str, content: str, action_type: str = ""):
        self._turns.append({"role": role, "content": content, "action_type": action_type, "ts": datetime.now().isoformat()})
        if len(self._turns) >= self.COMPRESS_AT and len(self._turns) % self.COMPRESS_AT == 0: self._compress()
        if len(self._turns) > self.MAX_TURNS: self._turns = self._turns[-self.MAX_TURNS:]
    def _compress(self):
        window = self._turns[-self.COMPRESS_AT:]; actions = [t["action_type"] for t in window if t.get("action_type")]; queries = [t["content"][:55] for t in window if t["role"] == "user"]
        self._summaries.append(f"[{len(queries)} queries: {', '.join(queries[:3])}{'…' if len(queries) > 3 else ''}; actions: {', '.join(dict.fromkeys(actions))}]")
    def add_workflow(self, workflow_id: str, steps: list, success: bool):
        self._workflow_history.append({"workflow_id": workflow_id, "steps": [getattr(s, "action", str(s)) for s in steps], "success": success, "ts": datetime.now().isoformat()})
        if len(self._workflow_history) > 100: self._workflow_history = self._workflow_history[-100:]
    def recent_context(self, n: int = 6) -> str:
        parts = [f"Summary: {self._summaries[-1]}"] if self._summaries else []
        for t in self._turns[-n:]: parts.append(f"{t['role']}: {t['content'][:80]}")
        return "\n".join(parts)
    def workflow_success_rate(self) -> float:
        if not self._workflow_history: return 1.0
        return round(sum(1 for w in self._workflow_history if w["success"]) / len(self._workflow_history), 3)
    def clear(self): self._turns = []; self._summaries = []; self._workflow_history = []

class WorkflowStateManager:
    def __init__(self): self._s = {}; self._ds_stack = DatasetStack(); self._current_workflow_id = ""; self.reset()
    def reset(self):
        self._s = {"current_workspace": "", "last_report": "", "last_student": "", "last_query_type": "", "last_result_type": "", "last_semester": None, "execution_steps": [], "active_filters": {}, "route_used": "", "verification_status": {}, "last_exportable_dataset": [], "last_report_name": "Report", "report_origin": ""}
        self._ds_stack.clear(); self._current_workflow_id = str(uuid.uuid4())[:8]
    def set(self, **kw): self._s.update(kw)
    def get(self, k, d=None): return self._s.get(k, d)
    @property
    def last_name(self) -> str: return self._s.get("last_student", "")
    @last_name.setter
    def last_name(self, v: str): self._s["last_student"] = v
    @property
    def last_sem(self): return self._s.get("last_semester")
    @last_sem.setter
    def last_sem(self, v): self._s["last_semester"] = v
    @property
    def last_rows(self) -> list: return self._ds_stack.get_rows()
    @last_rows.setter
    def last_rows(self, v: list):
        if v: self._ds_stack.push(v, source_query="(direct set)", action_type=self._s.get("last_query_type", "unknown"), workflow_id=self._current_workflow_id)
    @property
    def dataset_stack(self) -> DatasetStack: return self._ds_stack
    def record_action(self, action_type: str, rows: list, workspace: str = "", semester=None, report_name: str = "", source_query: str = ""):
        self._s["last_query_type"] = action_type; self._s["current_workspace"] = workspace
        if semester is not None: self._s["last_semester"] = semester
        
        aggregate_actions = {"all_students", "fail_report", "semester_stats", "branch_stats", "cgpa_rankings"}
        if action_type in aggregate_actions or action_type == "student_search":
            self._ds_stack.clear()
            self._current_workflow_id = str(uuid.uuid4())[:8]
            
        if action_type not in aggregate_actions and rows:
            n = rows[0].get("name") or rows[0].get("student_name")
            if n: self._s["last_student"] = n
            
        self._ds_stack.push(rows, source_query=source_query or action_type, action_type=action_type, workflow_id=self._current_workflow_id, label=report_name or action_type.replace("_", " ").title())
        if action_type in {"query_topper","cgpa_rankings","fail_report","student_search","semester_stats","branch_stats","grade_distribution","subject_detail", "convert_scale", "adjust_marks"} and rows:
            self._s["last_exportable_dataset"] = rows; self._s["last_report_name"] = report_name or action_type.replace("_"," ").title(); self._s["report_origin"] = action_type
        self._s["execution_steps"].append({"action": action_type, "rows": len(rows), "workspace": workspace, "ts": datetime.now().isoformat()})
        if len(self._s["execution_steps"]) > 30: self._s["execution_steps"] = self._s["execution_steps"][-30:]
    def new_workflow(self): self._current_workflow_id = str(uuid.uuid4())[:8]; return self._current_workflow_id
    def clear(self): self.reset()
    def summary(self) -> str:
        parts = []
        if self._s.get("last_student"): parts.append(f'student="{self._s["last_student"]}"')
        if self._s.get("last_semester"): parts.append(f'sem={self._s["last_semester"]}')
        if self._s.get("last_query_type"): parts.append(f'last={self._s["last_query_type"]}')
        chain = self._ds_stack.provenance_chain()
        if chain and chain != "empty": parts.append(f'chain={chain}')
        return ", ".join(parts) or "empty"

class ContextResolver:
    _PRONOUNS = re.compile(r'\b(their|them|him|her|his|those|these|it|that|this\s+report|previous\s+result|last\s+result|previous\s+data|those\s+students|these\s+students)\b', re.IGNORECASE)
    def has_pronoun(self, query: str) -> bool: return bool(self._PRONOUNS.search(query))
    def resolve_dataset(self, query: str, state: WorkflowStateManager) -> Optional[list]: return state.last_rows if self.has_pronoun(query) and state.last_rows else None
    def resolve_name(self, query: str, state: WorkflowStateManager, explicit: str = None) -> str:
        if re.search(r'\b(all|every)\s+student', query, re.IGNORECASE):
            if state: state.last_name = ""
            return ""
        return explicit or (state.last_name if state else "")
    def resolve_semester(self, query: str, state: WorkflowStateManager, explicit=None): return explicit or (state.last_sem if state else None)
    def detect_conversion(self, query: str) -> Optional[dict]:
        ql = query.lower()
        if "percentage" in ql or "percent" in ql: return {"type": "percentage"}
        m = re.search(r'(?:scale\s+(?:of\s+)?|gpa\s*|point\s*)(\d+(?:\.\d+)?)', ql)
        if m: return {"type": "scale", "target_scale": float(m.group(1))}
        m2 = re.search(r'(?:to|into)\s+(\d+(?:\.\d+)?)', ql)
        if m2:
            scale = float(m2.group(1))
            if 2 <= scale <= 10: return {"type": "scale", "target_scale": scale}
        return None
    def identify_source_field(self, rows: list) -> Optional[str]:
        if not rows: return None
        for key in ["sgpa", "cgpa", "avg_sgpa", "total_marks_obtained", "gpa_4"]:
            if key in rows[0] and rows[0][key] is not None: return key
        for k, v in rows[0].items():
            if isinstance(v, (int, float)) and v is not None: return k
        return None

class CalculationEngine:
    @staticmethod
    def convert_10_to_4(val: float) -> Optional[float]: return round(float(val) / 10.0 * 4.0, 3) if val is not None else None
    @staticmethod
    def convert_10_to_5(val: float) -> Optional[float]: return round(float(val) / 10.0 * 5.0, 3) if val is not None else None
    @staticmethod
    def convert_to_scale(val: float, target_scale: float, source_scale: float = 10.0) -> Optional[float]: return round(float(val) / source_scale * target_scale, 3) if val is not None else None
    @staticmethod
    def to_percentage(val: float, source_scale: float = 10.0) -> Optional[float]: return round(float(val) * (100.0 / source_scale), 2) if val is not None else None
    @staticmethod
    def convert_rows(rows: list, source_key: str, conversion: str = "scale4", target_scale: float = 4.0) -> list:
        out = []
        for r in rows:
            row = dict(r); val = row.get(source_key)
            if val is not None:
                try:
                    fv = float(val)
                    if conversion == "scale4":   row["gpa_4"]      = CalculationEngine.convert_10_to_4(fv)
                    elif conversion == "scale5": row["gpa_5"]      = CalculationEngine.convert_10_to_5(fv)
                    elif conversion == "percentage": row["percentage"] = CalculationEngine.to_percentage(fv)
                    else: row["converted"] = CalculationEngine.convert_to_scale(fv, target_scale)
                except: pass
            out.append(row)
        return out
    @staticmethod
    def calculate_average(rows: list, key: str) -> float:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    @staticmethod
    def calculate_median(rows: list, key: str) -> float:
        vals = sorted(float(r[key]) for r in rows if r.get(key) is not None)
        n = len(vals); return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 3) if n else 0.0
    @staticmethod
    def adjust_marks(rows: list, amount: float, source_key: str) -> list:
        out = []
        for r in rows:
            row = dict(r); val = row.get(source_key)
            if val is not None:
                try: row[source_key] = round(float(val) + amount, 3)
                except: pass
            out.append(row)
        return out

class VerificationEngine:
    WEIGHTS = {"rows_fetched": 0.25, "rows_rendered": 0.20, "calculation_ok": 0.20, "route_ok": 0.20, "context_ok": 0.15}
    def verify(self, rows: list, expected_count: int = None, rows_rendered: int = None, check_order_key: str = None, descending: bool = True, context_resolved: bool = True, route_ok: bool = True, calculation_ok: bool = True) -> dict:
        result = {"passed": True, "checks": [], "issues": [], "scores": {}, "confidence": 0.0}; scores = {}; actual = len(rows)
        
        scores["sql_ok"] = 1.0 if actual >= 0 else 0.0 
        
        if actual == 0:
            scores["rows_fetched"] = 0.0
            result["passed"] = False
            result["issues"].append("Query executed but returned 0 rows.")
            result["checks"].append("✗ rows_fetched: 0")
        else:
            scores["rows_fetched"] = 1.0
            result["checks"].append(f"✓ rows_fetched: {actual}")

        rendered = rows_rendered if rows_rendered is not None else actual
        if actual == 0: scores["rows_rendered"] = 1.0; result["checks"].append("✓ rows_rendered: n/a (0 rows)")
        elif rendered >= actual: scores["rows_rendered"] = 1.0; result["checks"].append(f"✓ rows_rendered: {rendered}/{actual}")
        elif rendered == 0: scores["rows_rendered"] = 0.0; result["issues"].append(f"✗ rows_rendered: 0 of {actual} rows"); result["checks"].append(f"✗ rows_rendered: 0/{actual}"); result["passed"] = False
        else: ratio = rendered / actual; scores["rows_rendered"] = ratio; result["issues"].append(f"⚠ rows_rendered: {rendered}/{actual}"); result["checks"].append(f"⚠ rows_rendered: {rendered}/{actual}")
        
        if check_order_key and rows and len(rows) > 1:
            vals = []
            for r in rows:
                v = r.get(check_order_key)
                if v is not None:
                    try: vals.append(float(v))
                    except: pass
            if len(vals) > 1:
                ordered = vals == sorted(vals, reverse=descending)
                if ordered: result["checks"].append(f"✓ order: {check_order_key} {'DESC' if descending else 'ASC'}")
                else: result["issues"].append(f"⚠ order drift on {check_order_key}")
                
        scores["calculation_ok"] = 1.0 if calculation_ok else 0.0; result["checks"].append(f"{'✓' if calculation_ok else '✗'} calculation")
        scores["route_ok"] = 1.0 if route_ok else 0.0; result["checks"].append(f"{'✓' if route_ok else '✗'} route")
        scores["context_ok"] = 1.0 if context_resolved else 0.0; result["checks"].append(f"{'✓' if context_resolved else '⚠'} context_resolved")
        
        data_multiplier = 1.0 if actual > 0 else 0.4 
        confidence = (
            (self.WEIGHTS["rows_fetched"] * scores["rows_fetched"]) +
            (self.WEIGHTS["route_ok"] * (1.0 if route_ok else 0.0) * data_multiplier) +
            (self.WEIGHTS["context_ok"] * (1.0 if context_resolved else 0.0) * data_multiplier) +
            (self.WEIGHTS["calculation_ok"] * (1.0 if calculation_ok else 0.0))
        )
        
        result["scores"] = scores
        result["confidence"] = round(min(max(confidence, 0.0), 1.0), 3)
        return result

class SchemaValidator:
    _MISSING_DOMAINS = {r'\b(placement|placed|placed\s+in|job\s+offer|offer\s+letter)\b': "Placement data is not available.", r'\b(attendance|present|absent|leaves)\b': "Attendance data is not available.", r'\b(internship|intern)\b': "Internship records are not available.", r'\b(salary|package|lpa|ctc)\b': "Salary data is not available.", r'\b(hostel|fee|fees|tuition)\b': "Fee data is not available."}
    _COMPANY_NAMES = re.compile(r'\b(google|amazon|microsoft|wipro|infosys|tcs|accenture|ibm|oracle|flipkart|swiggy|zomato|meta|apple|netflix|uber|ola)\b', re.IGNORECASE)
    def validate(self, query: str, qlib: Optional[QueryLibrary] = None) -> Optional[str]:
        ql = query.lower()
        for pattern, message in self._MISSING_DOMAINS.items():
            if re.search(pattern, ql, re.IGNORECASE): return message
        if self._COMPANY_NAMES.search(query) and re.search(r'\b(placed|placement|got|hired|selected|job|offer)\b', ql): return "Placement data is not available."
        return None

class AmbiguityDetector:
    _AMBIGUOUS = [(re.compile(r'\b(?:best|top)\s+(?:student|performer|scorer)\b(?!\s+(?:in|of|by)\s+(?:cgpa|sgpa|semester\s*\d|sem\s*\d))', re.IGNORECASE), "How would you like to rank the best student?", ["By CGPA", "By SGPA", "By improvement", "By fewest fails"]), (re.compile(r'\btop\s+(?:student|performer)\b(?!\s+(?:in|of|by|semester|sem|\d))', re.IGNORECASE), "Top student by which metric?", ["By CGPA", "By SGPA", "By total marks"]), (re.compile(r'\b(?:show|get|list|find)\s+(?:all\s+)?(?:good|excellent|average|poor)\s+students?\b', re.IGNORECASE), "What threshold defines 'good'/'poor'?", ["CGPA ≥ 8.0", "CGPA 6.5–8.0", "CGPA < 6.0"]), (re.compile(r'\b(?:compare|comparison)\b(?!.{0,30}(?:semester|sem|branch|year))', re.IGNORECASE), "What would you like to compare?", ["Two semesters", "Branches", "Pass vs fail rates"])]
    def check(self, query: str) -> Optional[dict]:
        for pattern, question, choices in self._AMBIGUOUS:
            if pattern.search(query): return {"question": question, "choices": choices, "original_query": query}
        return None

class WorkspaceRouter:
    CHAT_MAX = 10; MINI_MAX = 50
    def pre_route(self, action_type: str, params: dict = None) -> str:
        if action_type == "student_profile": return "student_profile"
        if action_type in ("show_chart", "grade_distribution"): return "chart"
        if action_type.startswith("export"): return "export_preview"
        if action_type in ("cgpa_rankings", "query_topper", "branch_stats", "semester_stats", "fail_report", "adjust_marks"): return "analytics"
        return "result_table"
    def route(self, rows: list, action_type: str, meta) -> dict:
        if action_type == "student_profile": return {"strategy": "profile_workspace", "show_chat": True, "show_workspace": True, "ws_key": "student_profile"}
        if action_type in ("show_chart", "grade_distribution"): return {"strategy": "chart_workspace", "show_chat": True, "show_workspace": True, "ws_key": "chart"}
        if action_type in ("export_excel", "export_csv", "export_pdf"): return {"strategy": "export_workspace", "show_chat": True, "show_workspace": True, "ws_key": "export_preview"}
        if action_type == "query_topper" and len(rows) == 1: return {"strategy": "profile_workspace", "show_chat": True, "show_workspace": True, "ws_key": "student_profile"}
        ws_key = self.pre_route(action_type); n = len(rows)
        if n <= self.CHAT_MAX: return {"strategy": "chat_inline", "show_chat": True, "show_workspace": False, "ws_key": ws_key}
        elif n <= self.MINI_MAX: return {"strategy": "chat_plus_workspace", "show_chat": True, "show_workspace": True, "ws_key": ws_key}
        else: meta.token_overflow = True; return {"strategy": "workspace_only", "show_chat": False, "show_workspace": True, "ws_key": ws_key}
    def format_inline(self, rows: list, key_fields: list = None) -> str:
        if not rows: return "No results."
        fields = key_fields or list(rows[0].keys())[:4]; lines = []
        for i, r in enumerate(rows[:10], 1): lines.append(f"  {i}. " + "  |  ".join([f"{k}: {r.get(k, '—')}" for k in fields if k in r]))
        return "\n".join(lines)

class ActionExecutor:
    SAFE_ACTIONS = {"query_topper","fail_report","student_search","student_profile","semester_stats","cgpa_rankings","show_chart","branch_stats","grade_distribution","export_excel","export_csv","export_pdf","open_workspace","close_workspace","subject_detail","convert_scale","adjust_marks","all_students"}
    def __init__(self, state_mgr: WorkflowStateManager): self.state_mgr = state_mgr
    @property
    def context(self) -> WorkflowStateManager: return self.state_mgr
    def execute(self, actions: list, qlib, ws_mgr, state, after_fn, chat_cb, steps: list = None):
        if not qlib: chat_cb("error", "❌ Database not ready."); return None
        step_map = {s.action: s for s in steps if s.action not in ("__verify__", "__render__")} if steps else {}
        for action in actions:
            if action.get("type") == "student_search":
                if action.get("params", {}).get("name", "").lower() in ("all", "students", "all students", "every", "everyone"):
                    action["type"] = "all_students"; action["params"] = {}
        summary = []
        for action in actions:
            atype = action.get("type", ""); params = action.get("params", {})
            if atype not in self.SAFE_ACTIONS: chat_cb("error", f"⚠️ Unknown action '{atype}'"); continue
            step = step_map.get(atype)
            if step: step.status = "running"
            try:
                r = self._dispatch(atype, params, qlib, ws_mgr, state, after_fn)
                if step: step.status = "done"
                if r: summary.append(r)
            except Exception as e:
                if step: step.status = "failed"; step.error = str(e)[:80]
                chat_cb("error", f"❌ {atype}: {e}")
        if steps:
            for s in steps:
                if s.action in ("__verify__", "__render__") and s.status == "pending": s.status = "done"
        return "\n".join(summary) if summary else None
    def _dispatch(self, atype, params, qlib, ws_mgr, state, after_fn):
        M = {"query_topper": self._topper, "fail_report": self._fails, "student_search": self._search, "student_profile": self._profile, "semester_stats": self._sem_stats, "cgpa_rankings": self._cgpa, "show_chart": self._chart, "branch_stats": self._branch, "grade_distribution": self._grades, "export_excel": self._export, "export_csv": self._export, "export_pdf": self._export, "open_workspace": self._open_ws, "close_workspace": self._close_ws, "subject_detail": self._subject_detail, "convert_scale": self._convert_scale, "adjust_marks": self._adjust_marks, "all_students": self._all_students}
        return M[atype](params, qlib, ws_mgr, state, after_fn, atype)
    def _topper(self, p, q, w, s, af, _):
        sem = p.get("semester"); limit = p.get("limit"); rows = q.rank_students_by_sgpa(int(sem), limit=limit) if sem else q.rank_students_by_cgpa(limit=limit)
        if p.get("convert_gpa4"): rows = CalculationEngine.convert_rows(rows, "cgpa" if not sem else "sgpa", "scale4")
        title = f"🏆 Top Rankings — Semester {sem}" if sem else "🏆 CGPA Rankings"; yk = "sgpa" if sem else "cgpa"
        self.state_mgr.record_action("query_topper", rows, "analytics", semester=sem, report_name=title)
        af(0, lambda: w.open("analytics", {"rows": rows, "x_key": "name", "y_key": yk, "subtitle": f"{len(rows)} students"}, s, title=title))
        return f"🏆 Topper: {rows[0].get('name')} — {'SGPA' if sem else 'CGPA'}: {rows[0].get(yk)}" if rows else "No topper data found."
    def _fails(self, p, q, w, s, af, _):
        sem = p.get("semester"); rows = q.get_fail_report_semester(int(sem)) if sem else q.get_fail_report()
        title = f"❌ Fail Report — Semester {sem}" if sem else "❌ Overall Fail Report"; yk = "failed_count" if sem else "failed_subjects"
        self.state_mgr.record_action("fail_report", rows, "analytics", semester=sem, report_name=title)
        af(0, lambda: w.open("analytics", {"rows": rows, "x_key": "name", "y_key": yk, "subtitle": f"{len(rows)} students"}, s, title=title))
        return f"Found {len(rows)} student(s) with fails."
    def _all_students(self, p, q, w, s, af, _):
        limit = p.get("limit")
        try: rows = q.list_all_students_full()
        except: rows = q._run("SELECT name, roll_number, branch, cgpa, semesters_completed FROM students ORDER BY cgpa DESC NULLS LAST")
        if limit: rows = rows[:int(limit)]
        title = f"👥 All Students ({len(rows)} of {q.count_total('students')})"
        self.state_mgr.record_action("all_students", rows, "result_table", report_name=title)
        af(0, lambda: w.open("result_table", {"rows": rows}, s, title=title))
        return f"Showing {len(rows)} students."
    def _search(self, p, q, w, s, af, _):
        name = p.get("name") or self.state_mgr.last_name
        if not name: return "No student name."
        rows = q.find_student(name)
        if len(rows) > 1 and len(rows) <= 5:
            names = [r.get("name") for r in rows]
            return f"Found multiple matches for '{name}': {', '.join(names)}. Please provide a more specific name."
        elif len(rows) == 0:
            return f"Could not find any student matching '{name}'."
        self.state_mgr.record_action("student_search", rows, "result_table", report_name=f"Search: {name}")
        af(0, lambda: w.open("result_table", {"rows": rows}, s, title=f"🔍 Search: {name}"))
        return f"Found matching record for {rows[0].get('name')}."
    def _profile(self, p, q, w, s, af, _):
        name = p.get("name") or self.state_mgr.last_name
        if not name: return "No student name."
        self.state_mgr.last_name = name; af(0, lambda: w.open("student_profile", {"name": name}, s, title=f"👤 Profile: {name}"))
        return f"Opening full profile for {name}."
    def _sem_stats(self, p, q, w, s, af, _):
        rows = q.all_semester_stats(); self.state_mgr.record_action("semester_stats", rows, "analytics", report_name="Semester Statistics")
        af(0, lambda: w.open("analytics", {"rows": rows, "x_key": "semester_number", "y_key": "avg_sgpa", "subtitle": f"{len(rows)} semesters"}, s, title="📊 Semester Statistics"))
        return f"Showing statistics for {len(rows)} semesters."
    def _cgpa(self, p, q, w, s, af, _):
        rows = q.rank_students_by_cgpa(limit=p.get("limit")); 
        if p.get("convert_gpa4"): rows = CalculationEngine.convert_rows(rows, "cgpa", "scale4")
        self.state_mgr.record_action("cgpa_rankings", rows, "analytics", report_name="🎓 CGPA Rankings")
        af(0, lambda: w.open("analytics", {"rows": rows, "x_key": "name", "y_key": "cgpa", "subtitle": f"{len(rows)} students"}, s, title="🎓 CGPA Rankings"))
        return f"Showing CGPA rankings for {len(rows)} students."
    def _chart(self, p, q, w, s, af, _):
        ct = p.get("chart_type","sgpa_trend"); sem = p.get("semester") or self.state_mgr.last_sem
        titles = {"sgpa_trend":"📈 SGPA Trend","grade_dist":"📊 Grade Distribution", "fail_bar":"📉 Fail Analysis","branch_cgpa":"🏫 Branch CGPA"}
        af(0, lambda: w.open("chart", {"chart_type": ct, "semester": sem}, s, title=titles.get(ct,"Chart")))
        return f"Rendering {ct.replace('_',' ')} chart."
    def _branch(self, p, q, w, s, af, _):
        rows = q.branch_stats(); self.state_mgr.record_action("branch_stats", rows, "analytics", report_name="Branch Statistics")
        af(0, lambda: w.open("analytics", {"rows": rows, "x_key": "branch", "y_key": "avg_cgpa", "subtitle": f"{len(rows)} branches"}, s, title="🏫 Branch Statistics"))
        return f"Showing statistics for {len(rows)} branches."
    def _grades(self, p, q, w, s, af, _):
        sem = p.get("semester") or self.state_mgr.last_sem
        af(0, lambda: w.open("chart", {"chart_type":"grade_dist","semester":sem}, s, title=f"📊 Grade Distribution{' Sem '+str(sem) if sem else ''}"))
        return "Showing grade distribution."
    def _export(self, p, q, w, s, af, atype):
        rows = w._current.rows if hasattr(w, "_current") and hasattr(w._current, "rows") else []
        if not rows: return "❌ No active data table to export."
        fmt = atype.replace("export_","")
        origin = self.state_mgr.get("report_origin",""); report_name = self.state_mgr.get("last_report_name","Report")
        subtitle = f"From: {origin.replace('_',' ').title()} — {report_name}" if origin else report_name
        af(0, lambda: w.open("export_preview", {"rows": rows, "fmt": fmt}, s, title=f"📦 Export: {subtitle} ({fmt.upper()})"))
        return f"Ready to export {len(rows)} rows as {fmt.upper()}."
    def _open_ws(self, p, q, w, s, af, _):
        key = p.get("workspace","result_table"); af(0, lambda: w.open(key, p.get("data") or {"rows": self.state_mgr.last_rows}, s, title=p.get("title", key.replace("_"," ").title())))
        return None
    def _close_ws(self, p, q, w, s, af, _): af(0, lambda: w.close()); return None
    def _subject_detail(self, p, q, w, s, af, _):
        name = p.get("name") or self.state_mgr.last_name; sem = p.get("semester") or self.state_mgr.last_sem
        if not name: return "No student name."
        rows = q.get_student_subjects(name, int(sem)) if sem else q._run("SELECT sm.semester_number,sub.subject_code,sub.subject_name,sub.grade,sub.total_marks FROM students st JOIN semesters sm ON st.id=sm.student_id JOIN subjects sub ON sm.id=sub.semester_id WHERE st.name LIKE ? ORDER BY sm.semester_number,sub.subject_code", (f"%{name}%",))
        self.state_mgr.record_action("subject_detail", rows, "result_table", report_name=f"Subjects: {name}")
        af(0, lambda: w.open("result_table", {"rows": rows}, s, title=f"📚 Subjects — {name}"))
        return f"{len(rows)} subject record(s) for {name}."
    def _convert_scale(self, p, q, w, s, af, _):
        rows = p.get("rows") or self.state_mgr.last_rows; source_key = p.get("source_key", "sgpa"); conversion = p.get("conversion", "scale5"); target = float(p.get("target_scale", 5.0))
        if not rows: return "❌ No dataset to convert."
        ALLOWED_NUMERIC_FIELDS = {"sgpa", "cgpa", "avg_sgpa", "avg_cgpa", "gpa_4", "gpa_5", "total_marks_obtained"}
        if source_key not in ALLOWED_NUMERIC_FIELDS and source_key not in rows[0]:
            detected = ContextResolver().identify_source_field(rows)
            if detected and detected in ALLOWED_NUMERIC_FIELDS: source_key = detected
            else: return f"❌ Conversion aborted: Dataset lacks a valid academic numeric field (like SGPA or CGPA)."
        converted = CalculationEngine.convert_rows(rows, source_key, conversion, target)
        title = f"🔢 Scale Conversion ({source_key})"
        self.state_mgr.record_action("convert_scale", converted, "result_table", report_name=title)
        self.state_mgr.set(last_exportable_dataset=converted, last_report_name=title, report_origin="convert_scale")
        af(0, lambda: w.open("result_table", {"rows": converted}, s, title=title))
        return f"Converted {len(converted)} rows."
    def _adjust_marks(self, p, q, w, s, af, _):
        rows = p.get("rows") or self.state_mgr.last_rows; amount = float(p.get("amount", 0)); source_key = p.get("source_key", "total_marks_obtained")
        if not rows: return "❌ No dataset to adjust."
        adjusted = CalculationEngine.adjust_marks(rows, amount, source_key)
        title = f"➕ Adjusted {source_key} (+{amount})"
        self.state_mgr.record_action("adjust_marks", adjusted, "result_table", report_name=title)
        self.state_mgr.set(last_exportable_dataset=adjusted, last_report_name=title, report_origin="adjust_marks")
        af(0, lambda: w.open("result_table", {"rows": adjusted}, s, title=title))
        return f"Added {amount} to {source_key} for {len(rows)} students."

class AIPlanner:
    SYSTEM_PROMPT = """You are an AI planner for AcadLib. Convert user's question into JSON plan. RESPOND ONLY with JSON: {"message":"<short>","actions":[{"type":"<action>","params":{...}}]}
ACTIONS: query_topper {"semester":N, "limit":N}, fail_report {"semester":N}, all_students {"limit":N}, student_search {"name":"..."}, student_profile {"name":"..."}, semester_stats {}, cgpa_rankings {"limit":N}, show_chart {"chart_type":"sgpa_trend|grade_dist|fail_bar|branch_cgpa","semester":N}, branch_stats {}, grade_distribution {"semester":N}, export_excel {}, export_csv {}, close_workspace {}, convert_scale {"source_key":"sgpa|cgpa","conversion":"scale4|scale5|percentage","target_scale":N}, adjust_marks {"amount":N, "source_key":"sgpa|cgpa|total_marks_obtained"}"""
    def __init__(self, openai_key: str = "", model: str = "gpt-4o-mini"): self.openai_key = openai_key; self.model = model
    def plan(self, question: str, context: dict = None, state_mgr: WorkflowStateManager = None) -> dict:
        ctx = ""
        if context and context.get("last_name"): ctx += f' Last student: "{context["last_name"]}".'
        if context and context.get("last_sem"):  ctx += f' Last semester: {context["last_sem"]}.'
        if self.openai_key:
            try: return self._call_openai(question, ctx)
            except Exception: pass
        return self._rule_based(question, state_mgr=state_mgr)
    def _call_openai(self, question: str, ctx: str) -> dict:
        import openai; client = openai.OpenAI(api_key=self.openai_key)
        resp = client.chat.completions.create(model=self.model, temperature=0, max_tokens=400, messages=[{"role":"system","content":self.SYSTEM_PROMPT+(f"\nCONTEXT:{ctx}" if ctx else "")}, {"role":"user",  "content":question}])
        raw = resp.choices[0].message.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    def _rule_based(self, q: str, state_mgr: WorkflowStateManager = None) -> dict:
        ql = q.lower(); resolver = ContextResolver()
        def sem_num():
            m = re.search(r'\bsem(?:ester)?\s*(\d)\b', q, re.IGNORECASE) or re.search(r'\b([1-8])\b', q)
            return int(m.group(1)) if m else None
        def student_name():
            for pat in [r'(?:student|find|search|lookup|show|profile|detail|record|transcript|for|of)\s+(?:student\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})', r"([A-Za-z]+(?:\s+[A-Za-z]+)+)'s", r'(?:of|for|profile|detail|record)\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,3})']:
                m = re.search(pat, q, re.IGNORECASE)
                if m and m.group(1).strip().lower() not in ("student","students","all","the","me","semester","results","performance","report"): return m.group(1).strip()
            return None
        m_add = re.search(r'\badd\s+(\d+(?:\.\d+)?)\s*(?:more\s+)?(?:marks|points?)', ql)
        if m_add:
            amt = float(m_add.group(1)); source_key = resolver.identify_source_field(state_mgr.last_rows if state_mgr else []) or "total_marks_obtained"
            actions = [{"type": "adjust_marks", "params": {"amount": amt, "source_key": source_key}}]
            msg = f"Adding {amt} to {source_key}."
            conversion = resolver.detect_conversion(ql)
            if conversion:
                target = conversion.get("target_scale", 4.0); conv_str = "scale4" if abs(target-4) < 0.1 else "scale5" if abs(target-5) < 0.1 else "percentage"
                actions.append({"type": "convert_scale", "params": {"source_key": source_key, "conversion": conv_str, "target_scale": target}}); msg += f" Then converting to scale {target}."
            return {"message": msg, "actions": actions}
        if resolver.has_pronoun(q):
            conversion = resolver.detect_conversion(q); prev_rows = state_mgr.last_rows if state_mgr else []
            if conversion and prev_rows:
                source_key = resolver.identify_source_field(prev_rows) or "sgpa"
                target = conversion.get("target_scale", 5.0) if conversion["type"] != "percentage" else 100.0
                conv_str = "percentage" if conversion["type"] == "percentage" else ("scale4" if abs(target-4) < 0.1 else "scale5")
                return {"message": f"Converting {source_key}.", "actions": [{"type": "convert_scale", "params": { "source_key": source_key, "conversion": conv_str, "target_scale": target, "rows": prev_rows }}]}
        if any(w in ql for w in ["chart","graph","plot","visual"]):
            ct = "sgpa_trend"
            if "grade" in ql: ct = "grade_dist"
            elif "fail" in ql: ct = "fail_bar"
            elif "branch" in ql: ct = "branch_cgpa"
            return {"message": f"Showing {ct.replace('_',' ')} chart.", "actions": [{"type": "show_chart", "params": {"chart_type": ct, "semester": sem_num()}}]}
        if re.search(r'\b(convert|change|scale|gpa|percentage)\b', ql):
            conversion = resolver.detect_conversion(q)
            if conversion:
                prev_rows = state_mgr.last_rows if state_mgr else []; source_key = resolver.identify_source_field(prev_rows) or "sgpa"
                target = conversion.get("target_scale", 5.0) if conversion["type"]=="scale" else 100.0; conv_str = "percentage" if conversion["type"]=="percentage" else ("scale4" if abs(target-4)<0.1 else "scale5")
                if prev_rows: return {"message": f"Converting {source_key}.", "actions": [{"type": "convert_scale", "params": { "source_key": source_key, "conversion": conv_str, "target_scale": target, "rows": prev_rows }}]}
        if re.search(r'\b(show|list|display|get|fetch|give\s+me)?\s*(all|every|entire|complete)\s+(students?|records?|database|list)\b|\b(show|list|display)\s+students?\b|\ball\s+students\b', ql, re.IGNORECASE):
            m_limit = re.search(r'\blimit\s+(\d+)\b|\btop\s+(\d+)\b', ql); limit = int(m_limit.group(1) or m_limit.group(2)) if m_limit else None
            return {"message": "Listing all students.", "actions": [{"type": "all_students", "params": {"limit": limit} if limit else {}}]}
        m_top = re.search(r'\btop\s+(\d+)\b', ql)
        if any(w in ql for w in ["topper","top student","rank 1","highest sgpa","highest cgpa"]) or m_top:
            s = sem_num(); limit = int(m_top.group(1)) if m_top else None
            if m_top and not s: return {"message": f"Top students.", "actions": [{"type": "cgpa_rankings", "params": {"limit": limit} if limit else {}}]}
            return {"message": f"Top students.", "actions": [{"type": "query_topper", "params": {"semester": s, "limit": limit} if limit else {"semester": s}}]}
        if any(w in ql for w in ["fail report","backlog","back paper"]) or re.search(r'\bfail(?:ed)?\s*report\b', ql) or (re.search(r'\bfail(?:ed|ing)?\b', ql) and not re.search(r'^\s*(why|how|explain|describe)', ql)): return {"message": "Students with fails.", "actions": [{"type": "fail_report", "params": {"semester": sem_num()}}]}
        if any(w in ql for w in ["profile","transcript","full detail"]) and student_name(): return {"message": f"Profile for {student_name()}.", "actions": [{"type": "student_profile", "params": {"name": student_name()}}]}
        if any(w in ql for w in ["search","find","lookup","who is"]) and student_name(): return {"message": f"Searching for {student_name()}.", "actions": [{"type": "student_search", "params": {"name": student_name()}}]}
        if any(w in ql for w in ["cgpa","ranking","rankings"]): return {"message": "CGPA rankings.", "actions": [{"type": "cgpa_rankings", "params": {}}]}
        if "branch" in ql: return {"message": "Branch stats.", "actions": [{"type": "branch_stats", "params": {}}]}
        if "grade" in ql: return {"message": "Grade dist.", "actions": [{"type": "grade_distribution", "params": {"semester": sem_num()}}]}
        if any(w in ql for w in ["explain","describe","summar","overview","overall","insight","analys","trend","pattern","why","how"]): return {"message": "Semester stats.", "actions": [{"type": "semester_stats", "params": {}}]}
        if any(w in ql for w in ["export","download","save"]): fmt = ("excel" if any(x in ql for x in ["excel","xlsx"]) else "csv" if "csv" in ql else "excel"); return {"message": f"Preparing {fmt} export.", "actions": [{"type": f"export_{fmt}", "params": {}}]}
        if any(w in ql for w in ["close","hide","clear"]): return {"message": "Closing.", "actions": [{"type": "close_workspace", "params": {}}]}
        return {"message": "Showing semester stats.", "actions": [{"type": "semester_stats", "params": {}}]}

class QueryClassifier:
    _AI_STARTERS = re.compile(r'^\s*(explain|describe|why\s+do|why\s+does|why\s+are|how\s+does|how\s+can|compare|what\s+is|what\s+are|summarize|summarise|tell\s+me\s+about|what\s+factors|is\s+there|are\s+there)', re.IGNORECASE)
    _HYBRID = [r'(topper|top\s*\d+|rank).{1,40}(explain|analys|pattern|insight)', r'(explain|analys|compare).{1,40}(report|fetch|get|list|show\s+me)', r'(and\s+then|,\s*then|;\s*)(explain|analys|compare|insight)', r'(top\s*\d+).{1,30}(explain|why|how|pattern)', r'convert.{0,30}(cgpa|gpa|scale)']
    _SQL = [r'\b(topper|top\s*\d+|rank(?:ing)?s?)\b', r'\bfail(?:ed)?\s*report\b|\bbacklog\b|\bback\s*paper\b', r'\bsgpa\s+(of|for|in)\b|\bcgpa\s+(of|for|in)\b', r'\bsemester\s*\d\b|\bsem\s*\d\b', r'\b(filter|where|list\s+all|all\s+students)\b', r'\b(roll\s*number|enrollment)\b', r'\bfail\s*report\b|\bfetch\b', r'\bbranch\s+(stat|wise|average|ranking)\b', r'\bgrade\s+distribution\b', r'\b(search|find|lookup)\s+\w+\b', r'\b(chart|graph|plot)\b', r'\b(export|download|save\s+as)\b']
    _AI = [r'\b(explain|describe|what\s+is|what\s+are)\b', r'\b(compare|comparison|vs\.?|versus)\b', r'\b(summar(?:ise|ize)|overview|brief)\b', r'\b(insight|analys(?:e|is|ize))\b', r'\b(reason|why|how\s+does|how\s+can)\b', r'\b(advice|suggest|recommend)\b', r'\b(meaning|interpret|significance|important)\b']
    _ALL_STUDENTS = re.compile(r'\b(show|list|display|get|fetch|give\s+me)?\s*(all|every|entire|complete)\s+(students?|records?|database|list)\b|\b(show|list|display)\s+students?\b|\ball\s+students\b', re.IGNORECASE)
    _SEMANTIC_INTENT = [(re.compile(r'\b(strongest|best\s+academic|highest\s+achiever|star\s+performer)\b', re.IGNORECASE), "sql_agent", 0.87), (re.compile(r'\b(worst|lowest|struggling|poorest|bottom\s+\d+)\b', re.IGNORECASE), "sql_agent", 0.82), (re.compile(r'\b(improvement|trajectory|upward|downward|declining|growing)\b', re.IGNORECASE), "smart_ai", 0.80), (re.compile(r'\b(who\s+is|who\s+are)\s+the\b', re.IGNORECASE), "sql_agent", 0.84), (re.compile(r'\b(how\s+many|count|total\s+number\s+of)\b', re.IGNORECASE), "sql_agent", 0.85), (re.compile(r'\b(list|show|display|give\s+me)\s+(all|every|the)\b', re.IGNORECASE), "sql_agent", 0.83), (re.compile(r'\b(pattern|correlation|relationship|factor)\b', re.IGNORECASE), "smart_ai", 0.78), (re.compile(r'\b(convert|transform|change)\s+.{0,20}(scale|gpa|point|percent)\b', re.IGNORECASE), "sql_agent", 0.88)]
    _CALC_PATTERNS = [re.compile(r'\b(convert|change|transform)\s+.{0,30}(sgpa|cgpa|gpa|grade)\s+.{0,30}(scale|point|percent)', re.IGNORECASE), re.compile(r'\b(to\s+)?(scale\s*[0-9]|gpa\s*[0-9]|10\s*point|4\s*point|5\s*point|percent(?:age)?)\b', re.IGNORECASE), re.compile(r'\b(add|subtract|adjust)\s+\d+(\.\d+)?\s+(mark|point|grade)', re.IGNORECASE)]
    def classify(self, query: str) -> dict:
        q = query.strip()
        if self._ALL_STUDENTS.match(q) or self._ALL_STUDENTS.search(q): return {"route": "sql_agent", "confidence": 0.93, "intent": "all_students"}
        if all(p.search(q) for p in self._CALC_PATTERNS[:1]) or (self._CALC_PATTERNS[1].search(q) and re.search(r'\b(their|the|previous|last|those|these)\b', q, re.IGNORECASE)): return {"route": "calc_engine", "confidence": 0.91, "intent": "convert_scale"}
        for pat in self._HYBRID:
            if re.search(pat, q, re.IGNORECASE): return {"route": "hybrid", "confidence": 0.86}
        if self._AI_STARTERS.match(q):
            ai_score = sum(1 for p in self._AI if re.search(p, q, re.IGNORECASE)); return {"route": "smart_ai", "confidence": min(0.95, 0.70 + ai_score * 0.05)}
        for pattern, route, conf in self._SEMANTIC_INTENT:
            if pattern.search(q): return {"route": route, "confidence": conf, "semantic": True}
        sql = sum(1 for p in self._SQL if re.search(p, q, re.IGNORECASE)); ai = sum(1 for p in self._AI if re.search(p, q, re.IGNORECASE))
        if sql > 0 and ai > 0: return {"route": "hybrid", "confidence": 0.79}
        if ai > sql: return {"route": "smart_ai", "confidence": min(0.95, 0.62 + ai * 0.10)}
        if sql > 0: return {"route": "sql_agent", "confidence": min(0.95, 0.62 + sql * 0.07)}
        return {"route": "sql_agent", "confidence": 0.52}

class SelfHealingExecutor:
    _FALLBACKS = {"student_search": ("semester_stats", {}), "student_profile": ("semester_stats", {}), "subject_detail": ("semester_stats", {}), "fail_report": ("cgpa_rankings", {}), "query_topper": ("cgpa_rankings", {}), "convert_scale": ("semester_stats", {}), "adjust_marks": ("semester_stats", {})}
    MAX_ATTEMPTS = 4
    def __init__(self, executor): self._exec = executor
    def run(self, actions: list, qlib, ws_mgr, state, after_fn, chat_cb, state_mgr=None, steps=None) -> tuple:
        original = [dict(a) for a in actions]; current = [dict(a) for a in actions]; snapshot_rows = []
        if state_mgr: top = state_mgr.dataset_stack.peek(); snapshot_rows = top.rows[:] if top else []
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try: r = self._exec.execute(current, qlib, ws_mgr, state, after_fn, chat_cb, steps=steps if attempt == 1 else None); return r, attempt > 1, attempt
            except Exception as e:
                if attempt == 1: current = self._simplify(original)
                elif attempt == 2: current = self._fallback_actions(original)
                elif attempt == 3:
                    if state_mgr and snapshot_rows: state_mgr.record_action("rollback", snapshot_rows, source_query="(rollback)")
                    current = [{"type": "semester_stats", "params": {}}]
                else:
                    chat_cb("error", f"❌ All {self.MAX_ATTEMPTS} recovery attempts failed.")
                    return None, True, self.MAX_ATTEMPTS
        return None, True, self.MAX_ATTEMPTS
    def _simplify(self, actions: list) -> list:
        return [{"type": a.get("type"), "params": {k: v for k, v in a.get("params", {}).items() if k in ("semester", "name", "chart_type", "limit")}} for a in actions]
    def _fallback_actions(self, actions: list) -> list:
        return [{"type": self._FALLBACKS[a.get("type", "")][0], "params": self._FALLBACKS[a.get("type", "")][1]} if a.get("type") in self._FALLBACKS else a for a in actions]

class MultiStepWorkflowPlanner:
    _DATA_PRODUCERS = {"query_topper", "cgpa_rankings", "fail_report", "student_search", "semester_stats", "branch_stats", "grade_distribution", "subject_detail", "student_profile", "all_students"}
    _DATASET_CONSUMERS = {"convert_scale", "adjust_marks"}
    _EXPORT_ACTIONS = {"export_excel", "export_csv", "export_pdf"}
    def build_graph(self, actions: list, query: str) -> List[WorkflowStep]:
        has_convert = bool(ContextResolver().detect_conversion(query)); has_export = any(a.get("type", "").startswith("export") for a in actions)
        producers = []; consumers = []; exports = []
        for a in actions:
            atype = a.get("type", "")
            if atype in self._DATA_PRODUCERS: producers.append(WorkflowStep(name=atype.replace("_", " ").title(), action=atype))
            elif atype in self._DATASET_CONSUMERS: consumers.append(WorkflowStep(name=atype.replace("_", " ").title(), action=atype))
            elif atype in self._EXPORT_ACTIONS: exports.append(WorkflowStep(name=atype.replace("_", " ").title(), action=atype))
            else: producers.append(WorkflowStep(name=atype.replace("_", " ").title(), action=atype))
        if has_convert and not consumers: consumers.append(WorkflowStep(name="Scale Conversion", action="convert_scale"))
        steps = producers + consumers
        steps.append(WorkflowStep(name="Verify", action="__verify__")); steps.append(WorkflowStep(name="Render", action="__render__"))
        if has_export and not exports: exports.append(WorkflowStep(name="Export", action="export_excel"))
        steps.extend(exports)
        for i, s in enumerate(steps): s.depends_on = [steps[i - 1].action] if i > 0 else []
        return steps
    def step_summary(self, steps: List[WorkflowStep]) -> str:
        icons = {"pending": "○", "running": "⏳", "done": "✓", "failed": "✗"}
        return " → ".join([f"{icons.get(s.status, '?')} {s.name}" for s in steps])
class EnterpriseOrchestrator:
    def __init__(self, state, ws_mgr, after_fn):
        self.state = state; self.ws_mgr = ws_mgr; self.after_fn = after_fn
        self.state_mgr = WorkflowStateManager(); self.resolver = ContextResolver(); self.calc_eng = CalculationEngine()
        self.classifier = QueryClassifier(); self.planner = AIPlanner(state.openai_key, state.model)
        self.executor = ActionExecutor(self.state_mgr); self.healer = SelfHealingExecutor(self.executor)
        self.verifier = VerificationEngine(); self.schema_val = SchemaValidator(); self.ambiguity = AmbiguityDetector()
        self.ws_router = WorkspaceRouter(); self.workflow = MultiStepWorkflowPlanner(); self.memory = ConversationMemory()
        self.audit = AuditLog(state.db_path.replace(".db","_audit.db"))
    @property
    def context(self) -> WorkflowStateManager: return self.state_mgr
    def refresh(self): self.planner.openai_key = self.state.openai_key; self.planner.model = self.state.model
    def run(self, query: str, chat_cb) -> tuple:
        t0 = datetime.now(); report = ExecutionReport()
        self.memory.add_turn("user", query)
        cls = self.classifier.classify(query); route = cls["route"]; report.route = route
        schema_error = self.schema_val.validate(query, self.state.qlib)
        
        if schema_error: 
            chat_cb("bot", f"⚠️ {schema_error}"); report.execution_ms = (datetime.now() - t0).total_seconds() * 1000; report.schema_rejected = True; return report, schema_error, None
        
        ambig = self.ambiguity.check(query)
        if ambig: 
            chat_cb("bot", f"❓ {ambig['question']}\n" + "\n".join(f"   {i+1}. {c}" for i, c in enumerate(ambig["choices"])))
            report.execution_ms = (datetime.now() - t0).total_seconds() * 1000; return report, ambig["question"], None
            
        prev_rows = self.resolver.resolve_dataset(query, self.state_mgr)
        report.context_resolved = (prev_rows is not None or not self.resolver.has_pronoun(query))
        wf_id = self.state_mgr.new_workflow()
        plan = self.planner.plan(query, context={"last_name": self.state_mgr.last_name, "last_sem": self.state_mgr.last_sem, "recent_history": self.memory.recent_context(4)}, state_mgr=self.state_mgr)
        message = plan.get("message", ""); actions = plan.get("actions", [])
        steps = self.workflow.build_graph(actions, query); action_type = actions[0].get("type", "") if actions else ""

        if re.search(r'convert|gpa\s*4|4[-\s.]?point|4\.0\s*scale', query, re.IGNORECASE): actions = self._inject_conversion(actions, query)
        
        # Block internal dim logs from reaching the UI
        def _cb(tag, msg):
            if tag != "dim": 
                self.after_fn(0, lambda t=tag, m=msg: chat_cb(t, m))

        result, healed, attempts = self.healer.run(actions, self.state.qlib, self.ws_mgr, self.state, self.after_fn, _cb, state_mgr=self.state_mgr, steps=steps)
        report.sql_ok = True; report.healed = healed; report.attempts = attempts; report.rows_returned = len(self.state_mgr.last_rows); report.rows_rendered = len(self.state_mgr.last_rows)
        n_fetched = len(self.state_mgr.last_rows); expected_count = self.state.qlib.count_total("students") if action_type in ("all_students", "cgpa_rankings") and self.state.qlib else None
        calc_ok = True
        route_ok = False if (route == "smart_ai" and not self.state.openai_key) or (route == "hybrid" and action_type == "convert_scale") else True
        order_key = "sgpa" if any(a.get("type") in ("query_topper", "cgpa_rankings") and a.get("params", {}).get("semester") for a in actions) else "cgpa" if any(a.get("type") in ("query_topper", "cgpa_rankings") for a in actions) else None

        vr = self.verifier.verify(self.state_mgr.last_rows, expected_count=expected_count, rows_rendered=n_fetched, check_order_key=order_key, context_resolved=report.context_resolved, route_ok=route_ok, calculation_ok=calc_ok)
        report.verification_ok = vr["passed"]; report.raw_confidence = vr["confidence"]

        meta = ResultMeta(rows_fetched=n_fetched, rows_rendered=n_fetched); meta.detect_truncation()
        strategy = self.ws_router.route(self.state_mgr.last_rows, action_type, meta); report.workspace_ok = True

        if strategy["strategy"] == "chat_inline" and self.state_mgr.last_rows:
            chat_cb("bot", f"📋 Results:\n{self.ws_router.format_inline(self.state_mgr.last_rows)}")

        self.memory.add_workflow(wf_id, steps, success=report.verification_ok); self.memory.add_turn("bot", message or "OK", action_type=action_type)
        report.calculation_ok = calc_ok; report.execution_ms = (datetime.now() - t0).total_seconds() * 1000
        if self.audit: self.audit.record(query, report, workspace=action_type or "none")
        return report, message, result
        
    def _inject_conversion(self, actions: list, query: str) -> list:
        n_match = re.search(r'\btop\s*(\d+)\b', query, re.IGNORECASE); limit = int(n_match.group(1)) if n_match else None
        for a in actions:
            if a.get("type") in ("cgpa_rankings", "query_topper"):
                p = a.setdefault("params", {}); p["convert_gpa4"] = True
                if limit: p["limit"] = limit
        return actions
    def clear(self): self.state_mgr.clear(); self.memory.clear()

class EvaluationRunner:
    def __init__(self): self.tests = []; self._classifier = QueryClassifier(); self._planner = AIPlanner()
    def load(self, path: str = None) -> int:
        if path is None: path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "ai_queries.json")
        with open(path, encoding="utf-8") as f: self.tests = json.load(f)
        return len(self.tests)
    def run_all(self, progress_cb=None) -> dict:
        total_cls = 0; ok_cls = 0; total_plan = 0; ok_plan = 0
        for i, t in enumerate(self.tests):
            q = t["query"]; exp_route = t.get("expected_route"); exp_action = t.get("expected_action")
            cls_res = self._classifier.classify(q)
            if exp_route:
                total_cls += 1
                if cls_res["route"] == exp_route: ok_cls += 1
            plan_res = self._planner.plan(q)
            if exp_action:
                total_plan += 1
                got = (plan_res.get("actions",[{}])[0].get("type",""))
                if got == exp_action: ok_plan += 1
            if progress_cb: progress_cb(i+1, len(self.tests), q)
        return {"classifier_acc": ok_cls / total_cls if total_cls else 0, "planner_acc": ok_plan/ total_plan if total_plan else 0, "total_cls": total_cls, "ok_cls": ok_cls, "total_plan": total_plan, "ok_plan": ok_plan}
    def report_text(self, m: dict) -> str:
        overall = (m["classifier_acc"] + m["planner_acc"]) / 2
        grade = "A+" if overall>=0.95 else "A" if overall>=0.90 else "B+" if overall>=0.80 else "B"
        return "\n".join(["🧪 Evaluation Results", f"  QueryClassifier : {m['ok_cls']}/{m['total_cls']} = {m['classifier_acc']:.1%}", f"  AIPlanner        : {m['ok_plan']}/{m['total_plan']} = {m['planner_acc']:.1%}", f"  Overall          : {overall:.1%}  [{grade}]"])