"""Protocolo, recepcion UDP y registro TinyWear. Solo biblioteca estandar."""
from __future__ import annotations

import csv
import ipaddress
import json
import math
import queue
import re
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CLASSES = ("caminar", "reposo", "sentarse_levantarse")
DISPLAY_NAMES = {
    "caminar": "Caminar", "reposo": "Reposo / de pie",
    "sentarse_levantarse": "Sentarse–levantarse", "incierto": "Incierto",
    "sin_etiquetar": "Sin etiqueta", "transicion": "Transición",
}
DEFAULT_IP = "192.168.4.1"
DEFAULT_PORT = 5005
STALE_SECONDS = 6.0


class ProtocolError(ValueError):
    pass


def number(data, key, minimum=0, maximum=math.inf):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"Campo numerico incorrecto: {key}")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ProtocolError(f"Campo fuera de rango: {key}")
    return value


def integer(data, key, minimum=0, maximum=0xFFFFFFFF):
    value = number(data, key, minimum, maximum)
    if not isinstance(value, int):
        raise ProtocolError(f"Se esperaba un entero en {key}")
    return value


def decode_packet(raw: bytes) -> dict:
    """Rechaza mensajes incompletos, valores no finitos y clases incompatibles."""
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeError as exc:
        raise ProtocolError("Datagrama no UTF-8") from exc
    if text == "TINYWEAR_ACK":
        return {"type": "ack"}
    if text.count(",") == 7 and not text.startswith("{"):
        raise ProtocolError("Se reciben lecturas de P1/P2. Cargar el firmware de inferencia.")
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("Datagrama JSON incorrecto") from exc
    if not isinstance(data, dict) or type(data.get("version")) is not int or data.get("version") != 1:
        raise ProtocolError("Version de protocolo no compatible")
    if not re.fullmatch(r"[0-9a-f]{8}", str(data.get("boot_id", ""))):
        raise ProtocolError("Identificador de arranque incorrecto")
    kind = data.get("type")
    if kind == "info":
        if data.get("classes") != list(CLASSES):
            raise ProtocolError("Las clases del modelo no coinciden con TinyWear")
        if data.get("axes") != ["ax", "ay", "az", "gx", "gy", "gz"]:
            raise ProtocolError("Orden de ejes incompatible")
        if data.get("fs_hz") != 50 or data.get("window_samples") != 100:
            raise ProtocolError("Se requieren 50 Hz y 100 lecturas por ventana")
        if data.get("normalized") is not True or data.get("quantization") != "int8":
            raise ProtocolError("Se requiere el modelo INT8 con normalizacion exportada")
        number(data, "threshold", 0, 1)
        integer(data, "kit", 1, 65535)
    elif kind == "prediction":
        integer(data, "seq")
        integer(data, "kit", 1, 65535)
        start_ms = integer(data, "t_start_ms")
        end_ms = integer(data, "t_end_ms")
        span_ms = (end_ms - start_ms) & 0xFFFFFFFF
        if not 1900 <= span_ms <= 2100:
            raise ProtocolError("Duracion de ventana incompatible con 100 lecturas a 50 Hz")
        number(data, "confidence", 0, 1)
        threshold = number(data, "threshold", 0, 1)
        for key in ("dsp_ms", "inference_ms", "total_ms", "lag_ms", "max_jitter_us"):
            number(data, key)
        scores = data.get("probabilities")
        if not isinstance(scores, dict) or set(scores) != set(CLASSES):
            raise ProtocolError("Faltan probabilidades de las tres actividades")
        for key in CLASSES:
            number(scores, key, 0, 1)
        best = max(CLASSES, key=lambda key: scores[key])
        confidence = scores[best]
        if abs(data["confidence"] - confidence) > 0.00002:
            raise ProtocolError("La confianza no coincide con las probabilidades")
        expected_label = best if confidence >= threshold else "incierto"
        if data.get("label") != expected_label:
            raise ProtocolError("La decision no coincide con el umbral del ESP32")
    elif kind == "status":
        if not isinstance(data.get("sensor_ok"), bool):
            raise ProtocolError("Estado de sensor incorrecto")
        for key in ("frames", "completed_windows", "rejected_windows", "i2c_errors",
                    "late_samples", "queue_drops", "max_jitter_us", "sample_age_ms", "free_heap"):
            integer(data, key)
        integer(data, "frames", 0, 100)
    elif kind == "error":
        integer(data, "seq")
        integer(data, "code", -100000, 100000)
        if not isinstance(data.get("message"), str):
            raise ProtocolError("Mensaje de error incorrecto")
    else:
        raise ProtocolError("Tipo de mensaje desconocido")
    return data


@dataclass
class Event:
    kind: str
    payload: dict | str
    received_at: float


class SequenceTracker:
    """No vuelve a mostrar resultados repetidos, atrasados o de un arranque anterior."""
    def __init__(self):
        self.boot_id = None
        self.last_seq = None
        self.retired_boots = set()
        self.gaps = 0
        self.ignored = 0

    def observe_boot(self, boot_id):
        if boot_id in self.retired_boots:
            return False
        if boot_id != self.boot_id:
            if self.boot_id is not None:
                self.retired_boots.add(self.boot_id)
            self.boot_id, self.last_seq = boot_id, None
        return True

    def accept(self, data):
        if not self.observe_boot(data["boot_id"]):
            self.ignored += 1
            return False
        seq = data["seq"]
        if self.last_seq is not None and seq <= self.last_seq:
            self.ignored += 1
            return False
        if self.last_seq is not None:
            self.gaps += max(0, seq - self.last_seq - 1)
        self.last_seq = seq
        return True


class UDPReceiver:
    def __init__(self, esp_ip=DEFAULT_IP, esp_port=DEFAULT_PORT, local_port=DEFAULT_PORT):
        ipaddress.IPv4Address(esp_ip)           # Se usa una IP literal, igual que en la captura previa.
        for value in (esp_port, local_port):
            if not 1 <= int(value) <= 65535:
                raise ValueError("El puerto debe estar entre 1 y 65535")
        self.destination = (esp_ip, int(esp_port))
        self.local_port = int(local_port)
        self.events = queue.Queue(maxsize=500)
        self.stop_event = threading.Event()
        self.thread = None
        self.sock = None
        self.last_rx = 0.0

    def emit(self, kind, payload, when=None):
        event = Event(kind, payload, time.monotonic() if when is None else when)
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            self.events.put_nowait(event)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", self.local_port)) # Puerto exclusivo: evita competir con el capturador.
            sock.settimeout(0.2)
        except OSError:
            sock.close()
            raise
        self.sock = sock
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        last_send = last_hello = last_warning = 0.0
        while not self.stop_event.is_set():
            now = time.monotonic()
            if now - last_send >= 2.0:
                hello = now - last_hello >= 8.0 or now - self.last_rx > STALE_SECONDS
                message = b"TINYWEAR_HELLO" if hello else b"TINYWEAR_KEEPALIVE"
                try:
                    self.sock.sendto(message, self.destination)
                    if hello:
                        last_hello = now
                except OSError as exc:
                    if not self.stop_event.is_set():
                        self.emit("warning", f"No se pudo enviar el registro UDP: {exc}")
                last_send = now
            try:
                raw, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self.stop_event.is_set():
                    self.emit("warning", f"Recepcion UDP interrumpida: {exc}")
                break
            if addr != self.destination:
                continue                      # Ignora datagramas de otros equipos o puertos.
            received_at = time.monotonic()
            try:
                data = decode_packet(raw)
            except ProtocolError as exc:
                if received_at - last_warning > 2:
                    self.emit("warning", str(exc), received_at)
                    last_warning = received_at
                continue
            self.last_rx = received_at
            self.emit(data["type"], data, received_at)

    def stop(self):
        self.stop_event.set()
        if self.sock:
            self.sock.close()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        self.sock = None


class DemoReceiver(UDPReceiver):
    """Datos SIMULADOS para comprobar la interfaz; no ejecuta el modelo."""
    def __init__(self):
        super().__init__()

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        self.emit("info", {
            "type": "info", "version": 1, "boot_id": "de000001", "kit": 1,
            "classes": list(CLASSES), "axes": ["ax", "ay", "az", "gx", "gy", "gz"],
            "fs_hz": 50, "window_samples": 100, "window_ms": 2000, "features": 78,
            "normalized": True, "quantization": "int8", "threshold": 0.6, "demo": True,
        })
        seq = 0
        while not self.stop_event.wait(2):
            label = CLASSES[(seq // 4) % 3]
            scores = {key: 0.04 for key in CLASSES}
            scores[label] = 0.92
            data = {
                "type": "prediction", "version": 1, "boot_id": "de000001", "kit": 1,
                "seq": seq, "t_start_ms": seq * 2000 + 20, "t_end_ms": (seq + 1) * 2000,
                "label": label, "confidence": 0.92, "threshold": 0.6,
                "probabilities": scores, "dsp_ms": 1.8, "inference_ms": 0.4,
                "total_ms": 2.3, "lag_ms": 3, "max_jitter_us": 350, "demo": True,
            }
            self.last_rx = time.monotonic()
            self.emit("prediction", data)
            seq += 1


CSV_FIELDS = (
    "fecha_hora_pc", "fuente", "sujeto", "actividad_real", "resultado_validacion",
    "kit", "boot_id", "ventana_seq", "t_inicio_ms", "t_fin_ms", "actividad_predicha",
    "confianza", "umbral", "p_caminar", "p_reposo", "p_sentarse_levantarse",
    "dsp_ms", "inferencia_ms", "total_ms", "retraso_ms", "jitter_max_us",
)


def validation_result(expected, label):
    if expected not in CLASSES:
        return "sin_evaluar"
    return "correcto" if expected == label else "incorrecto"


def eligible_activity(activity, changed_at, event: Event):
    if activity not in CLASSES:
        return "sin_etiquetar"
    # Una etiqueta recien seleccionada no describe la ventana previa completa.
    lag_seconds = event.payload["lag_ms"] / 1000
    estimated_start = event.received_at - lag_seconds - 2.0
    return activity if estimated_start >= changed_at + 0.25 else "transicion"


class CSVLogger:
    def __init__(self, path, subject):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", subject):
            raise ValueError("Sujeto: usar de 1 a 32 letras, numeros, guion o guion bajo")
        self.path = Path(path)
        self.subject = subject
        self.file = self.path.open("w", encoding="utf-8-sig", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=CSV_FIELDS)
        self.writer.writeheader()
        self.file.flush()
        self.rows = 0

    def write(self, data, expected="sin_etiquetar"):
        scores = data["probabilities"]
        self.writer.writerow({
            "fecha_hora_pc": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "fuente": "DEMO_SIMULADA" if data.get("demo") else "ESP32_S3",
            "sujeto": self.subject, "actividad_real": expected,
            "resultado_validacion": validation_result(expected, data["label"]),
            "kit": data["kit"], "boot_id": data["boot_id"], "ventana_seq": data["seq"],
            "t_inicio_ms": data["t_start_ms"], "t_fin_ms": data["t_end_ms"],
            "actividad_predicha": data["label"], "confianza": data["confidence"],
            "umbral": data["threshold"], "p_caminar": scores["caminar"],
            "p_reposo": scores["reposo"], "p_sentarse_levantarse": scores["sentarse_levantarse"],
            "dsp_ms": data["dsp_ms"], "inferencia_ms": data["inference_ms"],
            "total_ms": data["total_ms"], "retraso_ms": data["lag_ms"],
            "jitter_max_us": data["max_jitter_us"],
        })
        self.file.flush()                     # Cada prediccion queda escrita inmediatamente.
        self.rows += 1

    def close(self):
        self.file.close()
