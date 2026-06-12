import sqlite3, json, os, glob, threading
from datetime import datetime
from typing import Dict, List
import logging

logger = logging.getLogger("AcadLib.Database")

def build_database(json_dir, db_path):
    json_files = [f for f in sorted(glob.glob(os.path.join(json_dir,"*.json"))) if not os.path.basename(f).startswith("_")]
    if not json_files: raise FileNotFoundError(f"No JSON files in '{json_dir}'")
    all_data = [json.load(open(f,encoding="utf-8")) for f in json_files]
    
    temp_db_path = db_path + ".tmp"
    if os.path.exists(temp_db_path): os.remove(temp_db_path)
    
    conn = sqlite3.connect(temp_db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.executescript("""
        DROP TABLE IF EXISTS subjects; DROP TABLE IF EXISTS semesters; DROP TABLE IF EXISTS students;
        CREATE TABLE students (
            id INTEGER PRIMARY KEY, name TEXT COLLATE NOCASE, roll_number TEXT UNIQUE,
            enrollment_number TEXT, institute_code TEXT, institute_name TEXT COLLATE NOCASE,
            course TEXT, branch TEXT COLLATE NOCASE, gender TEXT, father_name TEXT COLLATE NOCASE,
            source_file TEXT, cgpa REAL, semesters_completed INTEGER, failed_subjects INTEGER
        );
        CREATE TABLE semesters (
            id INTEGER PRIMARY KEY, student_id INTEGER, semester_number INTEGER, even_odd TEXT,
            session TEXT, sgpa REAL, total_marks_obtained REAL, result_status TEXT,
            date_of_declaration TEXT, total_subjects INTEGER, theory_subjects INTEGER,
            practical_subjects INTEGER, FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY, semester_id INTEGER, subject_code TEXT COLLATE NOCASE,
            subject_name TEXT COLLATE NOCASE, subject_type TEXT, internal_marks REAL,
            external_marks REAL, total_marks REAL, back_paper_marks REAL, grade TEXT,
            FOREIGN KEY(semester_id) REFERENCES semesters(id)
        );
        CREATE INDEX idx_semesters_student_id ON semesters(student_id);
        CREATE INDEX idx_subjects_semester_id ON subjects(semester_id);
        CREATE INDEX idx_students_name ON students(name);
        CREATE INDEX idx_subjects_grade ON subjects(grade);
        CREATE INDEX idx_students_cgpa ON students(cgpa);
        CREATE INDEX idx_students_fails ON students(failed_subjects);
        CREATE INDEX idx_semesters_sem_num ON semesters(semester_number);
    """)
    students_data=[]; semesters_data=[]; subjects_data=[]
    student_id_counter=1; semester_id_counter=1; subject_id_counter=1
    
    for s in all_data:
        sems = s.get("semesters", [])
        sgpas = [sem["sgpa"] for sem in sems if sem.get("sgpa") is not None]
        cgpa = round(sum(sgpas)/len(sgpas),2) if sgpas else None
        semesters_completed = len(sems) # Ensure we count actual records
        fails = sum(1 for sem in sems for sub in sem.get("subjects",[]) if sub.get("grade") in ('F','E','E#'))
        students_data.append((student_id_counter, s.get("student_name"), s.get("roll_number"), s.get("enrollment_number"), s.get("institute_code"), s.get("institute_name"), s.get("course"), s.get("branch"), s.get("gender"), s.get("father_name"), s.get("source_file"), cgpa, semesters_completed, fails))
        for sem in sems:
            semesters_data.append((semester_id_counter, student_id_counter, sem.get("semester_number"), sem.get("even_odd"), sem.get("session"), sem.get("sgpa"), sem.get("total_marks_obtained"), sem.get("result_status"), sem.get("date_of_declaration"), sem.get("total_subjects"), sem.get("theory_subjects"), sem.get("practical_subjects")))
            for sub in sem.get("subjects", []):
                im=sub.get("internal_marks"); em=sub.get("external_marks"); tm=sub.get("total_marks")
                if tm is None:
                    if im is not None and em is not None: tm=im+em
                    elif im is not None: tm=im
                    elif em is not None: tm=em
                grade=sub.get("grade")
                if grade=="None": grade=None
                subjects_data.append((subject_id_counter, semester_id_counter, sub.get("subject_code"), sub.get("subject_name"), sub.get("subject_type"), im, em, tm, sub.get("back_paper_marks"), grade))
                subject_id_counter+=1
            semester_id_counter+=1
        student_id_counter+=1
        
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("INSERT INTO students (id,name,roll_number,enrollment_number,institute_code,institute_name,course,branch,gender,father_name,source_file,cgpa,semesters_completed,failed_subjects) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", students_data)
    cursor.executemany("INSERT INTO semesters (id,student_id,semester_number,even_odd,session,sgpa,total_marks_obtained,result_status,date_of_declaration,total_subjects,theory_subjects,practical_subjects) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", semesters_data)
    cursor.executemany("INSERT INTO subjects (id,semester_id,subject_code,subject_name,subject_type,internal_marks,external_marks,total_marks,back_paper_marks,grade) VALUES (?,?,?,?,?,?,?,?,?,?)", subjects_data)
    conn.commit()
    n = len(students_data)
    conn.close()
    
    if os.path.exists(db_path): os.remove(db_path)
    os.rename(temp_db_path, db_path)
    return n

class QueryLibrary:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._schema_cache: Dict[str, List[str]] = {}
        self._load_schema()

    def _load_schema(self):
        try:
            with self._lock:
                for tbl in ("students","semesters","subjects"):
                    cur = self.conn.execute(f"PRAGMA table_info({tbl})")
                    self._schema_cache[tbl] = [r[1] for r in cur.fetchall()]
        except Exception as e: logger.error(f"Failed to load schema: {e}")

    def get_schema(self) -> Dict[str, List[str]]: return self._schema_cache
    
    def _run(self, sql, params=()):
        with self._lock:
            try: return [dict(r) for r in self.conn.execute(sql, params).fetchall()]
            except Exception as e: logger.error(f"Query error: {sql} | {e}"); raise

    def execute_write(self, sql: str, params=()) -> int:
        if sql.strip().upper().startswith("SELECT"): raise ValueError("Use _run() for SELECT queries.")
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute(sql, params)
                self.conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Write query failed: {sql} | {e}")
                self.conn.rollback()
                raise

    # --- DYNAMIC FILTERS ---
    def _build_filter_sql(self, search: str, filters: dict):
        clauses = []; params = []
        if search:
            clauses.append("(name LIKE ? OR roll_number LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if filters:
            if filters.get("branch"):
                clauses.append("branch = ?"); params.append(filters["branch"])
            if filters.get("session"):
                # Subquery to filter students by session efficiently
                clauses.append("EXISTS (SELECT 1 FROM semesters sm WHERE sm.student_id = students.id AND sm.session = ?)")
                params.append(filters["session"])
            if filters.get("year"):
                val = filters["year"]
                if val == "1st Year": clauses.append("semesters_completed IN (1, 2)")
                elif val == "2nd Year": clauses.append("semesters_completed IN (3, 4)")
                elif val == "3rd Year": clauses.append("semesters_completed IN (5, 6)")
                elif val == "4th Year": clauses.append("semesters_completed IN (7, 8)")
                elif val == "Alumni/Grad": clauses.append("semesters_completed > 8")
            if filters.get("cgpa"):
                val = filters["cgpa"]
                if val == ">= 9.0": clauses.append("cgpa >= 9.0")
                elif val == ">= 8.0": clauses.append("cgpa >= 8.0")
                elif val == ">= 7.0": clauses.append("cgpa >= 7.0")
                elif val == ">= 6.0": clauses.append("cgpa >= 6.0")
                elif val == "< 6.0": clauses.append("cgpa < 6.0")
            if filters.get("fails"):
                val = filters["fails"]
                if val == "No Fails": clauses.append("failed_subjects = 0")
                elif val == "Has Fails": clauses.append("failed_subjects > 0")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def count_students(self, search: str = "", filters: dict = None) -> int:
        where, params = self._build_filter_sql(search, filters)
        return self._run(f"SELECT COUNT(*) as n FROM students {where}", tuple(params))[0]["n"]

    def list_students_paginated(self, limit: int, offset: int, search: str = "", sort_col: str = "name", sort_asc: bool = True, filters: dict = None):
        safe_cols = {"name": "name", "roll_number": "roll_number", "enrollment_number": "enrollment_number", "gender": "gender", "branch": "branch", "cgpa": "cgpa"}
        col = safe_cols.get(sort_col, "name"); order = "ASC" if sort_asc else "DESC"
        where, params = self._build_filter_sql(search, filters)
        sql = f"SELECT name,roll_number,enrollment_number,gender,branch,cgpa FROM students {where} ORDER BY {col} {order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return self._run(sql, tuple(params))

    def get_all_branches(self):
        rows = self._run("SELECT DISTINCT branch FROM students WHERE branch IS NOT NULL ORDER BY branch")
        return [r["branch"] for r in rows]

    def get_all_sessions(self):
        rows = self._run("SELECT DISTINCT session FROM semesters WHERE session IS NOT NULL ORDER BY session DESC")
        return [r["session"] for r in rows]

    def export_filtered_students(self, search: str = "", sort_col: str = "name", sort_asc: bool = True, filters: dict = None):
        safe_cols = {"name": "name", "roll_number": "roll_number", "enrollment_number": "enrollment_number", "gender": "gender", "branch": "branch", "cgpa": "cgpa"}
        col = safe_cols.get(sort_col, "name"); order = "ASC" if sort_asc else "DESC"
        where, params = self._build_filter_sql(search, filters)
        sql = f"SELECT RANK() OVER (ORDER BY {col} {order}) as Rank, name as Student_Name, roll_number as Roll_Number, enrollment_number as Enrollment_No, course as Course, branch as Branch, cgpa as CGPA, failed_subjects as Backlogs, semesters_completed as Semesters FROM students {where} ORDER BY {col} {order}"
        return self._run(sql, tuple(params))

    def list_all_students(self): return self._run("SELECT name,roll_number,enrollment_number,gender,branch,institute_name FROM students ORDER BY roll_number")
    def list_all_students_full(self): return self._run("SELECT name, roll_number, branch, cgpa, semesters_completed, gender, institute_name, RANK() OVER (ORDER BY cgpa DESC NULLS LAST) AS rank FROM students ORDER BY cgpa DESC NULLS LAST")
    def count_total(self, table: str = "students") -> int:
        try: return int(self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
        except: return 0
        
    def find_student(self, name): return self._run("SELECT * FROM students WHERE name LIKE ?", (f"%{name}%",))
    def get_student_sgpa(self, name, semester=None):
        if semester: return self._run("SELECT st.name,sm.semester_number,sm.sgpa,sm.result_status,sm.total_marks_obtained FROM students st JOIN semesters sm ON st.id=sm.student_id WHERE st.name LIKE ? AND sm.semester_number=?", (f"%{name}%",semester))
        return self._run("SELECT st.name,sm.semester_number,sm.sgpa,sm.result_status,sm.total_marks_obtained FROM students st JOIN semesters sm ON st.id=sm.student_id WHERE st.name LIKE ? ORDER BY sm.semester_number", (f"%{name}%",))
    def get_student_cgpa(self, name): return self._run("SELECT name,cgpa,semesters_completed FROM students WHERE name LIKE ?", (f"%{name}%",))
    def rank_students_by_sgpa(self, semester, limit=None):
        sql = "SELECT st.name,st.roll_number,st.branch,sm.sgpa,sm.result_status,sm.total_marks_obtained,RANK() OVER (ORDER BY sm.sgpa DESC) AS rank FROM students st JOIN semesters sm ON st.id=sm.student_id WHERE sm.semester_number=? ORDER BY sm.sgpa DESC"
        if limit: sql += f" LIMIT {int(limit)}"
        return self._run(sql, (semester,))
    def rank_students_by_cgpa(self, limit=None):
        sql = "SELECT name,roll_number,cgpa,semesters_completed,RANK() OVER (ORDER BY cgpa DESC) AS rank FROM students ORDER BY cgpa DESC"
        if limit: sql += f" LIMIT {int(limit)}"
        return self._run(sql)
    def get_fail_report(self, include_zero=False):
        if include_zero: return self._run("SELECT name,roll_number,failed_subjects FROM students ORDER BY failed_subjects DESC")
        return self._run("SELECT name,roll_number,failed_subjects FROM students WHERE failed_subjects>0 ORDER BY failed_subjects DESC")
    def get_fail_report_semester(self, semester): return self._run("SELECT st.name, st.roll_number, st.branch, COUNT(sub.id) AS failed_count, GROUP_CONCAT(sub.subject_name,', ') AS failed_subjects FROM students st JOIN semesters sm ON st.id=sm.student_id JOIN subjects sub ON sm.id=sub.semester_id WHERE sm.semester_number=? AND sub.grade IN ('F','E','E#') GROUP BY st.id ORDER BY failed_count DESC", (semester,))
    def get_student_subjects(self, name, semester): return self._run("SELECT sub.subject_code,sub.subject_name,sub.subject_type,sub.internal_marks,sub.external_marks,sub.total_marks,sub.back_paper_marks,sub.grade FROM students st JOIN semesters sm ON st.id=sm.student_id JOIN subjects sub ON sm.id=sub.semester_id WHERE st.name LIKE ? AND sm.semester_number=? ORDER BY sub.subject_type,sub.subject_code", (f"%{name}%",semester))
    def all_semester_stats(self): return self._run("SELECT semester_number,ROUND(AVG(sgpa),2) AS avg_sgpa,MAX(sgpa) AS max_sgpa,MIN(sgpa) AS min_sgpa,COUNT(*) AS students FROM semesters GROUP BY semester_number ORDER BY semester_number")
    def grade_distribution(self, semester=None):
        if semester: return self._run("SELECT sub.grade, COUNT(*) as count FROM semesters sm JOIN subjects sub ON sm.id=sub.semester_id WHERE sm.semester_number=? AND sub.grade IS NOT NULL GROUP BY sub.grade ORDER BY count DESC", (semester,))
        return self._run("SELECT grade, COUNT(*) as count FROM subjects WHERE grade IS NOT NULL GROUP BY grade ORDER BY count DESC")
    def branch_stats(self): return self._run("SELECT branch, COUNT(*) as students, ROUND(AVG(cgpa),2) as avg_cgpa, MAX(cgpa) as max_cgpa FROM students WHERE branch IS NOT NULL GROUP BY branch ORDER BY avg_cgpa DESC")
    def db_stats(self): return {"students": self.conn.execute("SELECT COUNT(*) FROM students").fetchone()[0], "semesters":self.conn.execute("SELECT COUNT(*) FROM semesters").fetchone()[0], "subjects": self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]}
    
    def close(self):
        with self._lock:
            if hasattr(self,'conn') and self.conn:
                try: self.conn.close()
                except Exception as e: logger.error(f"Error closing DB: {e}")

class AuditLog:
    _DDL = """CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, query TEXT NOT NULL,
        route TEXT DEFAULT '', execution_ms REAL DEFAULT 0, rows_returned INTEGER DEFAULT 0,
        workspace_used TEXT DEFAULT '', confidence REAL DEFAULT 0, status TEXT DEFAULT 'ok', error TEXT DEFAULT ''
    )"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = None
        self._init()
        
    def _init(self):
        try: 
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute(self._DDL); self._conn.commit()
        except Exception as e:
            logger.error(f"AuditLog init failed: {e}")
            self._conn = None
            
    def record(self, query: str, report, workspace: str = ""):
        if not self._conn: return
        with self._lock:
            try:
                self._conn.execute("INSERT INTO audit_log (timestamp,query,route,execution_ms,rows_returned,workspace_used,confidence,status,error) VALUES (?,?,?,?,?,?,?,?,?)", 
                                  (datetime.now().isoformat(), query, report.route, round(report.execution_ms, 1), report.rows_returned, workspace, report.confidence(), "error" if report.error else "ok", report.error[:500]))
                self._conn.commit()
            except Exception as e: logger.error(f"Failed to record audit log: {e}")
                
    def recent(self, limit: int = 20) -> list:
        if not self._conn: return []
        with self._lock:
            try: 
                cur = self._conn.execute("SELECT timestamp,query,route,execution_ms,rows_returned,workspace_used,confidence,status FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            except: return []
            
    def stats(self) -> dict:
        if not self._conn: return {}
        with self._lock:
            try:
                def _q(sql): return self._conn.execute(sql).fetchone()[0] or 0
                return {"total": _q("SELECT COUNT(*) FROM audit_log"), "avg_ms": round(_q("SELECT AVG(execution_ms) FROM audit_log"), 1), "avg_conf": round(_q("SELECT AVG(confidence) FROM audit_log"), 3), "errors": _q("SELECT COUNT(*) FROM audit_log WHERE status='error'"), "routes": dict(self._conn.execute("SELECT route,COUNT(*) FROM audit_log GROUP BY route").fetchall())}
            except: return {}
            
    def close(self):
        with self._lock:
            if self._conn:
                try: self._conn.close()
                except: pass