"""Stitch-inspired prompt surface for generating complete application projects."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sketchforge.generation.studio_generator import generate_studio_project
from sketchforge.utilities.paths import repo_root


class GenerationPanel(QWidget):
    """Prompt-driven frontend and optional SQLite-backend project generator."""

    project_ready = Signal(str)
    generation_failed = Signal(str)
    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("generationPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(11)

        brand = QLabel("✳  SKETCHFORGE STUDIO")
        brand.setObjectName("eyebrow")
        layout.addWidget(brand)
        title = QLabel("What would you like\nto bring to life?")
        title.setObjectName("generationTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        intro = QLabel("Start with an idea, a workflow, or a sketch. Your frontend and backend live together in one project.")
        intro.setObjectName("mutedText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName("generationPrompt")
        self.prompt.setPlaceholderText("A warm, modern client portal for a small creative studio…")
        self.prompt.setFixedHeight(130)
        layout.addWidget(self.prompt)

        self.backend = QCheckBox("Add a Python + SQLite backend")
        self.backend.setChecked(True)
        self.backend.setToolTip("Generate backend models, schema, database helpers, CRUD logic, and tests.")
        layout.addWidget(self.backend)

        self.generate_button = QPushButton("✦   Generate full stack")
        self.generate_button.setObjectName("generateButton")
        self.generate_button.clicked.connect(self.generate)
        layout.addWidget(self.generate_button)

        row = QHBoxLayout()
        self.choose_button = QPushButton("Choose output folder…")
        self.choose_button.setObjectName("quietButton")
        self.choose_button.clicked.connect(self.choose_output_folder)
        self.output_label = QLabel("output/projects")
        self.output_label.setObjectName("mutedText")
        self.output_label.setWordWrap(True)
        row.addWidget(self.choose_button)
        layout.addLayout(row)
        layout.addWidget(self.output_label)

        separator = QLabel("✦  QUICK STARTS")
        separator.setObjectName("eyebrow")
        layout.addSpacing(6)
        layout.addWidget(separator)
        for suggestion in (
            "A simple dashboard for tracking my team projects",
            "A booking page for a neighborhood coffee shop",
            "A personal finance tracker with monthly goals",
        ):
            button = QPushButton(suggestion)
            button.setObjectName("suggestionButton")
            button.setMinimumHeight(42)
            button.setStyleSheet("text-align: left; white-space: normal;")
            button.clicked.connect(lambda _checked=False, text=suggestion: self.prompt.setPlainText(text))
            layout.addWidget(button)

        layout.addStretch(1)
        self.recent = QLabel("YOUR WORKSPACE\n\nGenerated projects appear in the preview and project folder.")
        self.recent.setObjectName("workspaceHint")
        self.recent.setWordWrap(True)
        layout.addWidget(self.recent)
        self._output_base = repo_root() / "output" / "projects"

    def choose_output_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose generated project folder", str(self._output_base))
        if path:
            self._output_base = Path(path)
            self.output_label.setText(str(self._output_base))

    def generate(self) -> None:
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.status_message.emit("Add a short description before generating your app.")
            self.prompt.setFocus()
            return
        self.generate_button.setEnabled(False)
        self.generate_button.setText("◌   Building your project…")
        self.status_message.emit("Generating frontend and backend files…")
        try:
            root = generate_studio_project(prompt, self._output_base,
                                          include_backend=self.backend.isChecked())
        except (OSError, ValueError, RuntimeError) as exc:
            self.status_message.emit(f"Could not generate the project: {exc}")
            self.generation_failed.emit(str(exc))
        else:
            self.recent.setText(f"LATEST PROJECT\n\n{root.name}\n{len(list(root.rglob('*.*')))} generated files\n{root}")
            self.project_ready.emit(str(root))
            self.status_message.emit(f"Generated {root.name} with frontend and {'SQLite backend scaffold' if self.backend.isChecked() else 'no backend'}.")
        finally:
            self.generate_button.setEnabled(True)
            self.generate_button.setText("✦   Generate full stack")
