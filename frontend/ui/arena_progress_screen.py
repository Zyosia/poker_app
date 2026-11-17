"""Progress of a fast Bot Arena run, simulated off the Qt main thread."""

import threading
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.simulation.config import SimulationConfig, StackPolicy
from backend.simulation.result import SimulationResult
from backend.simulation.runner import SimulationCancelled, run_simulation
from backend.simulation.tournament_runner import (
    TournamentRunConfig,
    TournamentRunResult,
    run_tournaments,
)

ArenaConfig = SimulationConfig | TournamentRunConfig
ArenaResult = SimulationResult | TournamentRunResult


class SimulationThread(QThread):
    """Runs a simulation (and its worker pool) in the background.

    Its signals are delivered on the main thread, where the screen lives.
    """

    progressed = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, config: ArenaConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            result: ArenaResult

            if isinstance(self.config, TournamentRunConfig):
                result = run_tournaments(
                    self.config, progress=self.progressed.emit, cancel=self.cancel_event
                )
            else:
                result = run_simulation(
                    self.config,
                    progress=self.progressed.emit,
                    cancel=self.cancel_event,
                )
        except SimulationCancelled:
            self.cancelled.emit()
        except Exception as error:  # noqa: BLE001 - reported to the user
            # Any failure (an invariant broken, a bot error) must reach the
            # screen instead of dying silently with the thread.
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.succeeded.emit(result)


class ArenaProgressScreen(QWidget):
    """Shows the progress of a run and lets the user cancel it."""

    finished = Signal(object)
    """Emitted with the ``SimulationResult`` or ``TournamentRunResult``."""
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.simulation_thread: SimulationThread | None = None
        self._started_at = 0.0
        self._unit = "hands"

        title = QLabel("Simulating…")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label = QLabel()
        self.description_label.setObjectName("subtitle")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.speed_label = QLabel()
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label = QLabel()
        self.error_label.setObjectName("errorText")
        self.error_label.setWordWrap(True)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setMinimumHeight(44)
        self.cancel_button.clicked.connect(self.cancel)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(560)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 24, 28, 24)
        panel_layout.setSpacing(14)
        panel_layout.addWidget(self.progress_bar)
        panel_layout.addWidget(self.speed_label)
        panel_layout.addWidget(self.error_label)
        panel_layout.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.description_label)
        layout.addSpacing(20)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    @property
    def is_running(self) -> bool:
        return self.simulation_thread is not None and self.simulation_thread.isRunning()

    def start(self, config: ArenaConfig) -> None:
        """Start simulating ``config`` in the background."""
        if self.is_running:
            raise RuntimeError("A simulation is already running.")

        if isinstance(config, TournamentRunConfig):
            unit = "tournaments"
        elif config.stack_policy == StackPolicy.ELIMINATION:
            unit = "sessions"
        else:
            unit = "hands"

        seats = ", ".join(config.seat_names)
        self.description_label.setText(f"{seats} — {config.workers} worker(s)")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"%v / %m {unit}")
        self.speed_label.setText("Starting the workers…")
        self.error_label.clear()
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self._unit = unit
        self._started_at = time.perf_counter()

        thread = SimulationThread(config, self)
        thread.progressed.connect(self._on_progress)
        thread.succeeded.connect(self._on_succeeded)
        thread.cancelled.connect(self._on_cancelled)
        thread.failed.connect(self._on_failed)
        self.simulation_thread = thread
        thread.start()

    def cancel(self) -> None:
        """Stop the run; ``cancelled`` is emitted once the workers stopped."""
        if self.is_running and self.simulation_thread is not None:
            self.simulation_thread.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.speed_label.setText("Stopping the workers…")
        elif self.error_label.text():
            self.cancelled.emit()

    def wait(self, timeout_ms: int = 30_000) -> bool:
        """Block until the background run is over (used when closing)."""
        return self.simulation_thread is None or self.simulation_thread.wait(timeout_ms)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        elapsed = time.perf_counter() - self._started_at
        rate = done / elapsed if elapsed > 0 else 0.0
        remaining = (total - done) / rate if rate > 0 else 0.0
        self.speed_label.setText(
            f"{rate:,.0f} {self._unit}/s   ·   {remaining:,.0f} s remaining".replace(
                ",", " "
            )
        )

    def _finish_thread(self) -> None:
        """Release a finished run's thread (it has stopped: wait returns)."""
        if self.simulation_thread is not None:
            self.simulation_thread.wait()
            self.simulation_thread.deleteLater()
            self.simulation_thread = None

    def _on_succeeded(self, result: ArenaResult) -> None:
        self._finish_thread()
        self.finished.emit(result)

    def _on_cancelled(self) -> None:
        self._finish_thread()
        self.cancelled.emit()

    def _on_failed(self, message: str) -> None:
        self._finish_thread()
        self.error_label.setText(message)
        self.speed_label.setText("The simulation stopped with an error.")
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Back to setup")
        self.failed.emit(message)
