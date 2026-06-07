import os, sys, json, logging
from logging.handlers import RotatingFileHandler

# --- ENTERPRISE LOGGING SETUP ---
os.makedirs(os.path.expanduser("~/aktu_data/logs"), exist_ok=True)
log_file = os.path.expanduser("~/aktu_data/logs/acadlib.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AcadLib")

# --- THEME & CONSTANTS ---
THEME = {
    "bg":           "#0F1117", "sidebar_bg":   "#161B22", "card_bg":      "#1C2128",
    "border":       "#30363D", "accent":       "#238636", "accent2":      "#1F6FEB",
    "accent3":      "#A371F7", "accent4":      "#F78166", "text":         "#E6EDF3",
    "text_dim":     "#7D8590", "text_bright":  "#FFFFFF", "success":      "#3FB950",
    "warning":      "#D29922", "error":        "#F85149", "hover":        "#21262D",
    "selected":     "#1C2C42", "ws_bg":        "#13161D", "ws_header":    "#1A1F29",
}

SIDEBAR_W  = 220
TOPBAR_H   = 56
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_HEAD  = ("Segoe UI", 11, "bold")
FONT_BODY  = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO  = ("Cascadia Code", 10) if sys.platform == "win32" else ("Courier New", 10)

GRADE_COLORS = {
    "A+": "#3FB950", "A": "#56D364", "B+": "#388BFD", "B":  "#79C0FF", 
    "C": "#E3B341", "D":  "#D29922", "E":  "#F85149", "E#":"#DA3633", "F":  "#8B0000",
}

class AppState:
    def __init__(self):
        self.json_dir   = os.path.expanduser("~/aktu_data/json")
        self.db_path    = os.path.expanduser("~/aktu_data/university.db")
        self.export_dir = os.path.expanduser("~/aktu_data/exports")
        self.openai_key = ""
        self.model      = "gpt-4o-mini"
        self.db_ready   = False
        self.qlib       = None
        self.agent      = None
        self.chat_history = []
        self._load_settings()

    def _settings_path(self): return os.path.expanduser("~/aktu_data/settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path()) as f: d=json.load(f)
            self.json_dir   = d.get("json_dir",self.json_dir)
            self.db_path    = d.get("db_path",self.db_path)
            self.export_dir = d.get("export_dir",self.export_dir)
            self.openai_key = d.get("openai_key","")
            self.model      = d.get("model","gpt-4o-mini")
        except Exception as e:
            logger.warning(f"Could not load settings, using defaults. ({e})")

    def save_settings(self):
        os.makedirs(os.path.dirname(self._settings_path()),exist_ok=True)
        try:
            with open(self._settings_path(),"w") as f:
                json.dump({"json_dir":self.json_dir,"db_path":self.db_path,
                           "export_dir":self.export_dir,"openai_key":self.openai_key,"model":self.model},f,indent=2)
            logger.info("Settings saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def init_db_and_qlib(self):
        from database import QueryLibrary
        if os.path.exists(self.db_path):
            self.qlib=QueryLibrary(self.db_path); self.db_ready=True
            logger.info("Database connection initialized.")
        return self.db_ready

    def rebuild_db(self):
        from database import build_database, QueryLibrary
        if self.qlib:
            try: self.qlib.close()
            except Exception as e: logger.error(f"Error closing DB: {e}")
        os.makedirs(os.path.dirname(self.db_path),exist_ok=True)
        logger.info("Starting database rebuild process...")
        n=build_database(self.json_dir,self.db_path)
        self.qlib=QueryLibrary(self.db_path); self.db_ready=True
        logger.info(f"Database rebuild complete. Processed {n} records.")
        return n

    def init_agent(self):
        if not self.openai_key: return False
        try:
            from langchain_community.utilities import SQLDatabase
            from langchain_community.agent_toolkits import create_sql_agent
            from langchain_openai import ChatOpenAI
            import sqlite3
            os.environ["OPENAI_API_KEY"]=self.openai_key
            safe_db_path=self.db_path.replace("\\","/")
            db=SQLDatabase.from_uri(f"sqlite:///{safe_db_path}",sample_rows_in_table_info=3)
            llm=ChatOpenAI(model=self.model,temperature=0)
            
            # Contextual Schema Injection for Agent Hallucination Prevention
            conn_tmp=sqlite3.connect(self.db_path)
            n_students=conn_tmp.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            n_subjects=conn_tmp.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
            schema_text = ""
            for tbl in ["students", "semesters", "subjects"]:
                cur = conn_tmp.execute(f"PRAGMA table_info({tbl})")
                schema_text += f"- {tbl}: {', '.join([r[1] for r in cur.fetchall()])}\n"
            conn_tmp.close()

            top_k=max(n_students,min(n_subjects,500))
            system_prompt=(f"You are a precise SQL analyst for AKTU academic records.\n"
                           f"DATABASE: {n_students} students, {n_subjects} subjects.\n"
                           f"SCHEMA:\n{schema_text}\n"
                           "Use pre-computed cgpa/failed_subjects from students table.\n"
                           "NEVER fabricate columns. Use LIKE for name searches.")
            try:
                self.agent=create_sql_agent(llm,db=db,agent_type="openai-tools",verbose=False,
                    top_k=top_k,max_iterations=15,prefix=system_prompt,
                    agent_executor_kwargs={"return_intermediate_steps":True})
            except TypeError:
                self.agent=create_sql_agent(llm,db=db,agent_type="tool-calling",verbose=False,
                    top_k=top_k,max_iterations=15,
                    agent_executor_kwargs={"return_intermediate_steps":True})
            logger.info("AI SQL Agent initialized successfully.")
            return True
        except Exception as e:
            self.last_agent_error=str(e)
            logger.error(f"Failed to initialize AI Agent: {e}", exc_info=True)
            return False