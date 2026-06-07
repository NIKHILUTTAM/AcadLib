import os, sys, glob, json, threading, traceback, subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
from config import THEME, FONT_TITLE, FONT_HEAD, FONT_BODY, FONT_SMALL, FONT_MONO, AppState
from ai_core import EnterpriseOrchestrator, EvaluationRunner, ExecutionReport
from extractors import process_batch_f1, parse_aktu_pdf_f1, run_format2_update, DataExporter

try: import matplotlib; matplotlib.use("TkAgg"); import matplotlib.pyplot as plt; from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg; HAS_MATPLOTLIB = True
except ImportError: HAS_MATPLOTLIB = False

def apply_theme(root):
    style=ttk.Style(root); style.theme_use("clam")
    bg=THEME["bg"]; card=THEME["card_bg"]; border=THEME["border"]; text=THEME["text"]
    style.configure(".",background=bg,foreground=text,font=FONT_BODY,borderwidth=0,relief="flat")
    style.configure("TFrame",background=bg)
    style.configure("Card.TFrame",background=card)
    style.configure("TLabel",background=bg,foreground=text)
    style.configure("Dim.TLabel",background=bg,foreground=THEME["text_dim"])
    style.configure("Card.TLabel",background=card,foreground=text)
    style.configure("Title.TLabel",background=bg,foreground=THEME["text_bright"],font=FONT_TITLE)
    style.configure("Head.TLabel",background=card,foreground=THEME["text_bright"],font=FONT_HEAD)
    style.configure("Accent.TLabel",background=bg,foreground=THEME["accent2"],font=FONT_HEAD)
    style.configure("WS.TLabel",background=THEME["ws_bg"],foreground=text)
    style.configure("WSHead.TLabel",background=THEME["ws_header"],foreground=THEME["text_bright"],font=FONT_HEAD)
    style.configure("WSCard.TFrame",background=THEME["ws_bg"])
    style.configure("TButton",background=THEME["hover"],foreground=text,borderwidth=1,relief="flat",padding=(12,6))
    style.map("TButton",background=[("active",THEME["border"]),("pressed",border)], foreground=[("active",THEME["text_bright"])])
    style.configure("Accent.TButton",background=THEME["accent2"],foreground="white", font=("Segoe UI",10,"bold"))
    style.map("Accent.TButton",background=[("active","#1A5FC8")])
    style.configure("Green.TButton",background=THEME["accent"],foreground="white", font=("Segoe UI",10,"bold"))
    style.map("Green.TButton",background=[("active","#196B2B")])
    style.configure("TEntry",fieldbackground=THEME["card_bg"],foreground=text, insertcolor=text,bordercolor=border,lightcolor=border,darkcolor=border)
    style.configure("TCombobox",fieldbackground=THEME["card_bg"],foreground=text, selectbackground=THEME["selected"],selectforeground=text)
    style.configure("TProgressbar",troughcolor=THEME["card_bg"],background=THEME["accent2"],bordercolor=border)
    style.configure("Horizontal.TProgressbar",troughcolor=THEME["card_bg"],background=THEME["accent2"])
    style.configure("Treeview",background=THEME["bg"],foreground=text,fieldbackground=THEME["bg"], bordercolor=border,rowheight=26)
    style.configure("Treeview.Heading",background=THEME["card_bg"],foreground=THEME["text_bright"], font=FONT_HEAD,relief="flat")
    style.map("Treeview",background=[("selected",THEME["selected"])], foreground=[("selected",THEME["text_bright"])])
    style.configure("TNotebook",background=bg,tabmargins=[2,5,2,0])
    style.configure("TNotebook.Tab",background=THEME["card_bg"],foreground=THEME["text_dim"], padding=[12,6])
    style.map("TNotebook.Tab",background=[("selected",THEME["selected"])], foreground=[("selected",THEME["text_bright"])])
    style.configure("TRadiobutton",background=bg,foreground=text)
    style.configure("TCheckbutton",background=bg,foreground=text)
    style.configure("TSeparator",background=border)

def make_card(parent, **kw): return ttk.Frame(parent, style="Card.TFrame", **kw)

class Sidebar(tk.Frame):
    ITEMS = [("Dashboard", "🏠"),("Upload F1", "📤"),("Upload F2", "📥"),("Database", "🗄️"),("Students", "👥"),("Analytics", "📊"),("Chatbot", "💬"),("SQL Studio","🧠"),("Export", "📦"),("Settings", "⚙️")]
    def __init__(self, parent, on_select):
        super().__init__(parent, bg=THEME["sidebar_bg"], width=220); self.pack_propagate(False); self._on_select = on_select; self._buttons = {}; self._selected = None; self._build()
    def _build(self):
        tk.Label(self, text="AcadLib", bg=THEME["sidebar_bg"], fg=THEME["text_bright"], font=("Segoe UI",15,"bold")).pack(pady=(22,4))
        tk.Label(self, text="University Records", bg=THEME["sidebar_bg"], fg=THEME["text_dim"], font=("Segoe UI",9)).pack(pady=(0,18))
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=(0,10))
        for name, icon in self.ITEMS:
            btn = tk.Button(self, text=f"  {icon}  {name}", bg=THEME["sidebar_bg"], fg=THEME["text"], activebackground=THEME["hover"], activeforeground=THEME["text_bright"], font=FONT_BODY, anchor="w", relief="flat", bd=0, padx=12, pady=8, cursor="hand2", command=lambda n=name: self._select(n))
            btn.pack(fill="x", pady=1); self._buttons[name] = btn
    def _select(self, name):
        for n, b in self._buttons.items(): b.configure(bg=THEME["selected"] if n==name else THEME["sidebar_bg"], fg=THEME["text_bright"] if n==name else THEME["text"])
        self._selected = name; self._on_select(name)
    def select(self, name): self._select(name)

class BaseWorkspace(tk.Frame):
    def __init__(self, parent, data: dict, state: AppState, title: str = ""):
        super().__init__(parent, bg=THEME["ws_bg"]); self.data = data; self.state = state; self.rows = []
        self._build_header(title); self.build()
    def _build_header(self, title: str):
        hdr = tk.Frame(self, bg=THEME["ws_header"]); hdr.pack(fill="x")
        tk.Label(hdr, text=title, bg=THEME["ws_header"], fg=THEME["text_bright"], font=FONT_HEAD, padx=12, pady=8).pack(side="left")
        self._btn_frame = tk.Frame(hdr, bg=THEME["ws_header"]); self._btn_frame.pack(side="right", padx=6)
    def _add_action_btn(self, label: str, command): ttk.Button(self._btn_frame, text=label, command=command, style="TButton").pack(side="left", padx=2, pady=4)
    def _make_tree(self, parent, cols, widths, height=12):
        tree_area = tk.Frame(parent, bg=THEME["bg"])
        tree_area.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_area, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths): tree.heading(c, text=str(c).replace("_"," ").title()); tree.column(c, width=w, minwidth=40)
        vsb = ttk.Scrollbar(tree_area, orient="vertical", command=tree.yview); hsb = ttk.Scrollbar(tree_area, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x"); tree.pack(fill="both", expand=True)
        tree.tag_configure("top", background="#1E2D1E", foreground=THEME["success"]); tree.tag_configure("odd", background=THEME["bg"]); tree.tag_configure("even", background=THEME["card_bg"]); tree.tag_configure("fail", foreground=THEME["error"])
        return tree
    def _fmt(self, v): return "—" if v is None else f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    def _save_export(self, fmt: str):
        if not self.rows: messagebox.showwarning("No Data","No rows to export."); return
        os.makedirs(self.state.export_dir, exist_ok=True); ext = {"xlsx":"xlsx","csv":"csv","pdf":"pdf"}.get(fmt, "xlsx")
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}", filetypes=[(f"{ext.upper()} file",f"*.{ext}")], initialdir=self.state.export_dir)
        if not path: return
        try:
            if fmt=="csv": DataExporter.to_csv(self.rows, path)
            elif fmt=="pdf": DataExporter.to_pdf(self.rows, path)
            else: DataExporter.to_excel_simple(self.rows, path)
            messagebox.showinfo("Exported", f"Saved → {path}")
        except Exception as e: messagebox.showerror("Export Failed", str(e))
    def build(self): pass

class ResultTableWorkspace(BaseWorkspace):
    PAGE_SIZE = 100
    def build(self):
        rows = self.data.get("rows", []); self.rows = rows; self._all_rows = rows; self._page = 0
        self._add_action_btn("⬇ Excel", lambda: self._save_export("xlsx")); self._add_action_btn("⬇ CSV", lambda: self._save_export("csv"))
        if not rows: tk.Label(self, text="⚠️  No results.", bg=THEME["ws_bg"], fg=THEME["warning"], font=FONT_BODY).pack(pady=40); return
        IDENTITY = ["name", "roll_number", "branch", "enrollment_number"]; raw_cols = list(rows[0].keys()); id_cols = [c for c in IDENTITY if c in raw_cols]; rest = [c for c in raw_cols if c not in id_cols]
        self._cols = id_cols + rest; widths = [max(80, min(200, len(str(c))*11)) for c in self._cols]
        n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1)
        if n_pages > 1:
            bar = tk.Frame(self, bg=THEME["ws_bg"]); bar.pack(side="top", fill="x", padx=8, pady=(8, 4))
            self._prev_btn = ttk.Button(bar, text="◀ Prev", width=8, command=self._prev_page); self._prev_btn.pack(side="left", padx=2)
            self._next_btn = ttk.Button(bar, text="Next ▶", width=8, command=self._next_page); self._next_btn.pack(side="left", padx=2)
            self._page_lbl = tk.Label(bar, text="", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL); self._page_lbl.pack(side="left", padx=8)
        else: self._prev_btn = self._next_btn = self._page_lbl = None
        self._tree = self._make_tree(self, self._cols, widths, height=18); self._load_page()
    def _load_page(self):
        rows = self._all_rows
        if not rows: return
        n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1); self._page = max(0, min(self._page, n_pages - 1))
        start = self._page * self.PAGE_SIZE; chunk = rows[start: start + self.PAGE_SIZE]
        self._tree.delete(*self._tree.get_children())
        self._tree.update_idletasks()
        for i, r in enumerate(chunk): self._tree.insert("", "end", values=[self._fmt(r.get(c)) for c in self._cols], tags=("odd" if i % 2 == 0 else "even",))
        if self._page_lbl: self._page_lbl.config(text=f"Rows {start+1}–{start+len(chunk)} of {len(rows)}  (page {self._page+1}/{n_pages})")
        if self._prev_btn: self._prev_btn.state(["disabled"] if self._page <= 0 else ["!disabled"]); self._next_btn.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])
    def _prev_page(self): self._page -= 1; self._load_page()
    def _next_page(self): self._page += 1; self._load_page()

class StudentProfileWorkspace(BaseWorkspace):
    def build(self):
        name = self.data.get("name","")
        if not name or not self.state.qlib: tk.Label(self, text="No student selected.", bg=THEME["ws_bg"], fg=THEME["warning"], font=FONT_BODY).pack(pady=40); return
        students = self.state.qlib.find_student(name)
        if not students: tk.Label(self, text=f"⚠️  Student '{name}' not found.", bg=THEME["ws_bg"], fg=THEME["error"], font=FONT_BODY).pack(pady=40); return
        st = students[0]
        self._add_action_btn("⬇ Excel", lambda: self._export_profile("xlsx")); self._add_action_btn("⬇ CSV", lambda: self._export_profile("csv"))
        info = tk.Frame(self, bg=THEME["card_bg"], padx=16, pady=10); info.pack(fill="x", padx=8, pady=(4,6))
        for label, key in [("Name",st.get("name")),("Roll",st.get("roll_number")), ("Branch",st.get("branch")),("CGPA",st.get("cgpa")), ("Fails",st.get("failed_subjects"))]: tk.Label(info, text=f"{label}: {key or '—'}", bg=THEME["card_bg"], fg=THEME["text_bright"], font=FONT_BODY).pack(anchor="w")
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=8, pady=4)
        ov = ttk.Frame(nb, style="TFrame"); nb.add(ov, text="  Overview  ")
        sem_rows = self.state.qlib._run("SELECT sm.semester_number,sm.session,sm.sgpa,sm.total_marks_obtained,sm.result_status FROM students st JOIN semesters sm ON st.id=sm.student_id WHERE st.name LIKE ? ORDER BY sm.semester_number", (f"%{name}%",))
        tree_ov = self._make_tree(ov, ("Semester","Session","SGPA","Marks","Status"), (80,120,80,80,120), height=8)
        for r in sem_rows: tree_ov.insert("","end", values=(r.get("semester_number"), r.get("session") or "—", r.get("sgpa") or "—", self._fmt(r.get("total_marks_obtained")), r.get("result_status") or "—"))
        for sem_num in sorted(set(r["semester_number"] for r in sem_rows)):
            sf = ttk.Frame(nb, style="TFrame"); nb.add(sf, text=f"  Sem {sem_num}  ")
            subs  = self.state.qlib.get_student_subjects(name, sem_num)
            tree_s = self._make_tree(sf, ("Code","Subject","Type","Int","Ext","Total","Grade"), (90,280,80,55,55,55,55), height=12)
            for sub in subs:
                grade = sub.get("grade")
                if grade is None or str(grade).lower()=="none": grade="—"
                tree_s.insert("","end", values=(sub.get("subject_code"), sub.get("subject_name"), sub.get("subject_type"), self._fmt(sub.get("internal_marks")), self._fmt(sub.get("external_marks")), self._fmt(sub.get("total_marks")), grade), tags=("fail" if grade in ("F","E","E#") else ""))
        self._profile_name = name
    def _export_profile(self, fmt):
        if not self.state.qlib: return
        rows = self.state.qlib._run("SELECT sm.semester_number,sub.subject_code,sub.subject_name,sub.subject_type, sub.internal_marks,sub.external_marks,sub.total_marks,sub.grade FROM students st JOIN semesters sm ON st.id=sm.student_id JOIN subjects sub ON sm.id=sub.semester_id WHERE st.name LIKE ? ORDER BY sm.semester_number,sub.subject_code", (f"%{getattr(self,'_profile_name','')}%",))
        self.rows = rows; self._save_export(fmt)

class AnalyticsWorkspace(BaseWorkspace):
    PAGE_SIZE = 100
    def build(self):
        rows = self.data.get("rows", []); x_key = self.data.get("x_key"); y_key = self.data.get("y_key"); subtitle = self.data.get("subtitle",""); self.rows = rows; self._all_rows = rows; self._page = 0
        self._add_action_btn("⬇ Excel", lambda: self._save_export("xlsx")); self._add_action_btn("⬇ CSV", lambda: self._save_export("csv"))
        if not rows: tk.Label(self, text="⚠️  No analytics data.", bg=THEME["ws_bg"], fg=THEME["warning"], font=FONT_BODY).pack(pady=40); return
        if subtitle: tk.Label(self, text=f"  {subtitle}", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=12)
        
        stat_row = tk.Frame(self, bg=THEME["ws_bg"]); stat_row.pack(fill="x", padx=8, pady=6); shown = 0
        for k, v in (rows[0] if rows else {}).items():
            if shown >= 4: break
            try:
                fv = float(v); c = tk.Frame(stat_row, bg=THEME["card_bg"], padx=14, pady=8); c.pack(side="left", padx=4, pady=2)
                cl = [THEME["accent2"],THEME["accent3"],THEME["accent"],THEME["warning"]][shown]
                tk.Label(c, text=f"{fv:.2f}".rstrip("0").rstrip("."), bg=THEME["card_bg"], fg=cl, font=("Segoe UI",15,"bold")).pack()
                tk.Label(c, text=k.replace("_"," ").title(), bg=THEME["card_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack()
                shown += 1
            except (TypeError, ValueError): pass
        
        split = tk.Frame(self, bg=THEME["ws_bg"]); split.pack(fill="both", expand=True, padx=4, pady=4)
        tbl_f = tk.Frame(split, bg=THEME["ws_bg"]); tbl_f.pack(side="left",fill="both",expand=True)
        
        cols = list(rows[0].keys()); self._cols = cols; widths = [max(80,min(180,len(str(c))*11)) for c in cols]
        
        n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1)
        if n_pages > 1:
            bar = tk.Frame(tbl_f, bg=THEME["ws_bg"]); bar.pack(side="top", fill="x", padx=4, pady=(0, 4))
            self._prev_btn = ttk.Button(bar, text="◀ Prev", width=8, command=self._prev_page); self._prev_btn.pack(side="left", padx=2)
            self._next_btn = ttk.Button(bar, text="Next ▶", width=8, command=self._next_page); self._next_btn.pack(side="left", padx=2)
            self._page_lbl = tk.Label(bar, text="", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL); self._page_lbl.pack(side="left", padx=8)
        else: self._prev_btn = self._next_btn = self._page_lbl = None

        self.tree = self._make_tree(tbl_f, cols, widths, height=12)
        self._load_page()

        if HAS_MATPLOTLIB and x_key and y_key and len(rows) >= 2:
            cf = tk.Frame(split, bg=THEME["ws_bg"], width=260); cf.pack(side="right", fill="both", padx=(4,0)); cf.pack_propagate(False)
            try:
                x_vals = [str(r.get(x_key,""))[:12] for r in rows[:15]]; y_vals = [float(r.get(y_key,0) or 0) for r in rows[:15]]
                fig,ax = plt.subplots(figsize=(3.2,3.2)); fig.patch.set_facecolor(THEME["ws_bg"]); ax.set_facecolor(THEME["ws_bg"])
                bars = ax.barh(x_vals, y_vals, color=THEME["accent2"], height=0.6)
                if rows: bars[0].set_color(THEME["accent3"])
                ax.set_xlabel(y_key.replace("_"," ").title(), color=THEME["text_dim"], fontsize=7); ax.tick_params(colors=THEME["text_dim"], labelsize=6)
                for spine in ax.spines.values(): spine.set_edgecolor(THEME["border"])
                fig.tight_layout(); canvas = FigureCanvasTkAgg(fig, master=cf); canvas.draw(); canvas.get_tk_widget().pack(fill="both", expand=True)
            except Exception: pass

    def _load_page(self):
        rows = self._all_rows
        if not rows: return
        n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1); self._page = max(0, min(self._page, n_pages - 1))
        start = self._page * self.PAGE_SIZE; chunk = rows[start: start + self.PAGE_SIZE]
        
        self.tree.delete(*self.tree.get_children())
        self.tree.update_idletasks()
        for i, r in enumerate(chunk): self.tree.insert("", "end", values=[self._fmt(r.get(c)) for c in self._cols], tags=("top" if start+i == 0 else ("odd" if i % 2 == 0 else "even"),))
        
        if self._page_lbl: self._page_lbl.config(text=f"Rows {start+1}–{start+len(chunk)} of {len(rows)}  (page {self._page+1}/{n_pages})")
        if self._prev_btn: self._prev_btn.state(["disabled"] if self._page <= 0 else ["!disabled"]); self._next_btn.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])

    def _prev_page(self): self._page -= 1; self._load_page()
    def _next_page(self): self._page += 1; self._load_page()

class ChartWorkspace(BaseWorkspace):
    def build(self):
        if not HAS_MATPLOTLIB: tk.Label(self, text="Install matplotlib: pip install matplotlib", bg=THEME["ws_bg"], fg=THEME["warning"], font=FONT_BODY).pack(pady=40); return
        chart_type = self.data.get("chart_type","sgpa_trend"); semester = self.data.get("semester"); qlib = self.state.qlib
        if not qlib: tk.Label(self, text="Database not ready.", bg=THEME["ws_bg"], fg=THEME["error"], font=FONT_BODY).pack(pady=40); return
        body = tk.Frame(self, bg=THEME["ws_bg"]); body.pack(fill="both", expand=True, padx=4, pady=4)
        try:
            fn = {"sgpa_trend":self._sgpa_trend,"grade_dist":self._grade_dist, "fail_bar":self._fail_bar,"branch_cgpa":self._branch_cgpa}.get(chart_type, self._sgpa_trend)
            fn(body, qlib, semester)
        except Exception as e: tk.Label(body, text=f"Chart error: {e}", bg=THEME["ws_bg"], fg=THEME["error"], font=FONT_SMALL).pack(pady=20)
    def _embed(self, fig, parent): c = FigureCanvasTkAgg(fig, master=parent); c.draw(); c.get_tk_widget().pack(fill="both", expand=True)
    def _fig(self, sz=(7,4)): fig,ax = plt.subplots(figsize=sz); fig.patch.set_facecolor(THEME["ws_bg"]); ax.set_facecolor(THEME["bg"]); [sp.set_edgecolor(THEME["border"]) for sp in ax.spines.values()]; ax.tick_params(colors=THEME["text_dim"]); return fig, ax
    def _sgpa_trend(self, p, q, _s):
        rows = q.all_semester_stats()
        if not rows: return
        sems=[r["semester_number"] for r in rows]; avgs=[r["avg_sgpa"] for r in rows]; maxs=[r["max_sgpa"] for r in rows]; mins=[r["min_sgpa"] for r in rows]
        fig,ax = self._fig(); ax.plot(sems,avgs,color=THEME["accent2"],linewidth=2.5,marker="o",label="Avg",zorder=3); ax.fill_between(sems,mins,maxs,color=THEME["accent2"],alpha=0.12); ax.plot(sems,maxs,color=THEME["success"],linewidth=1,linestyle="--",label="Max"); ax.plot(sems,mins,color=THEME["error"],linewidth=1,linestyle="--",label="Min"); ax.set_title("SGPA Trends",color=THEME["text_bright"],fontsize=12); ax.set_xticks(sems); ax.legend(facecolor=THEME["card_bg"],edgecolor=THEME["border"],labelcolor=THEME["text"]); fig.tight_layout(); self._embed(fig, p)
    def _grade_dist(self, p, q, sem):
        rows = q.grade_distribution(sem)
        if not rows: return
        from config import GRADE_COLORS; fig,ax = self._fig((6,4)); ax.bar([r["grade"] for r in rows],[r["count"] for r in rows], color=[GRADE_COLORS.get(r["grade"],THEME["accent2"]) for r in rows], width=0.6); ax.set_title(f"Grade Distribution{' Sem '+str(sem) if sem else ''}", color=THEME["text_bright"],fontsize=11); fig.tight_layout(); self._embed(fig, p)
    def _fail_bar(self, p, q, sem):
        if sem: rows=q.get_fail_report_semester(sem); cnt_key="failed_count"; ttl=f"Fails — Sem {sem}"
        else: rows=q.get_fail_report(); cnt_key="failed_subjects"; ttl="Failed Subjects / Student"
        if not rows: return
        labels=[r.get("name","")[:14] for r in rows[:20]]; counts=[r.get(cnt_key,0) for r in rows[:20]]
        fig,ax = self._fig((7,4)); ax.barh(list(range(len(labels))),counts,color=THEME["error"],height=0.6); ax.set_yticks(list(range(len(labels)))); ax.set_yticklabels(labels,fontsize=7,color=THEME["text"]); ax.set_title(ttl, color=THEME["text_bright"],fontsize=11); fig.tight_layout(); self._embed(fig, p)
    def _branch_cgpa(self, p, q, _s):
        rows = q.branch_stats()
        if not rows: return
        labels=[r.get("branch","")[:16] for r in rows[:12]]; vals=[r.get("avg_cgpa",0) or 0 for r in rows[:12]]; colors=[THEME["accent2"] if v>=7.5 else THEME["warning"] if v>=6.0 else THEME["error"] for v in vals]
        fig,ax = self._fig((7,4)); ax.barh(labels, vals, color=colors, height=0.6); ax.set_title("CGPA by Branch", color=THEME["text_bright"],fontsize=11); fig.tight_layout(); self._embed(fig, p)

class ExportPreviewWorkspace(BaseWorkspace):
    def build(self):
        rows = self.data.get("rows", []); self.rows = rows; body = tk.Frame(self, bg=THEME["ws_bg"]); body.pack(fill="both", expand=True, padx=8, pady=8)
        info = tk.Frame(body, bg=THEME["card_bg"], padx=12, pady=10); info.pack(fill="x", pady=(0,10))
        tk.Label(info, text=f"📦  {len(rows)} rows ready to export", bg=THEME["card_bg"], fg=THEME["text_bright"], font=FONT_HEAD).pack(anchor="w")
        tk.Label(info, text="Choose a format below and save the file.", bg=THEME["card_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(anchor="w")
        btn_row = tk.Frame(body, bg=THEME["ws_bg"]); btn_row.pack(fill="x", pady=6)
        for fmt,label,style in [("xlsx","📊  Excel (.xlsx)","Green.TButton"), ("csv","📄  CSV (.csv)","Accent.TButton"), ("pdf","📑  PDF (.pdf)","TButton")]: ttk.Button(btn_row, text=label, style=style, width=18, command=lambda f=fmt: self._save_export(f)).pack(side="left", padx=(0,8))
        if rows:
            ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8); tk.Label(body, text="Preview (first 10 rows):", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=4)
            cols = list(rows[0].keys()); widths = [max(80,min(180,len(str(c))*11)) for c in cols]; tree = self._make_tree(body, cols, widths, height=10)
            for i,r in enumerate(rows[:10]): tree.insert("","end", values=[self._fmt(r.get(c)) for c in cols], tags=("odd" if i%2==0 else "even",))

class SQLViewerWorkspace(BaseWorkspace):
    PAGE_SIZE = 100
    def build(self):
        sql = self.data.get("sql",""); rows = self.data.get("rows",[]); self.rows = rows; self._all_rows = rows; self._page = 0
        self._add_action_btn("⬇ CSV", lambda: self._save_export("csv"))
        body = tk.Frame(self, bg=THEME["ws_bg"]); body.pack(fill="both", expand=True, padx=6, pady=6)
        tk.Label(body, text="Generated SQL:", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(anchor="w")
        sql_box = tk.Text(body, bg=THEME["card_bg"], fg=THEME["accent2"], font=FONT_MONO, height=4, relief="flat", state="normal", wrap="word", padx=8, pady=6)
        sql_box.insert("1.0", sql or "— no SQL available —"); sql_box.configure(state="disabled"); sql_box.pack(fill="x", pady=(0,8))
        tk.Label(body, text=f"Results — {len(rows)} rows:", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(anchor="w")
        
        if rows:
            cols = list(rows[0].keys()); self._cols = cols; widths = [max(80,min(200,len(str(c))*11)) for c in cols]
            n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1)
            if n_pages > 1:
                bar = tk.Frame(body, bg=THEME["ws_bg"]); bar.pack(side="top", fill="x", pady=(0, 4))
                self._prev_btn = ttk.Button(bar, text="◀ Prev", width=8, command=self._prev_page); self._prev_btn.pack(side="left", padx=2)
                self._next_btn = ttk.Button(bar, text="Next ▶", width=8, command=self._next_page); self._next_btn.pack(side="left", padx=2)
                self._page_lbl = tk.Label(bar, text="", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL); self._page_lbl.pack(side="left", padx=8)
            else: self._prev_btn = self._next_btn = self._page_lbl = None
            self.tree = self._make_tree(body, cols, widths, height=12)
            self._load_page()
        else: tk.Label(body, text="No rows returned.", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(pady=20)

    def _load_page(self):
        rows = self._all_rows
        if not rows: return
        n_pages = max(1, (len(rows) - 1) // self.PAGE_SIZE + 1); self._page = max(0, min(self._page, n_pages - 1))
        start = self._page * self.PAGE_SIZE; chunk = rows[start: start + self.PAGE_SIZE]
        
        self.tree.delete(*self.tree.get_children())
        self.tree.update_idletasks()
        for i, r in enumerate(chunk): self.tree.insert("", "end", values=[self._fmt(r.get(c)) for c in self._cols], tags=("odd" if i % 2 == 0 else "even",))
        
        if self._page_lbl: self._page_lbl.config(text=f"Rows {start+1}–{start+len(chunk)} of {len(rows)}  (page {self._page+1}/{n_pages})")
        if self._prev_btn: self._prev_btn.state(["disabled"] if self._page <= 0 else ["!disabled"]); self._next_btn.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])

    def _prev_page(self): self._page -= 1; self._load_page()
    def _next_page(self): self._page += 1; self._load_page()


WORKSPACE_REGISTRY = {"result_table": ResultTableWorkspace, "student_profile": StudentProfileWorkspace, "analytics": AnalyticsWorkspace, "chart": ChartWorkspace, "export_preview": ExportPreviewWorkspace, "sql_viewer": SQLViewerWorkspace}

class WorkspaceManager:
    def __init__(self, paned_window: tk.PanedWindow, right_frame: tk.Frame, left_min: int = 420):
        self._pw = paned_window; self._rf = right_frame; self._lmin = left_min; self._current = None; self._ph = None; self._visible = False; self._show_placeholder()
    def open(self, workspace_key: str, data: dict, state: AppState, title: str = ""):
        cls = WORKSPACE_REGISTRY.get(workspace_key)
        if cls is None: return
        self._clear(); title = title or workspace_key.replace("_"," ").title(); ws = cls(self._rf, data, state, title=title); ws.pack(fill="both", expand=True); self._current = ws; self._show()
    def close(self): self._clear(); self._hide(); self._show_placeholder()
    def is_visible(self): return self._visible
    def _clear(self):
        for w in [self._current, self._ph]:
            if w:
                try: w.destroy()
                except: pass
        self._current = None; self._ph = None
    def _show(self):
        self._visible = True
        try:
            total = self._pw.winfo_width()
            if total > 200: self._pw.sash_place(0, max(self._lmin, total//2), 0)
        except: pass
    def _hide(self):
        self._visible = False
        try: total = self._pw.winfo_width(); self._pw.sash_place(0, total-2, 0)
        except: pass
    def _show_placeholder(self):
        self._ph = tk.Frame(self._rf, bg=THEME["ws_bg"]); self._ph.pack(fill="both", expand=True)
        tk.Label(self._ph, text="🖥", bg=THEME["ws_bg"], fg=THEME["border"], font=("Segoe UI",40)).pack(pady=(60,8))
        tk.Label(self._ph, text="AI Workspace\nResults appear here when you ask a question.", bg=THEME["ws_bg"], fg=THEME["text_dim"], font=FONT_BODY, justify="center").pack()

# --- PANELS ---

class DashboardPanel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self.configure(style="TFrame"); self._build()
    def _build(self):
        hdr=ttk.Frame(self,style="TFrame"); hdr.pack(fill="x",padx=32,pady=(28,4))
        ttk.Label(hdr,text="Dashboard",style="Title.TLabel").pack(side="left"); ttk.Button(hdr,text="⟳  Refresh",command=self.refresh,style="TButton").pack(side="right")
        ttk.Label(self,text="AcadLib University Records System — Admin Panel",style="Dim.TLabel").pack(anchor="w",padx=32)
        self.stats_row=ttk.Frame(self,style="TFrame"); self.stats_row.pack(fill="x",padx=24,pady=20)
        act=make_card(self); act.pack(fill="x",padx=32,pady=(0,16)); ttk.Label(act,text="Quick Actions",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,8))
        btn_row=ttk.Frame(act,style="Card.TFrame"); btn_row.pack(fill="x",padx=16,pady=(0,12))
        ttk.Button(btn_row,text="📤  Extract OneView PDFs",command=lambda:self.event_generate("<<Nav_Upload F1>>"),style="Accent.TButton",width=24).pack(side="left",padx=(0,8))
        ttk.Button(btn_row,text="📥  Update from Tabulation",command=lambda:self.event_generate("<<Nav_Upload F2>>"),style="Accent.TButton",width=24).pack(side="left",padx=(0,8))
        ttk.Button(btn_row,text="🗄️  Rebuild Database",command=lambda:self.event_generate("<<Nav_Database>>"),style="Green.TButton",width=24).pack(side="left",padx=(0,8))
        ttk.Button(btn_row,text="💬  Open AI Workspace",command=lambda:self.event_generate("<<Nav_Chatbot>>"),style="TButton",width=24).pack(side="left")
        log_card=make_card(self); log_card.pack(fill="both",expand=True,padx=32,pady=(0,24))
        ttk.Label(log_card,text="System Status",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.log_text=scrolledtext.ScrolledText(log_card,bg=THEME["bg"],fg=THEME["text_dim"],font=FONT_MONO,height=8,relief="flat",state="disabled")
        self.log_text.pack(fill="both",expand=True,padx=16,pady=(0,12)); self.refresh()
    def _stat_card(self,parent,title,value,icon,color):
        c=make_card(parent); c.pack(side="left",fill="both",expand=True,padx=8)
        tk.Label(c,text=icon,bg=THEME["card_bg"],fg=color,font=("Segoe UI",24)).pack(pady=(16,4)); tk.Label(c,text=str(value),bg=THEME["card_bg"],fg=THEME["text_bright"],font=("Segoe UI",22,"bold")).pack()
        tk.Label(c,text=title,bg=THEME["card_bg"],fg=THEME["text_dim"],font=("Segoe UI",10)).pack(pady=(2,16))
    def refresh(self):
        for w in self.stats_row.winfo_children(): w.destroy()
        if self.state.db_ready and self.state.qlib:
            try:
                st=self.state.qlib.db_stats()
                self._stat_card(self.stats_row,"Students",st["students"],"👥",THEME["accent2"]); self._stat_card(self.stats_row,"Semesters",st["semesters"],"📅",THEME["accent3"]); self._stat_card(self.stats_row,"Subjects",st["subjects"],"📚",THEME["accent"])
                json_count=len([f for f in glob.glob(os.path.join(self.state.json_dir,"*.json")) if not os.path.basename(f).startswith("_")])
                self._stat_card(self.stats_row,"JSON Files",json_count,"📄",THEME["warning"])
                self._log(f"✅ Database ready: {st['students']} students, {st['semesters']} semesters, {st['subjects']} subjects")
            except Exception as e: self._log(f"⚠️  DB read error: {e}")
        else:
            for title,val,icon,color in [("Students","—","👥",THEME["text_dim"]),("Semesters","—","📅",THEME["text_dim"]),("Subjects","—","📚",THEME["text_dim"]),("JSON Files","—","📄",THEME["text_dim"])]: self._stat_card(self.stats_row,title,val,icon,color)
            self._log("⚠️  Database not built yet. Go to Database → Rebuild.")
        self._log(f"📁 JSON dir : {self.state.json_dir}"); self._log(f"🗄️  DB path  : {self.state.db_path}")
        agent_status="✅ Enabled" if self.state.agent else ("🔑 Key set" if self.state.openai_key else "❌ No API key"); self._log(f"🤖 AI Agent : {agent_status}")
    def _log(self,msg): self.log_text.configure(state="normal"); self.log_text.insert("end",f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"); self.log_text.see("end"); self.log_text.configure(state="disabled")

class UploadF1Panel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._build()
    def _build(self):
        ttk.Label(self,text="Extract OneView PDFs  (Format 1)",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Parse AKTU OneView student result PDFs and extract data to JSON",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,16))
        mode_card=make_card(self); mode_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(mode_card,text="Processing Mode",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,8))
        self.mode=tk.StringVar(value="batch"); row=ttk.Frame(mode_card,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=(0,12))
        ttk.Radiobutton(row,text="Batch — process entire folder",variable=self.mode,value="batch").pack(side="left",padx=(0,24)); ttk.Radiobutton(row,text="Single PDF",variable=self.mode,value="single").pack(side="left")
        path_card=make_card(self); path_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(path_card,text="Paths",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        for label,attr in [("Input PDF / Folder","_f1_input"),("Output JSON Folder","_f1_output")]:
            row=ttk.Frame(path_card,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=4); ttk.Label(row,text=f"{label}:",style="Card.TLabel",width=22).pack(side="left")
            setattr(self,f"{attr}_var",tk.StringVar(value=self.state.json_dir)); e=ttk.Entry(row,textvariable=getattr(self,f"{attr}_var"),width=48); e.pack(side="left",padx=(0,8)); ttk.Button(row,text="Browse",command=lambda a=attr:self._browse(a,True),width=8).pack(side="left")
        ttk.Frame(path_card,style="Card.TFrame",height=8).pack(); prog_card=make_card(self); prog_card.pack(fill="x",padx=32,pady=(0,12))
        ttk.Label(prog_card,text="Progress",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6)); self.progress=ttk.Progressbar(prog_card,orient="horizontal",mode="determinate",length=600,style="Horizontal.TProgressbar"); self.progress.pack(padx=16,pady=(0,6))
        self.prog_label=ttk.Label(prog_card,text="Ready",style="Card.TLabel"); self.prog_label.pack(anchor="w",padx=16,pady=(0,12))
        btn_row=ttk.Frame(self,style="TFrame"); btn_row.pack(fill="x",padx=32,pady=(0,12)); ttk.Button(btn_row,text="▶  Start Extraction",command=self._run,style="Green.TButton",width=22).pack(side="left",padx=(0,8)); ttk.Button(btn_row,text="📂  Open Output Folder",command=self._open_out,style="TButton",width=22).pack(side="left")
        log_card=make_card(self); log_card.pack(fill="both",expand=True,padx=32,pady=(0,24)); ttk.Label(log_card,text="Log",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.log=scrolledtext.ScrolledText(log_card,bg=THEME["bg"],fg=THEME["text"],font=FONT_MONO,height=12,relief="flat",state="disabled"); self.log.pack(fill="both",expand=True,padx=16,pady=(0,12))
    def _browse(self,attr,is_dir): path=filedialog.askdirectory() if is_dir else filedialog.askopenfilename(filetypes=[("PDF","*.pdf")]); getattr(self,f"{attr}_var").set(path) if path else None
    def _log(self,msg): self.log.configure(state="normal"); self.log.insert("end",f"{msg}\n"); self.log.see("end"); self.log.configure(state="disabled")
    def _run(self):
        inp=self._f1_input_var.get(); out=self._f1_output_var.get()
        if not inp or not os.path.exists(inp): messagebox.showerror("Error","Input path does not exist"); return
        self.progress["value"]=0
        def progress_cb(done,total,name):
            self.progress["value"]=done/total*100 if total else 0; self.prog_label.configure(text=f"[{done}/{total}] {name}")
            self._log(f"  [{done}/{total}] {name}"); self.update_idletasks()
        def run():
            try:
                self._log(f"\n{'─'*50}\nStarting extraction...\nInput : {inp}\nOutput: {out}\n")
                if self.mode.get()=="batch":
                    results=process_batch_f1(inp,out,progress_cb); ok=sum(1 for v in results.values() if v.get("status")=="ok"); fail=len(results)-ok
                    self._log(f"\n✅ Done! {ok} succeeded, {fail} failed"); self.progress["value"]=100; self.prog_label.configure(text=f"Complete: {ok} OK, {fail} failed")
                else:
                    record=parse_aktu_pdf_f1(inp); stem=record.roll_number or Path(inp).stem; out_path=os.path.join(out,re.sub(r'[^\w]','_',stem)+".json")
                    os.makedirs(out,exist_ok=True)
                    with open(out_path,"w",encoding="utf-8") as f: json.dump(record.__dict__,f,indent=2,ensure_ascii=False)
                    self._log(f"✅ Saved → {out_path}"); self.progress["value"]=100
                self.state.json_dir=out; self.state.save_settings()
            except Exception as e: self._log(f"❌ Error: {e}\n{traceback.format_exc()}"); messagebox.showerror("Extraction Error",str(e))
        threading.Thread(target=run,daemon=True).start()
    def _open_out(self):
        path=self._f1_output_var.get()
        if os.path.isdir(path): os.startfile(path) if sys.platform=="win32" else subprocess.Popen(["xdg-open",path])

class UploadF2Panel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._build()
    def _build(self):
        ttk.Label(self,text="Update from Tabulation Register  (Format 2)",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Parse AKTU tabulation PDFs and update/create student JSON records",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,16))
        cfg=make_card(self); cfg.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(cfg,text="Configuration",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        for label,attr,default in [("Tabulation PDF","_f2_pdf",""),("JSON Dataset Dir","_f2_dir",self.state.json_dir)]:
            row=ttk.Frame(cfg,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=4); ttk.Label(row,text=f"{label}:",style="Card.TLabel",width=20).pack(side="left")
            setattr(self,f"{attr}_var",tk.StringVar(value=default)); ttk.Entry(row,textvariable=getattr(self,f"{attr}_var"),width=48).pack(side="left",padx=(0,8))
            ttk.Button(row,text="Browse",command=lambda a=attr,d=(label=="JSON Dataset Dir"):self._browse(a,d),width=8).pack(side="left")
        self._dry_run=tk.BooleanVar(value=False); row2=ttk.Frame(cfg,style="Card.TFrame"); row2.pack(fill="x",padx=16,pady=(4,12))
        ttk.Checkbutton(row2,text="Dry Run (preview changes, don't write files)",variable=self._dry_run).pack(side="left")
        self.progress=ttk.Progressbar(self,orient="horizontal",mode="determinate",length=600,style="Horizontal.TProgressbar"); self.progress.pack(padx=32,pady=(0,4))
        self.prog_label=ttk.Label(self,text="Ready",style="Dim.TLabel"); self.prog_label.pack(anchor="w",padx=32,pady=(0,8))
        btn_row=ttk.Frame(self,style="TFrame"); btn_row.pack(fill="x",padx=32,pady=(0,12)); ttk.Button(btn_row,text="▶  Run Update",command=self._run,style="Green.TButton",width=20).pack(side="left",padx=(0,8))
        summary_card=make_card(self); summary_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(summary_card,text="Summary",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,4))
        self.summary_labels={}; srow=ttk.Frame(summary_card,style="Card.TFrame"); srow.pack(fill="x",padx=16,pady=(0,12))
        for key,lbl,color in [("updated","Updated",THEME["success"]),("created","Created",THEME["accent2"]),("skipped","Skipped",THEME["text_dim"]),("conflict","Conflicts",THEME["error"])]:
            c=tk.Frame(srow,bg=THEME["card_bg"]); c.pack(side="left",expand=True); tk.Label(c,text="0",bg=THEME["card_bg"],fg=color,font=("Segoe UI",20,"bold")).pack(); tk.Label(c,text=lbl,bg=THEME["card_bg"],fg=THEME["text_dim"],font=FONT_SMALL).pack(); self.summary_labels[key]=c.winfo_children()[0]
        log_card=make_card(self); log_card.pack(fill="both",expand=True,padx=32,pady=(0,24)); ttk.Label(log_card,text="Log",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.log=scrolledtext.ScrolledText(log_card,bg=THEME["bg"],fg=THEME["text"],font=FONT_MONO,height=10,relief="flat",state="disabled"); self.log.pack(fill="both",expand=True,padx=16,pady=(0,12))
    def _browse(self,attr,is_dir): path=filedialog.askdirectory() if is_dir else filedialog.askopenfilename(filetypes=[("PDF","*.pdf")]); getattr(self,f"{attr}_var").set(path) if path else None
    def _log(self,msg): self.log.configure(state="normal"); self.log.insert("end",f"{msg}\n"); self.log.see("end"); self.log.configure(state="disabled")
    def _run(self):
        pdf=self._f2_pdf_var.get(); json_dir=self._f2_dir_var.get()
        if not os.path.isfile(pdf): messagebox.showerror("Error","PDF not found"); return
        if not json_dir: messagebox.showerror("Error","JSON directory required"); return
        dry=self._dry_run.get(); self.progress["value"]=0
        def progress_cb(done,total,msg): self.progress["value"]=done/total*100 if total else 0; self.prog_label.configure(text=f"[{done}/{total}] {msg}"); self._log(f"  [{done}/{total}] {msg}"); self.update_idletasks()
        def run():
            try:
                self._log(f"\n{'─'*50}\nParsing: {os.path.basename(pdf)}\nDry run: {dry}\n")
                doc,students,counters=run_format2_update(pdf,json_dir,dry_run=dry,progress_cb=progress_cb)
                self._log(f"\nInstitute : {doc.get('institute_name')}"); self._log(f"Branch    : {doc.get('branch_name')}"); self._log(f"Semester  : {doc.get('semester_number')} ({doc.get('sem_word')})"); self._log(f"Students  : {len(students)}")
                self._log(f"\nSummary: Updated={counters['updated']} Created={counters['created']} Skipped={counters['skipped']} Conflicts={counters['conflict']}")
                for k,lbl in self.summary_labels.items(): lbl.configure(text=str(counters.get(k,0)))
                self.progress["value"]=100
                if not dry: self.state.json_dir=json_dir; self.state.save_settings()
            except Exception as e: self._log(f"❌ Error: {e}\n{traceback.format_exc()}"); messagebox.showerror("Update Error",str(e))
        threading.Thread(target=run,daemon=True).start()

class DatabasePanel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._build()
    def _build(self):
        ttk.Label(self,text="Database Management",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Build and manage the SQLite relational database from JSON records",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,16))
        cfg=make_card(self); cfg.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(cfg,text="Configuration",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        for label,attr in [("JSON Source Directory","_db_json"),("Database File Path","_db_path")]:
            row=ttk.Frame(cfg,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=4); ttk.Label(row,text=f"{label}:",style="Card.TLabel",width=24).pack(side="left")
            val=self.state.json_dir if "JSON" in label else self.state.db_path
            setattr(self,f"{attr}_var",tk.StringVar(value=val)); ttk.Entry(row,textvariable=getattr(self,f"{attr}_var"),width=44).pack(side="left",padx=(0,8)); ttk.Button(row,text="Browse",command=lambda a=attr,d=("JSON" in label):self._browse(a,d),width=8).pack(side="left")
        ttk.Frame(cfg,style="Card.TFrame",height=8).pack(); agent_card=make_card(self); agent_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(agent_card,text="AI Agent (Optional)",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        row3=ttk.Frame(agent_card,style="Card.TFrame"); row3.pack(fill="x",padx=16,pady=(0,4)); ttk.Label(row3,text="OpenAI API Key:",style="Card.TLabel",width=18).pack(side="left")
        self._api_key_var=tk.StringVar(value=self.state.openai_key); e=ttk.Entry(row3,textvariable=self._api_key_var,width=52,show="•"); e.pack(side="left",padx=(0,8)); ttk.Button(row3,text="Show",command=lambda:e.configure(show="" if e["show"] else "•"),width=6).pack(side="left")
        row4=ttk.Frame(agent_card,style="Card.TFrame"); row4.pack(fill="x",padx=16,pady=(0,12)); ttk.Label(row4,text="Model:",style="Card.TLabel",width=18).pack(side="left")
        self._model_var=tk.StringVar(value=self.state.model); ttk.Combobox(row4,textvariable=self._model_var,width=20,values=["gpt-4o-mini","gpt-4o","gpt-3.5-turbo"]).pack(side="left")
        btn_row=ttk.Frame(self,style="TFrame"); btn_row.pack(fill="x",padx=32,pady=(0,12)); ttk.Button(btn_row,text="🗄️  Build / Rebuild DB",command=self._rebuild,style="Green.TButton",width=22).pack(side="left",padx=(0,8)); ttk.Button(btn_row,text="🤖  Initialize AI Agent",command=self._init_agent,style="Accent.TButton",width=22).pack(side="left",padx=(0,8)); ttk.Button(btn_row,text="💾  Save Settings",command=self._save,style="TButton",width=18).pack(side="left")
        self.status_card=make_card(self); self.status_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(self.status_card,text="Status",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.status_lbl=ttk.Label(self.status_card,text="Not built",style="Card.TLabel"); self.status_lbl.pack(anchor="w",padx=16,pady=(0,4))
        self.agent_lbl=ttk.Label(self.status_card,text="Agent: Not initialized",style="Card.TLabel"); self.agent_lbl.pack(anchor="w",padx=16,pady=(0,12))
        log_card=make_card(self); log_card.pack(fill="both",expand=True,padx=32,pady=(0,24)); ttk.Label(log_card,text="Output",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.log=scrolledtext.ScrolledText(log_card,bg=THEME["bg"],fg=THEME["text"],font=FONT_MONO,height=8,relief="flat",state="disabled"); self.log.pack(fill="both",expand=True,padx=16,pady=(0,12)); self._refresh_status()
    def _browse(self,attr,is_dir): path=filedialog.askdirectory() if is_dir else filedialog.asksaveasfilename(defaultextension=".db",filetypes=[("SQLite","*.db")]); getattr(self,f"{attr}_var").set(path) if path else None
    def _log(self,msg): self.log.configure(state="normal"); self.log.insert("end",f"{msg}\n"); self.log.see("end"); self.log.configure(state="disabled")
    def _save(self):
        self.state.json_dir=self._db_json_var.get(); self.state.db_path=self._db_path_var.get(); self.state.openai_key=self._api_key_var.get(); self.state.model=self._model_var.get(); self.state.save_settings(); self._log("✅ Settings saved"); messagebox.showinfo("Saved","Settings saved.")
    def _rebuild(self):
        json_dir=self._db_json_var.get()
        if not os.path.isdir(json_dir): messagebox.showerror("Error","JSON directory not found"); return
        def run():
            try: self._log(f"Building database from {json_dir}..."); n=self.state.rebuild_db(); self._log(f"✅ Database built — {n} students"); self._refresh_status()
            except Exception as e: self._log(f"❌ {e}"); messagebox.showerror("DB Error",str(e))
        threading.Thread(target=run,daemon=True).start()
    def _init_agent(self):
        key=self._api_key_var.get()
        if not key: messagebox.showerror("Error","Please enter an OpenAI API key"); return
        if not self.state.db_ready: messagebox.showerror("Error","Build the database first"); return
        self.state.openai_key=key; self.state.model=self._model_var.get(); self._log("Initializing AI Agent..."); self.update_idletasks(); ok=self.state.init_agent()
        if ok:
            self._log(f"✅ Agent ready (model: {self.state.model})"); self.agent_lbl.configure(text=f"Agent: ✅ Ready ({self.state.model})",foreground=THEME["success"]); messagebox.showinfo("Success","AI Agent is ready! Go to the Chatbot tab.")
        else: err=getattr(self.state,"last_agent_error","Unknown error"); self._log(f"❌ Agent initialization failed: {err}"); messagebox.showerror("Agent Error",f"Failed to initialize the AI agent.\n\nDetails: {err}")
    def _refresh_status(self):
        if self.state.db_ready and os.path.exists(self.state.db_path):
            try: s=self.state.qlib.db_stats(); self.status_lbl.configure(text=f"✅ Ready — {s['students']} students · {s['semesters']} semesters · {s['subjects']} subjects",foreground=THEME["success"])
            except: self.status_lbl.configure(text="⚠️ DB exists but unreadable",foreground=THEME["warning"])
        else: self.status_lbl.configure(text="❌ Not built",foreground=THEME["error"])

class StudentsPanel(ttk.Frame):
    PAGE_SIZE = 100
    def __init__(self,parent,state:AppState): 
        super().__init__(parent); self.state=state; self._rows=[]
        self._page=0; self._total_records=0
        self._sort_col="name"; self._sort_asc=True; self._build()
    
    def _build(self):
        self.main_container = ttk.Frame(self, style="TFrame")
        self.main_container.pack(fill="both", expand=True)

        self.list_view = ttk.Frame(self.main_container, style="TFrame")
        self.list_view.pack(fill="both", expand=True)

        ttk.Label(self.list_view,text="Students",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4))
        bar=ttk.Frame(self.list_view,style="TFrame"); bar.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(bar,text="Search:").pack(side="left",padx=(0,8))
        self._search_var=tk.StringVar(); e=ttk.Entry(bar,textvariable=self._search_var,width=36); e.pack(side="left",padx=(0,8)); e.bind("<Return>",lambda _:self._search())
        ttk.Button(bar,text="Search",command=self._search,style="Accent.TButton").pack(side="left",padx=(0,8)); ttk.Button(bar,text="Show All",command=self._load_all,style="TButton").pack(side="left"); self._count_lbl=ttk.Label(bar,text="",style="Dim.TLabel"); self._count_lbl.pack(side="right")
        
        tbl_frame=make_card(self.list_view); tbl_frame.pack(fill="both",expand=True,padx=32,pady=(0,8))
        tbl_frame.grid_columnconfigure(0, weight=1); tbl_frame.grid_rowconfigure(1, weight=1)
        
        page_bar = ttk.Frame(tbl_frame, style="Card.TFrame")
        page_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.btn_prev = ttk.Button(page_bar, text="◀ Prev", command=self._prev_page, width=8); self.btn_prev.pack(side="left")
        self.btn_next = ttk.Button(page_bar, text="Next ▶", command=self._next_page, width=8); self.btn_next.pack(side="left", padx=5)
        self.page_lbl = ttk.Label(page_bar, text="", style="Dim.TLabel"); self.page_lbl.pack(side="left", padx=10)
        
        tree_container = ttk.Frame(tbl_frame, style="TFrame")
        tree_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))

        cols=("Name","Roll Number","Enrollment","Gender","Branch"); self.tree=ttk.Treeview(tree_container,columns=cols,show="headings",height=16)
        
        col_map={"Name":"name","Roll Number":"roll_number","Enrollment":"enrollment_number","Gender":"gender","Branch":"branch"}
        for col,w in zip(cols,(240,160,180,80,220)): 
            self.tree.heading(col,text=col,command=lambda c=col_map[col]:self._sort(c))
            self.tree.column(col,width=w,minwidth=60)
            
        vsb=ttk.Scrollbar(tree_container,orient="vertical",command=self.tree.yview); hsb=ttk.Scrollbar(tree_container,orient="horizontal",command=self.tree.xview); self.tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x"); self.tree.pack(fill="both",expand=True); self.tree.tag_configure("odd",background=THEME["bg"]); self.tree.tag_configure("even",background=THEME["card_bg"])
        
        self.tree.bind("<Double-1>", self._on_double_click)

        self.profile_view = ttk.Frame(self.main_container, style="TFrame")
        self._load_all()

    def _on_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        values = self.tree.item(item_id, "values")
        if not values: return
        student_name = values[0]
        
        self.list_view.pack_forget()
        self._build_profile(student_name)
        self.profile_view.pack(fill="both", expand=True)

    def _show_list(self):
        self.profile_view.pack_forget()
        self.list_view.pack(fill="both", expand=True)

    def _fmt(self, v): return "—" if v is None else f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    
    def _make_profile_tree(self, parent, cols, widths, height=12):
        tree_area = tk.Frame(parent, bg=THEME["bg"]); tree_area.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_area, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths): tree.heading(c, text=str(c).replace("_"," ").title()); tree.column(c, width=w, minwidth=40)
        vsb = ttk.Scrollbar(tree_area, orient="vertical", command=tree.yview); hsb = ttk.Scrollbar(tree_area, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x"); tree.pack(fill="both", expand=True)
        tree.tag_configure("odd", background=THEME["bg"]); tree.tag_configure("even", background=THEME["card_bg"]); tree.tag_configure("fail", foreground=THEME["error"])
        return tree

    def _build_profile(self, name):
        for w in self.profile_view.winfo_children(): w.destroy()

        hdr = ttk.Frame(self.profile_view, style="TFrame")
        hdr.pack(fill="x", padx=32, pady=(28,4))
        ttk.Button(hdr, text="◀ Back to Students", command=self._show_list, style="Accent.TButton").pack(side="left", padx=(0,16))
        ttk.Label(hdr, text=f"Profile: {name}", style="Title.TLabel").pack(side="left")

        if not self.state.qlib: return
        students = self.state.qlib.find_student(name)
        if not students:
            ttk.Label(self.profile_view, text="Student not found.", style="Dim.TLabel").pack(padx=32, pady=20); return
        st = students[0]

        card = make_card(self.profile_view)
        card.pack(fill="both", expand=True, padx=32, pady=(0,24))

        info = tk.Frame(card, bg=THEME["card_bg"], padx=16, pady=10); info.pack(fill="x", padx=8, pady=(4,6))
        for label, key in [("Name",st.get("name")),("Roll",st.get("roll_number")), ("Branch",st.get("branch")),("CGPA",st.get("cgpa")), ("Fails",st.get("failed_subjects"))]: 
            tk.Label(info, text=f"{label}: {key or '—'}", bg=THEME["card_bg"], fg=THEME["text_bright"], font=FONT_BODY).pack(anchor="w")

        nb = ttk.Notebook(card); nb.pack(fill="both", expand=True, padx=16, pady=(0,16))

        ov = ttk.Frame(nb, style="TFrame"); nb.add(ov, text="  Overview  ")
        sem_rows = self.state.qlib._run("SELECT sm.semester_number,sm.session,sm.sgpa,sm.total_marks_obtained,sm.result_status FROM students st JOIN semesters sm ON st.id=sm.student_id WHERE st.name LIKE ? ORDER BY sm.semester_number", (f"%{name}%",))
        tree_ov = self._make_profile_tree(ov, ("Semester","Session","SGPA","Marks","Status"), (80,120,80,80,120), height=8)
        for r in sem_rows: tree_ov.insert("","end", values=(r.get("semester_number"), r.get("session") or "—", r.get("sgpa") or "—", self._fmt(r.get("total_marks_obtained")), r.get("result_status") or "—"))

        for sem_num in sorted(set(r["semester_number"] for r in sem_rows)):
            sf = ttk.Frame(nb, style="TFrame"); nb.add(sf, text=f"  Sem {sem_num}  ")
            subs  = self.state.qlib.get_student_subjects(name, sem_num)
            tree_s = self._make_profile_tree(sf, ("Code","Subject","Type","Int","Ext","Total","Grade"), (90,280,80,55,55,55,55), height=12)
            for sub in subs:
                grade = sub.get("grade")
                if grade is None or str(grade).lower()=="none": grade="—"
                tree_s.insert("","end", values=(sub.get("subject_code"), sub.get("subject_name"), sub.get("subject_type"), self._fmt(sub.get("internal_marks")), self._fmt(sub.get("external_marks")), self._fmt(sub.get("total_marks")), grade), tags=("fail" if grade in ("F","E","E#") else ""))

    def _load_all(self):
        if not self.state.db_ready: return
        self._search_var.set("")
        self._page = 0
        self._fetch_page()

    def _search(self):
        if not self.state.db_ready: return
        self._page = 0
        self._fetch_page()

    def _fetch_page(self):
        q = self._search_var.get().strip()
        offset = self._page * self.PAGE_SIZE
        
        self._total_records = self.state.qlib.count_students(search=q)
        self._rows = self.state.qlib.list_students_paginated(limit=self.PAGE_SIZE, offset=offset, search=q, sort_col=self._sort_col, sort_asc=self._sort_asc)
        
        self._render_tree()

    def _render_tree(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        if not self._rows: 
            self.page_lbl.configure(text="No results found."); self.btn_prev.state(["disabled"]); self.btn_next.state(["disabled"]); return
        
        n_pages = max(1, (self._total_records - 1) // self.PAGE_SIZE + 1)
        start = (self._page * self.PAGE_SIZE) + 1
        end = min(start + self.PAGE_SIZE - 1, self._total_records)
        
        for i,r in enumerate(self._rows): 
            self.tree.insert("","end",values=(r.get("name"),r.get("roll_number"),r.get("enrollment_number"),r.get("gender"),r.get("branch")),tags=("odd" if i%2==0 else "even",))
        
        self.page_lbl.configure(text=f"Rows {start}–{end} of {self._total_records}  (Page {self._page+1}/{n_pages})")
        self._count_lbl.configure(text=f"Total: {self._total_records} student(s)")
        
        self.btn_prev.state(["disabled"] if self._page <= 0 else ["!disabled"])
        self.btn_next.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])

    def _prev_page(self):
        if self._page > 0: self._page -= 1; self._fetch_page()
    def _next_page(self):
        if self._page < (self._total_records - 1) // self.PAGE_SIZE: self._page += 1; self._fetch_page()

    def _sort(self,col_key):
        self._sort_asc = not self._sort_asc if self._sort_col==col_key else True
        self._sort_col=col_key
        self._page = 0
        self._fetch_page()

class AnalyticsPanel(ttk.Frame):
    PAGE_SIZE = 100
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._rows=[]; self._cols=[]; self._page=0; self._build()
    def _build(self):
        ttk.Label(self,text="Analytics",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="CGPA rankings, fail reports, and semester statistics",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,12)); btn_row=ttk.Frame(self,style="TFrame"); btn_row.pack(fill="x",padx=32,pady=(0,12))
        for lbl,cmd in [("🏆 CGPA Rankings",self._cgpa),("❌ Fail Report",self._fails), ("📊 Semester Stats",self._stats),("🏫 Branch Stats",self._branch)]: ttk.Button(btn_row,text=lbl,command=cmd,style="TButton",width=20).pack(side="left",padx=(0,8))
        tbl_card=make_card(self); tbl_card.pack(fill="both",expand=True,padx=32,pady=(0,24))
        tbl_card.grid_columnconfigure(0, weight=1); tbl_card.grid_rowconfigure(1, weight=1)
        
        page_bar = ttk.Frame(tbl_card, style="Card.TFrame")
        page_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.btn_prev = ttk.Button(page_bar, text="◀ Prev", command=self._prev_page, width=8); self.btn_prev.pack(side="left", padx=2)
        self.btn_next = ttk.Button(page_bar, text="Next ▶", command=self._next_page, width=8); self.btn_next.pack(side="left", padx=2)
        self.page_lbl = ttk.Label(page_bar, text="", style="Dim.TLabel"); self.page_lbl.pack(side="left", padx=8)

        tree_container = ttk.Frame(tbl_card, style="TFrame")
        tree_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))

        self.tree=ttk.Treeview(tree_container,show="headings"); vsb=ttk.Scrollbar(tree_container,orient="vertical",command=self.tree.yview); hsb=ttk.Scrollbar(tree_container,orient="horizontal",command=self.tree.xview); self.tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set); vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x"); self.tree.pack(fill="both",expand=True); self.tree.tag_configure("odd",background=THEME["bg"]); self.tree.tag_configure("even",background=THEME["card_bg"])
        self._status=ttk.Label(self,text="",style="Dim.TLabel"); self._status.pack(anchor="w",padx=32,pady=(0,8))

    def _load(self,rows,cols=None):
        self._rows = rows; self._cols = cols if cols is not None else (list(rows[0].keys()) if rows else []); self.tree["columns"]=self._cols
        for col in self._cols: self.tree.heading(col,text=col.replace("_"," ").title()); self.tree.column(col,width=max(80,min(200,len(col)*11)))
        self._page = 0; self._render_page()

    def _render_page(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        if not self._rows: 
            self.page_lbl.configure(text="No data"); self._status.configure(text="Total: 0 rows"); self.btn_prev.state(["disabled"]); self.btn_next.state(["disabled"]); return
        self.tree.update_idletasks()
        start = self._page * self.PAGE_SIZE; chunk = self._rows[start : start + self.PAGE_SIZE]
        n_pages = max(1, (len(self._rows) - 1) // self.PAGE_SIZE + 1)
        for i,r in enumerate(chunk): self.tree.insert("","end",values=[r.get(c,"") for c in self._cols],tags=("odd" if i%2==0 else "even",))
        self.page_lbl.configure(text=f"Rows {start+1}–{start+len(chunk)} of {len(self._rows)}  (Page {self._page+1}/{n_pages})")
        self._status.configure(text=f"Total: {len(self._rows)} rows")
        self.btn_prev.state(["disabled"] if self._page <= 0 else ["!disabled"])
        self.btn_next.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])

    def _prev_page(self):
        if self._page > 0: self._page -= 1; self._render_page()
    def _next_page(self):
        if self._page < (len(self._rows) - 1) // self.PAGE_SIZE: self._page += 1; self._render_page()

    def _check(self):
        if not self.state.db_ready: messagebox.showwarning("DB","Database not ready"); return False
        return True
    def _cgpa(self):
        if self._check(): self._load(self.state.qlib.rank_students_by_cgpa())
    def _fails(self):
        if self._check(): self._load(self.state.qlib.get_fail_report())
    def _stats(self):
        if self._check(): self._load(self.state.qlib.all_semester_stats())
    def _branch(self):
        if self._check(): self._load(self.state.qlib.branch_stats())

class ExportPanel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._build()
    def _build(self):
        ttk.Label(self,text="Export",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Export academic data to Excel, CSV, or PDF",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,16)); card=make_card(self); card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(card,text="Quick Export",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,8))
        for lbl,cmd in [("📊  Master Excel Report",self._master_excel), ("📄  CGPA Rankings CSV",self._cgpa_csv), ("❌  Fail Report CSV",self._fail_csv), ("📊  Semester Stats CSV",self._stats_csv)]:
            row=ttk.Frame(card,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=3); ttk.Button(row,text=lbl,command=cmd,style="TButton",width=30).pack(side="left")
        ttk.Frame(card,style="Card.TFrame",height=8).pack(); log_card=make_card(self); log_card.pack(fill="both",expand=True,padx=32,pady=(0,24)); ttk.Label(log_card,text="Export Log",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self.log=scrolledtext.ScrolledText(log_card,bg=THEME["bg"],fg=THEME["text"],font=FONT_MONO,height=8,relief="flat",state="disabled"); self.log.pack(fill="both",expand=True,padx=16,pady=(0,12))
    def _log(self,msg): self.log.configure(state="normal"); self.log.insert("end",f"{msg}\n"); self.log.see("end"); self.log.configure(state="disabled")
    def _check(self):
        if not self.state.db_ready: messagebox.showwarning("DB","Database not ready"); return False
        return True
    def _save(self,rows,default_name,ext):
        os.makedirs(self.state.export_dir,exist_ok=True); path=filedialog.asksaveasfilename(defaultextension=f".{ext}",filetypes=[(f"{ext.upper()} file",f"*.{ext}")],initialdir=self.state.export_dir,initialfile=default_name)
        if not path: return
        try:
            if ext=="xlsx": DataExporter.to_excel_simple(rows,path)
            else: DataExporter.to_csv(rows,path)
            self._log(f"✅ Saved → {path}"); messagebox.showinfo("Exported",f"Saved to:\n{path}")
        except Exception as e: self._log(f"❌ {e}"); messagebox.showerror("Export Error",str(e))
    def _master_excel(self):
        if not self._check(): return
        os.makedirs(self.state.export_dir,exist_ok=True); path=filedialog.asksaveasfilename(defaultextension=".xlsx",filetypes=[("Excel","*.xlsx")],initialdir=self.state.export_dir,initialfile="AcadLib_Master_Report.xlsx")
        if not path: return
        try: DataExporter.to_excel_master(self.state.qlib,path); self._log(f"✅ Master Excel → {path}"); messagebox.showinfo("Done",f"Master report saved:\n{path}")
        except Exception as e: self._log(f"❌ {e}"); messagebox.showerror("Error",str(e))
    def _cgpa_csv(self):
        if not self._check(): return
        rows=self.state.qlib.rank_students_by_cgpa(); self._save(rows,"cgpa_rankings.csv","csv")
    def _fail_csv(self):
        if not self._check(): return
        rows=self.state.qlib.get_fail_report(); self._save(rows,"fail_report.csv","csv")
    def _stats_csv(self):
        if not self._check(): return
        rows=self.state.qlib.all_semester_stats(); self._save(rows,"semester_stats.csv","csv")

class SettingsPanel(ttk.Frame):
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self._build()
    def _build(self):
        ttk.Label(self,text="Settings",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Configure paths, AI integration, and export settings",style="Dim.TLabel").pack(anchor="w",padx=32,pady=(0,16)); card=make_card(self); card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(card,text="Data Paths",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6))
        self._vars={}
        for label,attr in [("JSON Records Directory","json_dir"),("Database File","db_path"),("Export Directory","export_dir")]:
            row=ttk.Frame(card,style="Card.TFrame"); row.pack(fill="x",padx=16,pady=4); ttk.Label(row,text=f"{label}:",style="Card.TLabel",width=24).pack(side="left"); v=tk.StringVar(value=getattr(self.state,attr)); self._vars[attr]=v; ttk.Entry(row,textvariable=v,width=44).pack(side="left",padx=(0,8)); ttk.Button(row,text="Browse",command=lambda a=attr:self._browse(a),width=8).pack(side="left")
        ttk.Frame(card,style="Card.TFrame",height=8).pack(); ai_card=make_card(self); ai_card.pack(fill="x",padx=32,pady=(0,12)); ttk.Label(ai_card,text="AI Agent",style="Head.TLabel").pack(anchor="w",padx=16,pady=(12,6)); row3=ttk.Frame(ai_card,style="Card.TFrame"); row3.pack(fill="x",padx=16,pady=(0,4)); ttk.Label(row3,text="OpenAI API Key:",style="Card.TLabel",width=20).pack(side="left"); self._key_var=tk.StringVar(value=self.state.openai_key); e=ttk.Entry(row3,textvariable=self._key_var,width=50,show="•"); e.pack(side="left",padx=(0,8)); ttk.Button(row3,text="Show",command=lambda:e.configure(show="" if e["show"] else "•"),width=6).pack(side="left")
        row4=ttk.Frame(ai_card,style="Card.TFrame"); row4.pack(fill="x",padx=16,pady=(0,12)); ttk.Label(row4,text="Model:",style="Card.TLabel",width=20).pack(side="left"); self._model_var=tk.StringVar(value=self.state.model); ttk.Combobox(row4,textvariable=self._model_var,width=20,values=["gpt-4o-mini","gpt-4o","gpt-3.5-turbo"]).pack(side="left"); ttk.Button(self,text="💾  Save Settings",command=self._save,style="Green.TButton",width=20).pack(anchor="w",padx=32,pady=(0,24))
    def _browse(self,attr): path=filedialog.askdirectory() if attr in ("json_dir","export_dir") else filedialog.asksaveasfilename(defaultextension=".db",filetypes=[("SQLite","*.db")]); self._vars[attr].set(path) if path else None
    def _save(self):
        for attr,v in self._vars.items(): setattr(self.state,attr,v.get())
        self.state.openai_key=self._key_var.get(); self.state.model=self._model_var.get(); self.state.save_settings(); messagebox.showinfo("Saved","Settings saved successfully.")

class SQLAgentPanel(ttk.Frame):
    PAGE_SIZE = 100
    def __init__(self,parent,state:AppState): super().__init__(parent); self.state=state; self.current_rows=[]; self._page=0; self._build()
    
    def _build(self):
        ttk.Label(self,text="SQL Agent Data Explorer",style="Title.TLabel").pack(anchor="w",padx=32,pady=(28,4)); ttk.Label(self,text="Ask natural language questions to generate instant data tables.",style="Dim.TLabel").pack(anchor="w",padx=32); inp_row=ttk.Frame(self,style="TFrame"); inp_row.pack(fill="x",padx=32,pady=(16,8)); self.query_var=tk.StringVar(); e=ttk.Entry(inp_row,textvariable=self.query_var,font=FONT_BODY,width=64); e.pack(side="left",fill="x",expand=True); e.bind("<Return>",lambda _:self._run_query()); ttk.Button(inp_row,text="Generate Data ▶",command=self._run_query,style="Accent.TButton",width=16).pack(side="left",padx=(8,0))
        toolbar=ttk.Frame(self,style="TFrame"); toolbar.pack(fill="x",padx=32,pady=(0,8)); self.btn_csv=ttk.Button(toolbar,text="📥 CSV",state="disabled",command=lambda:self._export('csv'),width=10); self.btn_csv.pack(side="left",padx=(0,4)); self.btn_excel=ttk.Button(toolbar,text="📊 Excel",state="disabled",command=lambda:self._export('xlsx'),width=10); self.btn_excel.pack(side="left",padx=(0,4)); self.status_lbl=ttk.Label(toolbar,text="",style="Dim.TLabel"); self.status_lbl.pack(side="right")
        
        tbl_card=make_card(self); tbl_card.pack(fill="both",expand=True,padx=32,pady=(0,24))
        tbl_card.grid_columnconfigure(0, weight=1); tbl_card.grid_rowconfigure(1, weight=1)
        
        page_bar = ttk.Frame(tbl_card, style="Card.TFrame")
        page_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.btn_prev = ttk.Button(page_bar, text="◀ Prev", command=self._prev_page, width=8); self.btn_prev.pack(side="left", padx=2)
        self.btn_next = ttk.Button(page_bar, text="Next ▶", command=self._next_page, width=8); self.btn_next.pack(side="left", padx=2)
        self.page_lbl = ttk.Label(page_bar, text="", style="Dim.TLabel"); self.page_lbl.pack(side="left", padx=8)

        tree_container = ttk.Frame(tbl_card, style="TFrame")
        tree_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))

        self.tree=ttk.Treeview(tree_container,show="headings"); vsb=ttk.Scrollbar(tree_container,orient="vertical",command=self.tree.yview); hsb=ttk.Scrollbar(tree_container,orient="horizontal",command=self.tree.xview); self.tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set); vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x"); self.tree.pack(fill="both",expand=True); self.tree.tag_configure("odd",background=THEME["bg"]); self.tree.tag_configure("even",background=THEME["card_bg"])

    def _run_query(self):
        q=self.query_var.get().strip(); 
        if not q: return
        if not self.state.agent: messagebox.showerror("Error","AI Agent not initialized. Go to the Database panel."); return
        for btn in (self.btn_csv,self.btn_excel): btn.configure(state="disabled")
        self.status_lbl.configure(text="⏳ AI Agent is analyzing…")
        for item in self.tree.get_children(): self.tree.delete(item)
        self.tree["columns"]=()
        
        def task():
            try:
                result=self.state.agent.invoke({"input":f"Generate SQL and return data for: '{q}'"}); steps=result.get("intermediate_steps",[]); last_sql=None
                for action,obs in steps:
                    if getattr(action,'tool','')=="sql_db_query":
                        t_in=getattr(action,'tool_input',''); last_sql=t_in.get("query") if isinstance(t_in,dict) else t_in
                if last_sql: rows=self.state.qlib._run(last_sql); self.after(0,lambda:self._update_table(rows))
                else: self.after(0,lambda:self.status_lbl.configure(text="❌ No SQL data returned."))
            except Exception as e: self.after(0,lambda:self.status_lbl.configure(text=f"❌ Error: {str(e)[:60]}"))
        threading.Thread(target=task,daemon=True).start()

    def _update_table(self,rows):
        self.current_rows=rows
        if not rows: self.status_lbl.configure(text="⚠️ Query returned 0 rows."); return
        cols=list(rows[0].keys()); self.tree["columns"]=cols
        for col in cols: self.tree.heading(col,text=col.replace("_"," ").title()); self.tree.column(col,width=max(80,min(200,len(col)*11)))
        
        self._page = 0
        self._render_page()
        for btn in (self.btn_csv,self.btn_excel): btn.configure(state="normal")

    def _render_page(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        self.tree.update_idletasks()
        
        if not self.current_rows:
            self.page_lbl.configure(text="No data"); self.status_lbl.configure(text="0 rows")
            self.btn_prev.state(["disabled"]); self.btn_next.state(["disabled"])
            return
            
        start = self._page * self.PAGE_SIZE; chunk = self.current_rows[start : start + self.PAGE_SIZE]
        n_pages = max(1, (len(self.current_rows) - 1) // self.PAGE_SIZE + 1)
        
        cols = list(self.current_rows[0].keys())
        for i,r in enumerate(chunk): self.tree.insert("","end",values=[r.get(c,"") for c in cols],tags=("odd" if i%2==0 else "even",))
        
        self.page_lbl.configure(text=f"Rows {start+1}–{start+len(chunk)} of {len(self.current_rows)}  (Page {self._page+1}/{n_pages})")
        self.status_lbl.configure(text=f"✓ Total: {len(self.current_rows)} rows")
        self.btn_prev.state(["disabled"] if self._page <= 0 else ["!disabled"])
        self.btn_next.state(["disabled"] if self._page >= n_pages - 1 else ["!disabled"])

    def _prev_page(self):
        if self._page > 0: self._page -= 1; self._render_page()
    def _next_page(self):
        if self._page < (len(self.current_rows) - 1) // self.PAGE_SIZE: self._page += 1; self._render_page()

    def _export(self,fmt):
        if not self.current_rows: return
        os.makedirs(self.state.export_dir,exist_ok=True); ext="csv" if fmt=="csv" else "xlsx"; path=filedialog.asksaveasfilename(defaultextension=f".{ext}",filetypes=[(f"{ext.upper()}",f"*.{ext}")],initialdir=self.state.export_dir)
        if not path: return
        try:
            if fmt=="csv": DataExporter.to_csv(self.current_rows,path)
            else: DataExporter.to_excel_simple(self.current_rows,path)
            messagebox.showinfo("Exported",f"Saved → {path}")
        except Exception as e: messagebox.showerror("Export Error",str(e))


class ChatbotPanel(ttk.Frame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent); self.state = state; self._is_processing = False; self._orch = None; self._build()
    
    def _build(self):
        hdr = ttk.Frame(self, style="TFrame"); hdr.pack(fill="x", padx=20, pady=(16,4))
        ttk.Label(hdr, text="AI Assistant", style="Title.TLabel").pack(side="left")
        
        self._pw = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=THEME["border"], sashwidth=5, sashrelief="flat", handlesize=0); self._pw.pack(fill="both", expand=True)
        self._left_frame = tk.Frame(self._pw, bg=THEME["bg"]); self._right_frame = tk.Frame(self._pw, bg=THEME["ws_bg"])
        self._pw.add(self._left_frame, minsize=400, stretch="always"); self._pw.add(self._right_frame, minsize=0, stretch="always")
        
        self._build_chat(self._left_frame)
        from ui import WorkspaceManager 
        self._ws_mgr = WorkspaceManager(self._pw, self._right_frame, left_min=400); self._orch = EnterpriseOrchestrator(self.state, self._ws_mgr, self.after)
        self.after(150, self._collapse_workspace)

    def _collapse_workspace(self):
        try: w = self._pw.winfo_width(); self._pw.sash_place(0, w-2, 0) if w > 100 else None
        except: pass

    def _toggle_workspace(self):
        try:
            total = self._pw.winfo_width(); sash = self._pw.sash_coord(0)[0]
            if sash >= total-10: self._pw.sash_place(0, max(380, total//2), 0)
            else: self._pw.sash_place(0, total-2, 0)
        except: pass

    def _build_chat(self, parent):
        chat_card = make_card(parent); chat_card.pack(fill="both", expand=True, padx=10, pady=(8,4))
        self.chat_display = scrolledtext.ScrolledText(chat_card, bg=THEME["bg"], fg=THEME["text"], font=FONT_BODY, height=16, relief="flat", state="disabled", wrap=tk.WORD, padx=20, pady=16)
        self.chat_display.pack(fill="both", expand=True)
        
        # --- CLEAN GEOMETRY ALIGNMENT TAGS ---
        self.chat_display.tag_configure("user", foreground=THEME["text_bright"], font=("Segoe UI", 10, "bold"), justify="right", rmargin=15, lmargin1=100, lmargin2=100, spacing1=10, spacing3=2)
        self.chat_display.tag_configure("bot", foreground=THEME["text_bright"], font=("Segoe UI", 10), justify="left", lmargin1=15, lmargin2=15, rmargin=100, spacing1=4, spacing3=2)
        self.chat_display.tag_configure("system", foreground=THEME["text_dim"], font=("Segoe UI", 9, "italic"), justify="center", spacing1=15, spacing3=15)
        self.chat_display.tag_configure("success", foreground=THEME["success"], font=("Segoe UI", 10, "bold"), justify="left", lmargin1=15, spacing1=10, spacing3=10)
        self.chat_display.tag_configure("error", foreground=THEME["error"], font=("Segoe UI", 10), justify="left", lmargin1=15, spacing3=10)
        self.chat_display.tag_configure("thinking", foreground=THEME["warning"], font=("Segoe UI", 9, "italic"), justify="left", lmargin1=15, spacing1=10, spacing3=10)

        sq_row = tk.Frame(parent, bg=THEME["bg"]); sq_row.pack(fill="x", padx=10, pady=(0,4))
        tk.Label(sq_row, text="Quick:", bg=THEME["bg"], fg=THEME["text_dim"], font=FONT_SMALL).pack(side="left", padx=(0,6))
        
        SAMPLE_QUERIES = ["Topper of semester 5", "Fail report for semester 3", "List all students from sem 5"]
        for q in SAMPLE_QUERIES: ttk.Button(sq_row, text=q[:22]+"…" if len(q)>22 else q, command=lambda x=q: self._send_query(x), style="TButton").pack(side="left", padx=(0,3))
        
        ws_row = tk.Frame(parent, bg=THEME["bg"]); ws_row.pack(fill="x", padx=10, pady=(0,4))
        ttk.Button(ws_row, text="◀▶ Toggle Workspace", command=self._toggle_workspace, style="TButton").pack(side="right")
        ttk.Button(ws_row, text="✕ Close", command=lambda: self._ws_mgr.close(), style="TButton").pack(side="right", padx=(0,4))

        inp_row = tk.Frame(parent, bg=THEME["bg"]); inp_row.pack(fill="x", padx=10, pady=(0,12))
        self._input_var = tk.StringVar(); self._entry = ttk.Entry(inp_row, textvariable=self._input_var, font=FONT_BODY, width=52); self._entry.pack(side="left", padx=(0,8), fill="x", expand=True); self._entry.bind("<Return>", lambda _: self._send()); self._send_btn = ttk.Button(inp_row, text="Send ▶", command=self._send, style="Accent.TButton", width=10); self._send_btn.pack(side="left", padx=(0,6))
        ttk.Button(inp_row, text="Clear", command=self._clear, style="TButton", width=7).pack(side="left")
        
        self._chat("system", "How can I help you today?")

    # --- CHAT RENDERING ENGINE WITH STREAMING SUPPORT ---
    def _chat(self, tag, msg):
        if tag in ("bot", "success") and "\n" in msg:
            lines = msg.split("\n")
            self._animate_lines(lines, tag, 0)
        else:
            self.chat_display.configure(state="normal")
            self.chat_display.insert(tk.END, f"{msg.strip()}\n", tag)
            self.chat_display.see(tk.END)
            self.chat_display.configure(state="disabled")

    # Non-blocking sequential line animator loop
    def _animate_lines(self, lines, tag, index):
        if index < len(lines):
            self.chat_display.configure(state="normal")
            line = lines[index]
            # Strip extra spaces but preserve deliberate structures like tab lists
            self.chat_display.insert(tk.END, f"{line}\n", tag)
            self.chat_display.see(tk.END)
            self.chat_display.configure(state="disabled")
            
            # 45ms pause between lines simulates typical high-speed LLM token streaming
            self.after(45, lambda: self._animate_lines(lines, tag, index + 1))

    def _send(self):
        q = self._input_var.get().strip(); 
        if q: self._input_var.set(""); self._send_query(q)

    def _send_query(self, question: str):
        if self._is_processing: self._chat("error","⏳ Please wait — a query is running…"); return
        if not self.state.db_ready: self._chat("error","❌ Database not ready. Go to Database → Rebuild."); return
        if not self._orch: self._chat("error","❌ Orchestrator not ready."); return
        
        self._is_processing = True; self._set_busy(True)
        self._chat("user", question)
        self._chat("thinking", "⏳ Thinking…")
        self.state.chat_history.append(("user", question))
        
        def run():
            try:
                report, message, result = self._orch.run(question, chat_cb=lambda t,m: self.after(0, lambda tt=t, mm=m: self._chat(tt, mm)))
                self.state.chat_history.append(("assistant", message or "")); 
                if len(self.state.chat_history) > 12: self.state.chat_history = self.state.chat_history[-12:]
                self.after(0, lambda m=message,r=result,rp=report: self._on_smart(m, r, rp))
            except Exception as e: self.after(0, lambda err=str(e): self._on_error(err))
        threading.Thread(target=run, daemon=True).start()

    def _on_smart(self, message, result, report: ExecutionReport):
        self._remove_thinking()
        if message: self._chat("bot", message)
        if result: self._chat("success", f"✅ {result}")
        self._is_processing = False; self._set_busy(False)

    def _on_error(self, msg: str):
        self._remove_thinking()
        self._chat("error", f"❌ {msg[:300]}")
        self._is_processing = False; self._set_busy(False)

    def _remove_thinking(self):
        try:
            self.chat_display.configure(state="normal")
            pos = self.chat_display.search("⏳ Thinking…", "1.0", tk.END)
            if pos: 
                start = self.chat_display.index(f"{pos} linestart")
                end = self.chat_display.index(f"{pos} lineend + 1c")
                self.chat_display.delete(start, end)
            self.chat_display.configure(state="disabled")
        except: pass

    def _set_busy(self, busy: bool):
        s = "disabled" if busy else "normal"
        try: self._send_btn.configure(state=s); self._entry.configure(state=s)
        except: pass

    def _clear(self):
        if self._is_processing: return
        self.chat_display.configure(state="normal"); self.chat_display.delete("1.0", tk.END); self.chat_display.configure(state="disabled"); self.state.chat_history.clear()
        if self._orch: self._orch.clear()
        self._ws_mgr.close()
        self._chat("system","👋 Workspace cleared. Context reset. Ask me anything!")