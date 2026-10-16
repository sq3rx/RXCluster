# Agent Guidelines for Python Project

## Core Scope & Execution Principles
- **Local Project Directory Only:** All operations, files, and workspace context must strictly remain within the current project directory. Do not attempt to access, write, or modify system files outside of this folder. 📁
- **Python Virtual Environment (`venv`) Strictly Required:** **All operations, script executions, and terminal commands MUST be performed exclusively within the active Python virtual environment (`venv`).** 🐍
- **Isolated Installations Only:** **You are ALLOWED to install new packages (e.g., using `pip install`), but strictly and ONLY within the active `venv`.** **Never attempt to install, modify, or add any dependencies globally or at the system level.** 🛑
- **Focus on Architecture & Logic:** Focus your efforts on generating clean, precise, and modular Python code, maintaining good architectural practices. 🏗️

## Language & Documentation Standards
- **English Only for Technical Content:** All Python code, docstrings, inline comments, commit messages, and project documentation must be written strictly in **English**. 🎨

## Output & Delivery Format
Whenever you create or modify Python scripts:
1. **File Updates:** Keep the project's primary `.py` files up to date with the latest state, ensuring no breaking changes to existing modules. 🔄
2. **Ready-to-Use Code:** Always provide the **full, complete Python code snippets** for any new functions or modified classes directly in your response so the user can quickly copy and paste them. 📋
3. **Integration Instructions:** Always provide **explicit, step-by-step instructions** on how to integrate the newly added or updated code within the existing project structure and how to call the functions. 🔗