"""Wrappers for running Surface Evolver on .fe files and parsing results."""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from kse.solver.dump_parser import DumpParser


@dataclass
class SERunResult:
    """Result of an SE execution."""
    success: bool
    dump_path: Optional[Path] = None
    energy: Optional[float] = None
    volume: Optional[float] = None
    n_vertices: int = 0
    n_faces: int = 0
    vertex_positions: Optional[np.ndarray] = None
    face_triangles: Optional[np.ndarray] = None
    free_face_triangles: Optional[np.ndarray] = None  # non-fixed faces only
    stderr: str = ""
    stdout: str = ""


def _patch_missing_reads(fe_copy: Path, work_dir: Path):
    """Comment out 'read "..."' lines that reference missing .cmd files."""
    text = fe_copy.read_text()
    lines = text.split("\n")
    patched = False
    for i, line in enumerate(lines):
        m = re.match(r'^(\s*read\s+)"([^"]+)"', line)
        if m:
            ref_file = work_dir / m.group(2)
            if not ref_file.exists():
                lines[i] = f"// PATCHED: {line}"
                patched = True
    if patched:
        fe_copy.write_text("\n".join(lines))


def run_original_fe(
    fe_path: Path,
    evolver_path: Path,
    work_dir: Path,
    gogo_cmd: str = "gogo",
    timeout: int = 180,
) -> SERunResult:
    """Run an original .fe file through SE and return parsed results.

    Copies the .fe to work_dir, executes SE with gogo + dump, and
    parses the resulting dump file.
    """
    fe_path = Path(fe_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Copy .fe file (and any auxiliary files in same directory)
    fe_copy = work_dir / fe_path.name
    shutil.copy(fe_path, fe_copy)

    # Copy auxiliary .cmd files if they exist in the same directory
    for cmd_file in fe_path.parent.glob("*.cmd"):
        shutil.copy(cmd_file, work_dir / cmd_file.name)

    # Patch out read "..." lines that reference missing files
    # (e.g. bga-7.fe references xzforce.cmd which isn't available)
    _patch_missing_reads(fe_copy, work_dir)

    dmp_name = fe_path.stem + ".dmp"
    dmp_path = work_dir / dmp_name

    commands = f'{gogo_cmd};\ndump "{dmp_name}";\nq\n'

    try:
        proc = subprocess.run(
            [str(evolver_path), "-p1", fe_copy.name],
            input=commands,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return SERunResult(success=False, stderr="Timeout")
    except FileNotFoundError:
        return SERunResult(success=False, stderr="Evolver binary not found")

    if not dmp_path.exists():
        return SERunResult(
            success=False,
            stderr=proc.stderr[:500] if proc.stderr else "No dump file produced",
            stdout=proc.stdout[:500] if proc.stdout else "",
        )

    # Parse the dump
    parser = DumpParser()
    try:
        mesh = parser.parse(dmp_path)
    except Exception as e:
        return SERunResult(
            success=False,
            stderr=f"Dump parse error: {e}",
            dump_path=dmp_path,
        )

    body_vol = None
    if mesh.bodies:
        body = list(mesh.bodies.values())[0]
        body_vol = body.actual_volume or body.volume

    verts = mesh.vertex_array
    tris = mesh.face_triangles
    free_tris = mesh.free_face_triangles

    return SERunResult(
        success=True,
        dump_path=dmp_path,
        energy=mesh.total_energy,
        volume=body_vol,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        vertex_positions=verts,
        face_triangles=tris,
        free_face_triangles=free_tris,
        stdout=proc.stdout[-500:] if proc.stdout else "",
        stderr=proc.stderr[-500:] if proc.stderr else "",
    )


def run_kse_fe(
    fe_path: Path,
    evolver_path: Path,
    work_dir: Path,
    timeout: int = 300,
) -> SERunResult:
    """Run a KSE-generated .fe file through SE.

    Uses KSE's gogo + gomore evolution sequence.
    """
    fe_path = Path(fe_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Copy .fe if not already in work_dir
    if fe_path.parent != work_dir:
        fe_copy = work_dir / fe_path.name
        shutil.copy(fe_path, fe_copy)
    else:
        fe_copy = fe_path

    dmp_name = fe_path.stem + ".dmp"
    dmp_path = work_dir / dmp_name

    commands = f'gogo;\ngomore;\ndump "{dmp_name}";\nq\n'

    try:
        proc = subprocess.run(
            [str(evolver_path), "-p1", fe_copy.name],
            input=commands,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return SERunResult(success=False, stderr="Timeout")
    except FileNotFoundError:
        return SERunResult(success=False, stderr="Evolver binary not found")

    if not dmp_path.exists():
        return SERunResult(
            success=False,
            stderr=proc.stderr[:500] if proc.stderr else "No dump file produced",
            stdout=proc.stdout[:500] if proc.stdout else "",
        )

    parser = DumpParser()
    try:
        mesh = parser.parse(dmp_path)
    except Exception as e:
        return SERunResult(
            success=False,
            stderr=f"Dump parse error: {e}",
            dump_path=dmp_path,
        )

    body_vol = None
    if mesh.bodies:
        body = list(mesh.bodies.values())[0]
        body_vol = body.actual_volume or body.volume

    verts = mesh.vertex_array
    tris = mesh.face_triangles
    free_tris = mesh.free_face_triangles

    return SERunResult(
        success=True,
        dump_path=dmp_path,
        energy=mesh.total_energy,
        volume=body_vol,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        vertex_positions=verts,
        face_triangles=tris,
        free_face_triangles=free_tris,
        stdout=proc.stdout[-500:] if proc.stdout else "",
        stderr=proc.stderr[-500:] if proc.stderr else "",
    )


def result_to_dict(result: SERunResult) -> dict:
    """Convert SERunResult to JSON-serializable dict for reference storage."""
    d = {
        "energy": result.energy,
        "volume": result.volume,
        "n_vertices": result.n_vertices,
        "n_faces": result.n_faces,
    }
    if result.vertex_positions is not None:
        d["vertex_positions"] = result.vertex_positions.tolist()
    if result.face_triangles is not None and len(result.face_triangles) > 0:
        d["face_triangles"] = result.face_triangles.tolist()
    return d
