import os
import tkinter as tk
from tkinter import ttk
from config import THEME, AppState
from ui import (
    Sidebar, DashboardPanel, UploadF1Panel, UploadF2Panel, DatabasePanel, 
    StudentsPanel, AnalyticsPanel, ChatbotPanel, SQLAgentPanel, 
    ExportPanel, SettingsPanel, apply_theme
)
class App(tk.Tk):
    PANELS = {
        "Dashboard":  DashboardPanel,
        "Upload F1":  UploadF1Panel,
        "Upload F2":  UploadF2Panel,
        "Database":   DatabasePanel,
        "Students":   StudentsPanel,
        "Analytics":  AnalyticsPanel,
        "Chatbot":    ChatbotPanel,
        "SQL Studio": SQLAgentPanel,
        "Export":     ExportPanel,
        "Settings":   SettingsPanel,
    }

    def __init__(self):
        super().__init__()
        self.title("AcadLib — University Records System [MVC Structured]")
        self.geometry("1360x820")
        self.minsize(1024, 650)
        apply_theme(self)
        self.configure(bg=THEME["bg"])
        
        self.state = AppState()
        self.state.init_db_and_qlib()
        
        self._panels = {}
        self._current = None
        self._build()
        self.sidebar.select("Dashboard")
        
        for ev, name in [("<<Nav_Upload F1>>", "Upload F1"), ("<<Nav_Upload F2>>", "Upload F2"),
                         ("<<Nav_Database>>", "Database"), ("<<Nav_Chatbot>>", "Chatbot")]:
            self.bind(ev, lambda _, n=name: self.sidebar.select(n))

    def _build(self):
        self.sidebar = Sidebar(self, self._on_nav)
        self.sidebar.pack(side="left", fill="y")
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=THEME["bg"])
        self.content.pack(side="left", fill="both", expand=True)

    def _on_nav(self, name: str):
        if self._current: self._current.pack_forget()
        if name not in self._panels:
            cls = self.PANELS.get(name)
            if cls:
                panel = cls(self.content, self.state)
                self._panels[name] = panel
        panel = self._panels.get(name)
        if panel:
            panel.pack(fill="both", expand=True)
            self._current = panel
        if name == "Dashboard" and hasattr(panel, "refresh"): panel.refresh()
        if name == "Chatbot" and hasattr(panel, "_refresh_status"): panel._refresh_status()

if __name__ == "__main__":
    os.makedirs(os.path.expanduser("~/aktu_data/json"),    exist_ok=True)
    os.makedirs(os.path.expanduser("~/aktu_data/exports"), exist_ok=True)
    app = App()
    app.mainloop()