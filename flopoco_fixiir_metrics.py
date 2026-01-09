"""
Utilitaires pour extraire les métriques FixIIR à partir des logs de FloPoCo.

Objectif :
    Lancer `flopoco FixIIR ... loglevel=1` et parser automatiquement les informations suivantes :
      - H : worst-case peak gain (gain maximal du filtre)
      - Heps : worst-case peak gain de l’amplification de l’erreur
      - lsbExt : extension interne du LSB choisie par FixIIR (nombre de bits de garde)

Ces métriques sont utilisées pour caractériser la stabilité numérique et
le dimensionnement interne des filtres IIR en virgule fixe.
"""


from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import subprocess
from typing import Optional, Sequence


@dataclass(frozen=True)
class FixIIRMetrics:
    H: float
    Heps: Optional[float]
    lsbExt: int
    raw_log: str
    timedOut: bool = False


_FLOAT_RE = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"

_RE_H = re.compile(
    r"(?:Computed filter worst-case peak gain|Filter worst-case peak gain):\s*H=" + _FLOAT_RE
)
_RE_HEPS = re.compile(
    r"(?:Computed error amplification worst-case peak gain|Error amplification worst-case peak gain):\s*Heps="
    + _FLOAT_RE
)
_RE_LSBEXT = re.compile(r"Building an IIR filter faithful to\s*lsbExt=([+-]?\d+)")


def _resolve_flopoco_exe(flopoco_exe: Optional[str]) -> str:
    if flopoco_exe:
        return flopoco_exe
    found = shutil.which("flopoco")
    if found:
        return found
    # Common local build location
    return "./build/flopoco"


def run_fixiir_and_parse_metrics(
    *,
    coeffb: str,
    coeffa: str,
    lsbIn: int,
    lsbOut: int,
    loglevel: int = 1,
    generateFigures: int = 0,
    flopoco_exe: Optional[str] = None,
    extra_args: Optional[Sequence[str]] = None,
    timeout_s: Optional[float] = None,
    fallback_H: Optional[float] = None,
) -> FixIIRMetrics:
    """
    Lance FloPoCo FixIIR et extrait les métriques (H, Heps, lsbExt).

    Arguments :
        coeffb : liste de coefficients du numérateur, séparés par ':' et exprimés
                en flottants hexadécimaux (le format Python float.hex() est compatible).
        coeffa : liste de coefficients du dénominateur, séparés par ':'.
                Dans les exemples FloPoCo, il s’agit généralement de a[1:]
                (le coefficient a0 = 1 est omis).
        lsbIn / lsbOut : positions des LSB d’entrée et de sortie pour FixIIR.
        loglevel : le niveau 1 active les lignes 'Detail:' nécessaires pour extraire
                H et lsbExt depuis les logs.
        generateFigures : mettre à 0 pour accélérer l’exécution (pas de figures générées).
        flopoco_exe : chemin vers l’exécutable FloPoCo, ou None pour une détection automatique.
        extra_args : arguments supplémentaires passés à FloPoCo (par ex. target=...).
        timeout_s : délai maximal d’exécution du sous-processus.

    """

    flopoco_exe = _resolve_flopoco_exe(flopoco_exe)

    cmd = [
        flopoco_exe,
        f"generateFigures={int(generateFigures)}",
        "FixIIR",
        f"coeffb={coeffb}",
        f"coeffa={coeffa}",
        f"lsbIn={int(lsbIn)}",
        f"lsbOut={int(lsbOut)}",
        f"loglevel={int(loglevel)}",
    ]
    if extra_args:
        cmd.extend(list(extra_args))

    try:
        # Use bytes output and decode explicitly to avoid mixing bytes/str
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        # e.stdout / e.stderr may be bytes or None
        stdout_b = e.stdout or b""
        stderr_b = e.stderr or b""
        try:
            stdout = stdout_b.decode("utf-8", errors="replace") if isinstance(stdout_b, (bytes, bytearray)) else str(stdout_b)
            stderr = stderr_b.decode("utf-8", errors="replace") if isinstance(stderr_b, (bytes, bytearray)) else str(stderr_b)
        except Exception:
            stdout = str(stdout_b)
            stderr = str(stderr_b)
        raw_log = stdout + "\n" + stderr
        # Best effort: FixIIR often prints H/Heps/lsbExt early, then spends a long time
        # synthesizing the operator. If we already have the metrics, return them.
        mH = _RE_H.search(raw_log)
        mHeps = _RE_HEPS.search(raw_log)
        mlsb = _RE_LSBEXT.search(raw_log)
        if mH and mlsb:
            H = float(mH.group(1))
            Heps = float(mHeps.group(1)) if mHeps else None
            lsbExt = int(mlsb.group(1))
            return FixIIRMetrics(H=H, Heps=Heps, lsbExt=lsbExt, raw_log=raw_log, timedOut=True)

        raise RuntimeError(
            f"FloPoCo timeout after {timeout_s}s while running FixIIR. Log:\n{raw_log}"
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(
            f"FloPoCo executable not found: {flopoco_exe}. "
            f"Either install `flopoco` in PATH or pass flopoco_exe=..."
        ) from e

    # proc.stdout / proc.stderr are bytes (text=False). Decode safely.
    stdout_b = proc.stdout or b""
    stderr_b = proc.stderr or b""
    try:
        stdout = stdout_b.decode("utf-8", errors="replace") if isinstance(stdout_b, (bytes, bytearray)) else str(stdout_b)
        stderr = stderr_b.decode("utf-8", errors="replace") if isinstance(stderr_b, (bytes, bytearray)) else str(stderr_b)
    except Exception:
        stdout = str(stdout_b)
        stderr = str(stderr_b)
    raw_log = stdout + "\n" + stderr

    if proc.returncode != 0:
        raise RuntimeError(f"FloPoCo exited with code {proc.returncode}. Log:\n{raw_log}")

    mH = _RE_H.search(raw_log)
    if mH:
        H = float(mH.group(1))
    elif fallback_H is not None:
        H = float(fallback_H)
    else:
        raise RuntimeError(f"Could not parse H from FloPoCo log. Log:\n{raw_log}")

    mHeps = _RE_HEPS.search(raw_log)
    Heps = float(mHeps.group(1)) if mHeps else None

    mlsb = _RE_LSBEXT.search(raw_log)
    if not mlsb:
        raise RuntimeError(f"Could not parse lsbExt from FloPoCo log. Log:\n{raw_log}")
    lsbExt = int(mlsb.group(1))

    return FixIIRMetrics(H=H, Heps=Heps, lsbExt=lsbExt, raw_log=raw_log, timedOut=False)


def coeffs_to_flopoco_hex_list(coeffs) -> str:
    """Convert an iterable of floats to a ':' separated list of hex-float literals."""
    return ":".join([float(c).hex() for c in coeffs])


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run FloPoCo FixIIR and extract H / Heps / lsbExt.")
    ap.add_argument("--coeffb", required=True, help="':' separated hex-float list")
    ap.add_argument("--coeffa", required=True, help="':' separated hex-float list (typically a[1:])")
    ap.add_argument("--lsbIn", type=int, default=-12)
    ap.add_argument("--lsbOut", type=int, default=-12)
    ap.add_argument("--loglevel", type=int, default=1)
    ap.add_argument("--generateFigures", type=int, default=0)
    ap.add_argument("--flopoco", dest="flopoco_exe", default=None)
    args = ap.parse_args()

    m = run_fixiir_and_parse_metrics(
        coeffb=args.coeffb,
        coeffa=args.coeffa,
        lsbIn=args.lsbIn,
        lsbOut=args.lsbOut,
        loglevel=args.loglevel,
        generateFigures=args.generateFigures,
        flopoco_exe=args.flopoco_exe,
    )

    print(f"H={m.H}")
    print(f"Heps={m.Heps}")
    print(f"lsbExt={m.lsbExt}")
