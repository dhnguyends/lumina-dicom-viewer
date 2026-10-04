"""Lumina: local, single-frame monochrome CT viewer. No notebook execution required."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import mimetypes
import os
import threading
import uuid
from collections import defaultdict
from email.parser import BytesParser
from email.policy import default
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pydicom
from PIL import Image
from pydicom.pixel_data_handlers.util import apply_modality_lut

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "demo"
SERIES: dict[str, dict] = {}
LOCK = threading.Lock()
MAX_UPLOAD = 256 * 1024 * 1024


def orientation_labels(orientation):
    """Patient directions of the right and bottom edges, in DICOM LPS space."""
    def direction(vector):
        letters = [('R', 'L'), ('A', 'P'), ('I', 'S')]
        order = np.argsort(np.abs(vector))[::-1]
        return ''.join(letters[i][int(vector[i] > 0)] for i in order if abs(vector[i]) > .2)
    row, col = np.array(orientation[:3]), np.array(orientation[3:])
    return {"right": direction(row), "left": direction(-row),
            "bottom": direction(col), "top": direction(-col)}


def read_header(path):
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    if ds.get("Modality") != "CT":
        raise ValueError("Seules les images CT sont prises en charge.")
    if int(ds.get("NumberOfFrames", 1)) != 1:
        raise ValueError("Les DICOM multiframe ne sont pas pris en charge.")
    if ds.get("PhotometricInterpretation") not in ("MONOCHROME1", "MONOCHROME2"):
        raise ValueError("Une image CT monochrome est requise.")
    if not ds.get("Rows") or not ds.get("Columns") or not ds.get("SeriesInstanceUID"):
        raise ValueError("En-tête DICOM incomplet.")
    return ds


def index_paths(paths, source="Série locale"):
    groups = defaultdict(list)
    rejected = 0
    for path in paths:
        try:
            ds = read_header(path)
            orient = tuple(float(v) for v in ds.get("ImageOrientationPatient", [1, 0, 0, 0, 1, 0]))
            spacing = tuple(float(v) for v in ds.get("PixelSpacing", [1, 1]))
            if len(orient) != 6 or len(spacing) != 2 or min(spacing) <= 0:
                raise ValueError("Géométrie DICOM invalide.")
            normal = np.cross(orient[:3], orient[3:])
            if not np.all(np.isfinite(orient)) or not np.all(np.isfinite(spacing)) or np.linalg.norm(normal) < .9:
                raise ValueError("Orientation DICOM invalide.")
            key = (str(ds.SeriesInstanceUID), tuple(round(v, 4) for v in orient),
                   int(ds.Rows), int(ds.Columns), spacing)
            pos = ds.get("ImagePositionPatient")
            physical = pos is not None and "ImageOrientationPatient" in ds
            location = float(np.dot(np.array(pos, dtype=float), normal)) if physical else None
            if location is not None and not math.isfinite(location):
                raise ValueError("Position DICOM invalide.")
            groups[key].append({"path": Path(path), "ds": ds, "position": location,
                                "instance": int(ds.get("InstanceNumber", 0))})
        except (ValueError, OSError, TypeError, AttributeError, pydicom.errors.InvalidDicomError):
            rejected += 1
    added = []
    for key, records in groups.items():
        all_physical = all(r["position"] is not None for r in records)
        records.sort(key=lambda r: (r["position"] if all_physical else r["instance"], str(r["path"])))
        ds = records[0]["ds"]
        positions = [r["position"] for r in records]
        gaps = np.diff(positions) if all_physical and len(records) > 1 else np.array([])
        positive_gaps = gaps[gaps > 1e-4]
        measured = float(np.median(positive_gaps)) if len(positive_gaps) else None
        warnings = []
        if not all_physical:
            warnings.append("Géométrie incomplète : tri par numéro d’instance, orientation non certifiée.")
        if len(gaps) and np.any(gaps <= 1e-4):
            warnings.append("Des positions de coupe sont dupliquées.")
        if measured and np.any(np.abs(gaps - measured) > max(.1, measured * .05)):
            warnings.append("Espacement irrégulier entre les coupes.")
        calibrated = all("RescaleSlope" in r["ds"] and "RescaleIntercept" in r["ds"] for r in records)
        if not calibrated:
            warnings.append("Calibration HU absente sur certaines coupes : valeurs d’intensité à vérifier.")
        normal = np.cross(key[1][:3], key[1][3:])
        plane = ["sagittale", "coronale", "axiale"][int(np.argmax(np.abs(normal)))]
        if max(abs(normal)) < .99:
            plane = "oblique"
        # Stable opaque identifier: bookmarks/favorites survive server restarts.
        identity = repr(key) + repr([str(r["ds"].get("SOPInstanceUID", r["path"].name)) for r in records])
        sid = hashlib.sha256(identity.encode()).hexdigest()[:16]
        with LOCK:
            if sid in SERIES:
                added.append(sid)
                continue
            ordinal = len(SERIES) + 1
            item = {"id": sid, "name": f"Série CT {ordinal:02d}", "description": "Acquisition tomodensitométrique",
                    "source": source, "count": len(records), "rows": int(ds.Rows), "columns": int(ds.Columns),
                    "pixel_spacing": list(key[4]), "slice_spacing": measured,
                    "plane": plane, "labels": orientation_labels(key[1]) if all_physical else {},
                    "warnings": warnings, "calibrated": calibrated, "records": records}
            SERIES[sid] = item
        added.append(sid)
    return added, rejected


def public_series(item):
    return {k: v for k, v in item.items() if k != "records"}


@lru_cache(maxsize=16)
def pixels(sid, index):
    record = SERIES[sid]["records"][index]
    ds = pydicom.dcmread(record["path"])
    raw = ds.pixel_array
    if raw.ndim != 2:
        raise ValueError("Dimensions de pixels non prises en charge.")
    padding = np.zeros(raw.shape, dtype=bool)
    if "PixelPaddingValue" in ds:
        a = float(ds.PixelPaddingValue)
        b = float(ds.get("PixelPaddingRangeLimit", a))
        padding = (raw >= min(a, b)) & (raw <= max(a, b))
    hu = np.asarray(apply_modality_lut(raw, ds), dtype=np.float32)
    return hu, padding, ds.PhotometricInterpretation == "MONOCHROME1"


def window_pixels(hu, center, width):
    """DICOM LINEAR window, preserving fractional calibration before display."""
    if width == 1:
        return (hu > center - .5).astype(np.float32)
    return np.clip((hu - (center - .5)) / (width - 1) + .5, 0, 1)


@lru_cache(maxsize=64)
def image_png(sid, index, center, width, invert):
    hu, padding, mono1 = pixels(sid, index)
    gray = window_pixels(hu, center, width)
    if bool(invert) != mono1:
        gray = 1 - gray
    gray[padding] = 0
    image = Image.fromarray((gray * 255).astype(np.uint8))
    sy, sx = SERIES[sid]["pixel_spacing"]
    # Preserve physical pixel aspect ratio rather than forcing a square matrix.
    ratio = image.width * sx / (image.height * sy)
    longest = min(1536, max(image.size))
    size = (longest, max(1, round(longest / ratio))) if ratio >= 1 else (max(1, round(longest * ratio)), longest)
    if image.size != size:
        image = image.resize(size, Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not print uploaded names or DICOM identifiers.
        pass

    def send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def trusted_request(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin in {f"http://{h}" for h in allowed})

    def do_GET(self):
        if not self.trusted_request():
            return self.send(403, {"error": "Origine non autorisée."})
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/api/series":
                with LOCK:
                    return self.send(200, [public_series(s) for s in SERIES.values()])
            if url.path in ("/api/image", "/api/slice"):
                sid = q.get("series", [""])[0]
                if sid not in SERIES:
                    return self.send(404, {"error": "Série introuvable."})
                index = int(q.get("index", ["0"])[0])
                if not 0 <= index < SERIES[sid]["count"]:
                    return self.send(400, {"error": "Numéro de coupe hors limites."})
                if url.path == "/api/slice":
                    r = SERIES[sid]["records"][index]
                    return self.send(200, {"index": index, "position": r["position"], "instance": r["instance"]})
                center = float(q.get("center", ["-600"])[0])
                width = float(q.get("width", ["1500"])[0])
                if not math.isfinite(center) or not math.isfinite(width) or not -10000 <= center <= 10000 or not 1 <= width <= 20000:
                    raise ValueError("Fenêtre de contraste invalide.")
                data = image_png(sid, index, center, width, q.get("invert", ["0"])[0] == "1")
                if q.get("download"):
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Disposition", f'attachment; filename="lumina-coupe-{index + 1:03d}.png"')
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return self.send(200, data, "image/png")
            if url.path == "/guide.md":
                return self.send(200, (ROOT / "GUIDE_UTILISATEUR.md").read_bytes(), "text/markdown; charset=utf-8")
            files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg",
                     "/guide": "guide.html", "/guide.html": "guide.html", "/guide.css": "guide.css",
                     "/guide-assets/fenetres-ct.png": "guide-assets/fenetres-ct.png",
                     "/guide-assets/lumina-galerie.jpg": "guide-assets/lumina-galerie.jpg",
                     "/guide-assets/lumina-visionneuse.jpg": "guide-assets/lumina-visionneuse.jpg"}
            if url.path not in files:
                return self.send(404, {"error": "Page introuvable."})
            path = ROOT / "static" / files[url.path]
            return self.send(200, path.read_bytes(), mimetypes.guess_type(path)[0] or "application/octet-stream")
        except (ValueError, TypeError) as exc:
            return self.send(400, {"error": str(exc)})
        except Exception:
            return self.send(422, {"error": "Image illisible. Vérifiez le DICOM et les décodeurs de sa syntaxe de transfert."})

    def do_POST(self):
        if not self.trusted_request():
            return self.send(403, {"error": "Origine non autorisée."})
        if urlparse(self.path).path != "/api/import":
            return self.send(404, {"error": "Route introuvable."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD:
                return self.send(413, {"error": "Import limité à 256 Mo par lot."})
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data;") or "boundary=" not in content_type:
                raise ValueError("Un lot de fichiers DICOM est requis.")
            body = self.rfile.read(length)
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body)
            parts = [part for part in message.iter_parts() if part.get_filename() is not None]
            if not parts or len(parts) > 2000:
                raise ValueError("Sélectionnez entre 1 et 2 000 fichiers DICOM.")
            folder = ROOT / "data" / "imports" / uuid.uuid4().hex
            folder.mkdir(parents=True, exist_ok=True)
            paths = []
            rejected = 0
            for part in parts:
                path = folder / f"{uuid.uuid4().hex}.dcm"
                path.write_bytes(part.get_payload(decode=True) or b"")
                try:
                    read_header(path)
                    paths.append(path)
                except Exception:
                    path.unlink()
                    rejected += 1
            ids, invalid_geometry = index_paths(paths, "Import local")
            rejected += invalid_geometry
            if not ids:
                for path in paths:
                    path.unlink(missing_ok=True)
                folder.rmdir()
                raise ValueError("Aucune image CT monochrome single-frame valide trouvée.")
            return self.send(201, {"ids": ids, "rejected": rejected})
        except (ValueError, TypeError) as exc:
            return self.send(400, {"error": str(exc)})
        except Exception:
            return self.send(500, {"error": "L’import a échoué. Vérifiez les fichiers et l’espace disque disponible."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA, help="Dossier d’une acquisition DICOM (récursif)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.data_dir.is_dir():
        paths = [Path(parent) / name for parent, _, names in os.walk(args.data_dir) for name in names]
        ids, rejected = index_paths(paths)
        print(f"Chargement : {len(ids)} série(s), {sum(s['count'] for s in SERIES.values())} coupes, {rejected} fichier(s) écarté(s).", flush=True)
    imports = ROOT / "data" / "imports"
    if imports.is_dir():
        for folder in sorted(imports.iterdir()):
            if folder.is_dir():
                index_paths(folder.glob("*.dcm"), "Import local")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Lumina est disponible sur http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
