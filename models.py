from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class SubjectRecord:
    subject_code: str; subject_name: str; subject_type: str
    internal_marks: Optional[float]; external_marks: Optional[float]
    total_marks: Optional[float]; back_paper_marks: Optional[float]; grade: Optional[str]

@dataclass
class SemesterRecord:
    semester_number: int; even_odd: Optional[str]; session: Optional[str]
    total_subjects: Optional[int]; theory_subjects: Optional[int]
    practical_subjects: Optional[int]; total_marks_obtained: Optional[float]
    result_status: Optional[str]; sgpa: Optional[float]
    date_of_declaration: Optional[str]; subjects: list = field(default_factory=list)

@dataclass
class StudentRecord:
    source_file: Optional[str]; institute_code: Optional[str]
    institute_name: Optional[str]; course: Optional[str]; branch: Optional[str]
    roll_number: Optional[str]; enrollment_number: Optional[str]
    student_name: Optional[str]; father_name: Optional[str]
    gender: Optional[str]; semesters: list = field(default_factory=list)

@dataclass
class DatasetProvenance:
    dataset_id:    str
    source_query:  str
    creation_time: str
    workflow_id:   str
    action_type:   str
    derived_from:  Optional[str] = None

@dataclass
class DatasetEntry:
    entry_id:   str
    rows:       list
    provenance: DatasetProvenance
    label:      str = ""

class DatasetStack:
    MAX_DEPTH = 12
    def __init__(self):
        self._stack: List[DatasetEntry] = []
        self._counter = 0

    def push(self, rows: list, source_query: str, action_type: str, workflow_id: str = "", label: str = "") -> DatasetEntry:
        self._counter += 1
        parent_id = self._stack[-1].entry_id if self._stack else None
        ds_id = f"ds_{self._counter}_{action_type}"
        
        # ENTERPRISE FIX: Truncate in-memory dataset to prevent OOM errors on large AI chains
        # The AI only needs a sample to verify schema/values. The actual rendering UI
        # manages its own dataset reference.
        memory_safe_rows = rows[:150] if rows else []
        
        entry = DatasetEntry(entry_id=ds_id, rows=memory_safe_rows, label=label or action_type.replace("_", " ").title(),
            provenance=DatasetProvenance(dataset_id=ds_id, source_query=source_query, creation_time=datetime.now().isoformat(), workflow_id=workflow_id, action_type=action_type, derived_from=parent_id)
        )
        self._stack.append(entry)
        if len(self._stack) > self.MAX_DEPTH: self._stack = self._stack[-self.MAX_DEPTH:]
        return entry

    def peek(self) -> Optional[DatasetEntry]: return self._stack[-1] if self._stack else None
    def peek_by_type(self, action_type: str) -> Optional[DatasetEntry]:
        for e in reversed(self._stack):
            if e.provenance.action_type == action_type: return e
        return None
    def get_rows(self) -> list:
        top = self.peek()
        return top.rows if top else []
    def all_entries(self) -> List[DatasetEntry]: return list(self._stack)
    def provenance_chain(self, display_last: int = 4) -> str:
        if not self._stack: return "empty"
        total = len(self._stack)
        show  = self._stack[-display_last:]
        parts = [f"{e.provenance.action_type}({len(e.rows)})" for e in show]
        chain = " → ".join(parts)
        if total > display_last:
            older = total - display_last
            chain = f"[+{older} earlier] → {chain}"
        return chain
    def clear(self):
        self._stack = []; self._counter = 0

@dataclass
class ResultMeta:
    rows_fetched:   int  = 0
    rows_rendered:  int  = 0
    truncated:      bool = False
    token_overflow: bool = False
    CHAT_LIMIT    = 10
    MINI_WS_LIMIT = 50

    def detect_truncation(self):
        self.truncated      = self.rows_rendered < self.rows_fetched
        self.token_overflow = self.rows_fetched > self.MINI_WS_LIMIT

@dataclass
class ExecutionReport:
    route:            str   = ""
    sql_ok:           bool  = False
    verification_ok:  bool  = False
    calculation_ok:   bool  = False
    workspace_ok:     bool  = False
    context_resolved: bool  = False
    rows_returned:    int   = 0
    rows_rendered:    int   = 0
    execution_ms:     float = 0.0
    healed:           bool  = False
    attempts:         int   = 1
    error:            str   = ""
    raw_confidence:   float = 0.0
    schema_rejected:  bool  = False

    def confidence(self) -> float:
        if self.schema_rejected: return 0.93
        if self.raw_confidence > 0: 
            c = self.raw_confidence
        else: 
            c = sum(0.20 for ch in [self.sql_ok, self.verification_ok, self.calculation_ok, self.workspace_ok, self.context_resolved] if ch)
            
        # Mathematical penalties
        if self.healed:            c -= 0.05
        if self.attempts > 2:      c -= 0.05
        if self.error:             c  = c * 0.30
        if self.rows_returned == 0 and not self.error: c = max(c, 0.50)
        return round(min(max(c, 0.0), 1.0), 3)
    
    def badge(self) -> str:
        c = self.confidence()
        if c >= 0.90: return f"🟢 {c:.0%}"
        elif c >= 0.70: return f"🟡 {c:.0%}"
        else: return f"🔴 {c:.0%}"

@dataclass
class WorkflowStep:
    name:       str
    action:     str
    status:     str       = "pending"
    rows_in:    int       = 0
    rows_out:   int       = 0
    error:      str       = ""
    depends_on: List[str] = field(default_factory=list)