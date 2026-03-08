"""Run Surface Evolver subprocess and manage execution."""

import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EvolverResult:
    """Result from a Surface Evolver run."""

    success: bool
    dump_file: Optional[Path]
    stdout: str
    stderr: str
    elapsed_seconds: float
    final_energy: Optional[float] = None
    final_volume: Optional[float] = None


class EvolverRunner:
    """Execute Surface Evolver and manage processes."""

    def __init__(self, evolver_path: Optional[str | Path] = None):
        if evolver_path is None:
            evolver_path = self._find_evolver()
        self.evolver_path = Path(evolver_path)
        if not self.evolver_path.exists():
            raise FileNotFoundError(
                f"Surface Evolver not found at {self.evolver_path}. "
                "Use --evolver-path to specify location."
            )

    def run(
        self,
        fe_file: str | Path,
        commands: Optional[str] = None,
        dump_file: Optional[str | Path] = None,
        timeout: int = 600,
        headless: bool = True,
    ) -> EvolverResult:
        """Run Surface Evolver on a .fe file.

        Args:
            fe_file: Path to the .fe input file.
            commands: SE commands to execute (default: gogo; gomore; dump).
            dump_file: Path for output dump file.
            timeout: Maximum execution time in seconds.
            headless: Run without graphics (recommended for batch).
        """
        fe_file = Path(fe_file)
        if dump_file is None:
            dump_file = fe_file.with_suffix(".dmp")
        dump_file = Path(dump_file)

        if commands is None:
            commands = self._default_commands(dump_file)

        # Build command line
        cmd = [str(self.evolver_path)]
        if headless:
            cmd.extend(["-p1"])  # single thread, no graphics window
        cmd.append(str(fe_file))

        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                input=commands,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(fe_file.parent),
            )
            elapsed = time.time() - start

            success = proc.returncode == 0 and dump_file.exists()

            # Try to extract energy and volume from stdout
            energy = self._parse_energy(proc.stdout)
            volume = self._parse_volume(proc.stdout)

            return EvolverResult(
                success=success,
                dump_file=dump_file if dump_file.exists() else None,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                final_energy=energy,
                final_volume=volume,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            return EvolverResult(
                success=False,
                dump_file=None,
                stdout="",
                stderr=f"Evolver timed out after {timeout}s",
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.time() - start
            return EvolverResult(
                success=False,
                dump_file=None,
                stdout="",
                stderr=str(e),
                elapsed_seconds=elapsed,
            )

    def _default_commands(self, dump_file: Path) -> str:
        """Generate default evolution + dump commands using strategy."""
        from .evolution_scripts import EvolutionStrategy, generate_runtime_commands
        strategy = EvolutionStrategy(preset="basic")
        return generate_runtime_commands(strategy, dump_file.name)

    def _parse_energy(self, stdout: str) -> Optional[float]:
        """Extract final energy from SE output."""
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if "total energy" in line.lower() or "energy:" in line.lower():
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        return float(parts[-1].strip())
                    except ValueError:
                        pass
            # SE prints energy after each iteration as a number
            if line and line[0].isdigit() and "." in line:
                try:
                    return float(line.split()[0])
                except (ValueError, IndexError):
                    pass
        return None

    def _parse_volume(self, stdout: str) -> Optional[float]:
        """Extract final volume from SE output."""
        for line in reversed(stdout.splitlines()):
            if "volume" in line.lower():
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        return float(parts[-1].strip())
                    except ValueError:
                        pass
        return None

    @staticmethod
    def _find_evolver() -> Path:
        """Auto-detect Surface Evolver executable."""
        candidates = []

        # PyInstaller bundle path
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            base = Path(meipass)
            candidates.append(base / "src" / "evolver")
            candidates.append(base / "src" / "evolver.exe")

        # Check common locations
        candidates += [
            Path(__file__).parent.parent.parent / "src" / "evolver",
            Path(__file__).parent.parent.parent / "src" / "evolver.exe",
        ]

        # Check PATH
        which = shutil.which("evolver")
        if which:
            candidates.insert(0, Path(which))

        if platform.system() == "Windows":
            which_exe = shutil.which("evolver.exe")
            if which_exe:
                candidates.insert(0, Path(which_exe))

        for p in candidates:
            if p.exists():
                return p

        # Default to src/evolver
        return Path(__file__).parent.parent.parent / "src" / "evolver"
