# AcadLib — Enterprise Academic Records & Analytics Orchestration Engine

AcadLib is a high-throughput, multi-threaded academic intelligence and records extraction system designed to parse, aggregate, normalize, and verify unstructured engineering tabulation ledgers and transcripts. Built on a clean decoupling of presentation logic and analytical execution layers (Model-View-Controller architecture), the engine provides automated data transformation pipelines alongside an autonomous, deterministic natural language execution space.

---

## 👥 System Capabilities & Architecture

The framework is architected to scale safely across volatile local database footprints containing over **500,000+ relational student entities** without memory growth or data fragmentation.

+------------------------------------------------------------+
|                       Tkinter View Layer                   |
|   - Virtualized Treeviews with Database Pagination Loop     |
|   - Non-Blocking Micro-Delayed Line Animation Workspace    |
+------------------------------------------------------------+
|
v (Thread-Isolated Event Loops)
+------------------------------------------------------------+
|               EnterpriseOrchestrator Backend               |
|   - Deterministic Intent Classification Engine             |
|   - Linear Workflow Dependency Graph Constructor          |
|   - Verification Engine (Fetch-to-Render Ratio Logic)       |
+------------------------------------------------------------+
|
v (Thread-Safe Shared Reentrant Locks)
+------------------------------------------------------------+
|                 Relational Persistence Layer               |
|   - SQLite persistency tuned with Write-Ahead Logging (WAL) |
|   - Memory-safe bounded Dataset Stack Optimization          |
+------------------------------------------------------------+


### 🧠 Core Architectural Components

#### 1. Multi-Step Execution & Graph Planning (`ai_core.py`)
Queries traveling through the conversational assistant are compiled into an execution plan. The `MultiStepWorkflowPlanner` evaluates the user's explicit intent alongside active window tokens, dynamically injecting structural tasks into a dependency string (`Producer → Consumer → Verifier → Renderer`).

#### 2. Persistence Layer with Concurrent Protection (`database.py`)
Persistent storage is handled via an optimized SQLite engine engineered to survive asynchronous context switching.
* **Write-Ahead Logging (WAL):** Enabled natively to safely permit concurrent reading operations while a background pipeline executes high-volume data writes.
* **Concurrency Locking Strategy:** Implements `threading.RLock()` across core query APIs. This thread-isolation mechanism prevents structural cross-contamination or internal memory corruption when an active user query interrupts a system database update.

#### 3. Real Database-Driven Pagination Layout (`ui.py`)
To prevent out-of-memory (OOM) faults on enormous academic bodies, user navigation maps do not retain bulk memory tables. The system utilizes automated data slicing directly through strict `LIMIT` and `OFFSET` parameters inside SQL persistency loops. 

#### 4. Context Retention Layer & Bounded Datasets (`models.py`)
Linear continuity across queries (e.g., matching a sequence like `"Show topper sem 5"` followed by `"Convert their scale to 4"`) is guarded by a memory-safe `DatasetStack`. The stack enforces a boundary constraint (`MAX_DEPTH = 12`) and clamps transient records to a limit of `150` items inside tracking nodes, freeing garbage collection pools while preserving parent data derivation lines.

---

## 🛠️ Installation & Microservice Deployment

### Prerequisites
* Python 3.10 or higher
* SQLite 3.36+ (packaged implicitly within Python standard runtime)

### 1. Environment Initialization
Clone the repository and spin up an isolated virtual execution container:
```bash
git clone [https://github.com/NIKHILUTTAM/AcadLib.git](https://github.com/NIKHILUTTAM/AcadLib.git)
cd AcadLib

# Initialize structural virtual space
python -m venv .venv
source .venv/Scripts/activate  # On Windows: .venv\Scripts\activate
2. Dependency Resolution
Install necessary processing engines using the project manifest:

Bash
pip install -r requirements.txt
3. Persistency Footprint Allocation
The database and internal engine metrics write directly onto your system's localized data space. Run main.py to create the default structural system mapping:

Bash
python main.py
This routine automatically builds out the core data repository under the user path:
~/aktu_data/{json/, exports/, logs/}

🚀 Binary Compilation (Creating Shared .exe Distribution)
To securely compile the system application into a single executable application node for external client systems, deploy the specialized compilation process through PyInstaller. This command groups asset resources and builds deep asset collection hooks for dynamic packages:

Bash
pyinstaller --noconfirm --onefile --windowed \
  --name "AcadLib" \
  --collect-all langchain \
  --collect-all langchain_community \
  --collect-all openai \
  --collect-all pandas \
  --collect-all matplotlib \
  main.py
The production-hardened binary node will compile directly into the newly provisioned ./dist/ directory.

📊 Relational Database Schema Design
Persisted academic transcripts are mapped across strict structural constraint lines to guarantee high third-normal form normalization and clean joining performance:

SQL
CREATE TABLE students (
    id INTEGER PRIMARY KEY,
    name TEXT COLLATE NOCASE,
    roll_number TEXT UNIQUE,
    enrollment_number TEXT,
    institute_code TEXT,
    institute_name TEXT COLLATE NOCASE,
    course TEXT,
    branch TEXT COLLATE NOCASE,
    gender TEXT,
    father_name TEXT COLLATE NOCASE,
    source_file TEXT,
    cgpa REAL,
    semesters_completed INTEGER,
    failed_subjects INTEGER
);

CREATE TABLE semesters (
    id INTEGER PRIMARY KEY,
    student_id INTEGER,
    semester_number INTEGER,
    even_odd TEXT,
    session TEXT,
    sgpa REAL,
    total_marks_obtained REAL,
    result_status TEXT,
    date_of_declaration TEXT,
    total_subjects INTEGER,
    FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE subjects (
    id INTEGER PRIMARY KEY,
    semester_id INTEGER,
    subject_code TEXT COLLATE NOCASE,
    subject_name TEXT COLLATE NOCASE,
    subject_type TEXT,
    internal_marks REAL,
    external_marks REAL,
    total_marks REAL,
    back_paper_marks REAL,
    grade TEXT,
    FOREIGN KEY(semester_id) REFERENCES semesters(id) ON DELETE CASCADE
);