"""
TinyWear: visualizacion de inferencias ESP32-S3 recibidas por Wi-Fi/UDP.
El modelo se ejecuta en la tarjeta. Python no normaliza ni clasifica datos.

Uso: python Interfaz_TinyWear_WIFI.py
Demo: python Interfaz_TinyWear_WIFI.py --demo
Terminal: python Interfaz_TinyWear_WIFI.py --console
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import queue
import sys
import time

from tinywear_core import (
    CLASSES, DEFAULT_IP, DEFAULT_PORT, DISPLAY_NAMES, STALE_SECONDS,
    CSVLogger, DemoReceiver, SequenceTracker, UDPReceiver, eligible_activity,
    validation_result,
)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = ttk = filedialog = messagebox = None


class TinyWearGUI:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.receiver = None
        self.logger = None
        self.tracker = SequenceTracker()
        self.last_prediction_at = 0.0
        self.last_sensor_ok = None
        self.label_changed_at = time.monotonic()
        self.validation_counts = Counter()
        self.uncertain = 0
        self.received = 0
        self.banner_stale = True
        self.ip = tk.StringVar(value=args.ip)
        self.local_port = tk.StringVar(value=str(args.local_port))
        self.subject = tk.StringVar(value=args.subject)
        self.activity = tk.StringVar(value="Sin etiqueta")
        self.prediction = tk.StringVar(value="Esperando conexión")
        self.confidence = tk.StringVar(value="—")
        self.connection = tk.StringVar(value="Sin conexión")
        self.message = tk.StringVar(value="Conectar la computadora a TinyWear-1 · Clave: TinyWear2026")
        self.model = tk.StringVar(value="ESP32-S3 · INT8 · 50 Hz · ventana de 2 s · normalización incluida")
        self.timings = tk.StringVar(value="DSP: —    Inferencia: —    Procesamiento total: —")
        self.diagnostics = tk.StringVar(value="Diagnóstico del sensor: esperando datos")
        self.metrics = tk.StringVar(value="Ventanas recibidas: 0 · Evaluadas: 0 · Exactitud observada: —")
        self.recording = tk.StringVar(value="Registro CSV detenido")
        self.probabilities = {key: tk.DoubleVar(value=0) for key in CLASSES}
        self.probability_text = {key: tk.StringVar(value="—") for key in CLASSES}
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll)
        if args.demo:
            self.root.after(200, self.connect)

    def _build(self):
        self.root.title("TinyWear | Inferencia por Wi-Fi" + (" | DEMOSTRACIÓN" if self.args.demo else ""))
        width = min(1080, self.root.winfo_screenwidth() - 60)
        height = min(780, self.root.winfo_screenheight() - 70)
        self.root.geometry(f"{max(920, width)}x{max(680, height)}")
        self.root.minsize(920, 680)
        self.root.configure(background="#f2f4f7")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f4f7")
        style.configure("TLabel", background="#f2f4f7", foreground="#263449", font=("Arial", 10))
        style.configure("Title.TLabel", font=("Arial", 20, "bold"))
        style.configure("Prediction.TLabel", font=("Arial", 28, "bold"), foreground="#183756")
        style.configure("Confidence.TLabel", font=("Arial", 20, "bold"))
        style.configure("TButton", font=("Arial", 10), padding=(10, 6))
        style.configure("Treeview", font=("Arial", 9), rowheight=24)
        style.configure("Treeview.Heading", font=("Arial", 9, "bold"))
        palette = ("#486c96", "#597d68", "#8a729c")
        for key, color in zip(CLASSES, palette):
            style.configure(f"{key}.Horizontal.TProgressbar", background=color, troughcolor="#dfe5eb")

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(7, weight=1)
        top = ttk.Frame(outer)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="TinyWear | Inferencia local", style="Title.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.connection).pack(side="right")
        ttk.Label(outer, textvariable=self.model).grid(row=1, column=0, sticky="w", pady=(5, 10))
        if self.args.demo:
            self.message.set("DEMOSTRACIÓN CON DATOS SIMULADOS: no se ejecuta el modelo ni se usa Wi-Fi.")

        network = ttk.LabelFrame(outer, text="Conexión Wi-Fi / UDP", padding=10)
        network.grid(row=2, column=0, sticky="ew")
        ttk.Label(network, text="IP del ESP32:").grid(row=0, column=0, padx=(0, 5))
        self.ip_entry = ttk.Entry(network, textvariable=self.ip, width=17)
        self.ip_entry.grid(row=0, column=1)
        ttk.Label(network, text="Puerto local:").grid(row=0, column=2, padx=(14, 5))
        self.port_entry = ttk.Entry(network, textvariable=self.local_port, width=7)
        self.port_entry.grid(row=0, column=3)
        self.connect_button = ttk.Button(network, text="Conectar", command=self.connect)
        self.connect_button.grid(row=0, column=4, padx=(20, 5))
        self.disconnect_button = ttk.Button(network, text="Desconectar", command=self.disconnect, state="disabled")
        self.disconnect_button.grid(row=0, column=5)
        ttk.Label(network, textvariable=self.message, wraplength=960).grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))

        results = ttk.LabelFrame(outer, text="Decisión del ESP32-S3", padding=12)
        results.grid(row=3, column=0, sticky="ew", pady=10)
        results.columnconfigure(0, weight=1)
        ttk.Label(results, textvariable=self.prediction, style="Prediction.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(results, textvariable=self.confidence, style="Confidence.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Label(results, text="Puntuación máxima del modelo; no representa la exactitud de la sesión.").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 7))
        for i, key in enumerate(CLASSES, start=2):
            row = ttk.Frame(results)
            row.grid(row=i, column=0, columnspan=2, sticky="ew", pady=3)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=DISPLAY_NAMES[key], width=22).grid(row=0, column=0, sticky="w")
            ttk.Progressbar(row, variable=self.probabilities[key], maximum=100,
                            style=f"{key}.Horizontal.TProgressbar").grid(row=0, column=1, sticky="ew", padx=12)
            ttk.Label(row, textvariable=self.probability_text[key], width=8, anchor="e").grid(row=0, column=2)
        ttk.Label(results, textvariable=self.timings).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        validation = ttk.LabelFrame(outer, text="Validación física y registro CSV", padding=10)
        validation.grid(row=4, column=0, sticky="ew")
        ttk.Label(validation, text="Sujeto:").grid(row=0, column=0, padx=(0, 5))
        self.subject_entry = ttk.Entry(validation, textvariable=self.subject, width=10)
        self.subject_entry.grid(row=0, column=1)
        ttk.Label(validation, text="Actividad real:").grid(row=0, column=2, padx=(15, 5))
        self.activity_combo = ttk.Combobox(validation, textvariable=self.activity, state="readonly", width=23,
            values=["Sin etiqueta"] + [DISPLAY_NAMES[key] for key in CLASSES])
        self.activity_combo.grid(row=0, column=3)
        self.activity_combo.bind("<<ComboboxSelected>>", self.activity_changed)
        self.record_button = ttk.Button(validation, text="Iniciar CSV", command=self.toggle_recording)
        self.record_button.grid(row=0, column=4, padx=(15, 5))
        ttk.Button(validation, text="Reiniciar conteo", command=self.reset_counts).grid(row=0, column=5)
        ttk.Label(validation, text="Las primeras ventanas después de cambiar la actividad real se marcan como transición.").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Label(validation, textvariable=self.recording).grid(row=2, column=0, columnspan=6, sticky="w", pady=(3, 0))

        ttk.Label(outer, textvariable=self.metrics).grid(row=5, column=0, sticky="w", pady=(9, 2))
        ttk.Label(outer, textvariable=self.diagnostics, wraplength=1020).grid(row=6, column=0, sticky="w", pady=(0, 5))
        history = ttk.Frame(outer)
        history.grid(row=7, column=0, sticky="nsew")
        history.columnconfigure(0, weight=1)
        history.rowconfigure(0, weight=1)
        columns = ("hora", "seq", "predicha", "confianza", "real", "evaluacion", "total")
        self.table = ttk.Treeview(history, columns=columns, show="headings", height=5)
        labels = ("Hora", "Ventana", "Actividad detectada", "Confianza", "Actividad real", "Evaluación", "Total ms")
        widths = (75, 65, 185, 80, 185, 100, 85)
        for key, label, col_width in zip(columns, labels, widths):
            self.table.heading(key, text=label)
            self.table.column(key, width=col_width, minwidth=55, anchor="center")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(history, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        ttk.Label(outer, text="TinyWear · ELECTRO 2026 · Ernesto Sifuentes de la Hoya").grid(
            row=8, column=0, sticky="w", pady=(7, 0))

    def connect(self):
        if self.receiver:
            return
        try:
            receiver = DemoReceiver() if self.args.demo else UDPReceiver(
                self.ip.get().strip(), self.args.port, int(self.local_port.get()))
            receiver.start()
        except (OSError, ValueError) as exc:
            messagebox.showerror("No fue posible iniciar la conexión",
                f"{exc}\n\nCerrar el capturador anterior o cualquier programa que use el puerto 5005.")
            return
        self.receiver = receiver
        self.tracker = SequenceTracker()
        self.last_prediction_at = 0
        self.last_sensor_ok = None
        self.label_changed_at = time.monotonic()
        self.connection.set("Demostración" if self.args.demo else "Registrando cliente…")
        self.prediction.set("Esperando ventana")
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="normal")
        self.ip_entry.configure(state="disabled")
        self.port_entry.configure(state="disabled")
        if not self.args.demo:
            self.message.set("Registro HELLO/ACK activo. Se espera una inferencia aproximadamente cada 2 segundos.")

    def disconnect(self):
        self.stop_recording()
        if self.receiver:
            self.receiver.stop()
            self.receiver = None
        self.connection.set("Sin conexión")
        self.connect_button.configure(state="normal")
        self.disconnect_button.configure(state="disabled")
        self.ip_entry.configure(state="normal")
        self.port_entry.configure(state="normal")
        self.clear_live("Desconectado")

    def activity_changed(self, _event=None):
        self.label_changed_at = time.monotonic()

    def selected_activity(self):
        return next((key for key in CLASSES if DISPLAY_NAMES[key] == self.activity.get()), "sin_etiquetar")

    def reset_counts(self):
        self.validation_counts.clear()
        self.received = self.uncertain = 0
        for item in self.table.get_children():
            self.table.delete(item)
        self.refresh_metrics()

    def refresh_metrics(self):
        n = sum(self.validation_counts.values())
        correct = self.validation_counts["correcto"]
        accuracy = f"{100 * correct / n:.1f} %" if n else "—"
        self.metrics.set(f"Ventanas recibidas: {self.received} · Evaluadas: {n} · "
                         f"Exactitud observada: {accuracy} · Inciertas: {self.uncertain} · "
                         f"Saltos de secuencia: {self.tracker.gaps}")

    def toggle_recording(self):
        if self.logger:
            self.stop_recording()
            return
        if not self.receiver:
            messagebox.showinfo("Registro CSV", "Iniciar la conexión antes de comenzar el registro.")
            return
        subject = self.subject.get().strip()
        directory = Path(__file__).resolve().parent / "resultados"
        try:
            directory.mkdir(exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Registro CSV", str(exc))
            return
        name = f"TinyWear_{subject}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = filedialog.asksaveasfilename(title="Guardar predicciones TinyWear", initialdir=directory,
                                           initialfile=name, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            self.logger = CSVLogger(path, subject)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Registro CSV", str(exc))
            return
        self.record_button.configure(text="Detener CSV")
        self.subject_entry.configure(state="disabled")
        self.recording.set(f"Guardando: {Path(path).name} · 0 filas")

    def stop_recording(self):
        if self.logger:
            rows, name = self.logger.rows, self.logger.path.name
            try:
                self.logger.close()
            except OSError as exc:
                self.message.set(f"Revisar el archivo CSV: {exc}")
            self.logger = None
            self.recording.set(f"Registro guardado: {name} · {rows} filas")
        self.record_button.configure(text="Iniciar CSV")
        self.subject_entry.configure(state="normal")

    def clear_live(self, text):
        self.prediction.set(text)
        self.confidence.set("—")
        for key in CLASSES:
            self.probabilities[key].set(0)
            self.probability_text[key].set("—")
        self.timings.set("DSP: —    Inferencia: —    Procesamiento total: —")
        self.banner_stale = True

    def handle(self, event):
        data = event.payload
        if event.kind == "warning":
            self.message.set(str(data))
            return
        if event.kind == "ack":
            self.connection.set("Wi-Fi conectado · UDP registrado")
            return
        if event.kind == "info":
            previous = self.tracker.boot_id
            if not self.tracker.observe_boot(data["boot_id"]):
                return
            if previous and previous != data["boot_id"]:
                self.clear_live("Tarjeta reiniciada")
                self.last_prediction_at = 0
                self.last_sensor_ok = None
            if not self.args.demo:
                self.model.set(f"Kit {data['kit']} · INT8 · 50 Hz · ventana de 2 s · "
                               f"{data.get('features', 78)} características · umbral {data['threshold']:.2f}")
                self.message.set(f"Modelo con normalización incorporada. Red TinyWear-{data['kit']} · UDP {self.args.port}.")
            return
        if event.kind == "status":
            previous = self.tracker.boot_id
            if not self.tracker.observe_boot(data["boot_id"]):
                return
            if previous and previous != data["boot_id"]:
                self.clear_live("Tarjeta reiniciada")
                self.last_prediction_at = 0
            self.last_sensor_ok = data["sensor_ok"]
            self.diagnostics.set(
                f"Sensor: {'OK' if data['sensor_ok'] else 'SIN LECTURAS'} · "
                f"Ventana: {data['frames']}/100 · Errores I²C: {data['i2c_errors']} · "
                f"Ventanas descartadas: {data['rejected_windows']} · Cola: {data['queue_drops']} · "
                f"Jitter máximo: {data['max_jitter_us'] / 1000:.2f} ms")
            if not data["sensor_ok"]:
                self.clear_live("Sin lecturas del sensor")
            return
        if event.kind == "error":
            if not self.tracker.observe_boot(data["boot_id"]):
                return
            self.clear_live("Error de inferencia")
            self.last_prediction_at = 0
            self.message.set(f"{data['message']} · Código {data['code']}")
            return
        if event.kind != "prediction" or not self.tracker.accept(data):
            return
        if time.monotonic() - event.received_at > STALE_SECONDS or data["lag_ms"] > 4000:
            self.message.set("Se descartó una predicción atrasada.")
            return
        self.last_prediction_at = event.received_at
        self.banner_stale = False
        self.last_sensor_ok = True
        self.prediction.set(DISPLAY_NAMES[data["label"]])
        self.confidence.set(f"{data['confidence'] * 100:.1f} %")
        for key in CLASSES:
            self.probabilities[key].set(data["probabilities"][key] * 100)
            self.probability_text[key].set(f"{data['probabilities'][key] * 100:.1f} %")
        self.timings.set(f"DSP: {data['dsp_ms']:.3f} ms    Inferencia: {data['inference_ms']:.3f} ms    "
                         f"Procesamiento total: {data['total_ms']:.3f} ms")
        expected = eligible_activity(self.selected_activity(), self.label_changed_at, event)
        evaluation = validation_result(expected, data["label"])
        self.received += 1
        self.uncertain += int(data["label"] == "incierto")
        if evaluation != "sin_evaluar":
            self.validation_counts[evaluation] += 1
        item = self.table.insert("", "end", values=(
            datetime.now().strftime("%H:%M:%S"), data["seq"], DISPLAY_NAMES[data["label"]],
            f"{data['confidence'] * 100:.1f} %", DISPLAY_NAMES.get(expected, expected),
            evaluation.replace("_", " ").capitalize(), f"{data['total_ms']:.3f}"))
        children = self.table.get_children()
        if len(children) > 200:
            self.table.delete(children[0])
        self.table.see(item)
        self.refresh_metrics()
        if self.args.demo:
            self.connection.set("DEMOSTRACIÓN · datos simulados")
            self.diagnostics.set("Simulación de la interfaz: estos tiempos y probabilidades no son mediciones del ESP32-S3.")
        if self.logger:
            try:
                self.logger.write(data, expected)
                self.recording.set(f"Guardando: {self.logger.path.name} · {self.logger.rows} filas")
            except OSError as exc:
                self.message.set(f"Error al guardar CSV: {exc}")
                self.stop_recording()

    def poll(self):
        if self.receiver:
            for _ in range(50):
                try:
                    event = self.receiver.events.get_nowait()
                except queue.Empty:
                    break
                self.handle(event)
            now = time.monotonic()
            if not self.args.demo and now - self.receiver.last_rx > STALE_SECONDS:
                self.connection.set("Sin respuesta · reintentando registro")
            if self.last_prediction_at and now - self.last_prediction_at > STALE_SECONDS and not self.banner_stale:
                self.clear_live("Sin inferencias recientes")
        self.root.after(100, self.poll)

    def close(self):
        self.disconnect()
        self.root.destroy()


def run_console(args):
    receiver = DemoReceiver() if args.demo else UDPReceiver(args.ip, args.port, args.local_port)
    logger = CSVLogger(args.csv, args.subject) if args.csv else None
    tracker = SequenceTracker()
    started = time.monotonic()
    count = 0
    try:
        receiver.start()
        print("DEMO: DATOS SIMULADOS" if args.demo else f"UDP {args.local_port}; destino {args.ip}:{args.port}. Ctrl+C para finalizar.", flush=True)
        while True:
            try:
                event = receiver.events.get(timeout=0.5)
            except queue.Empty:
                continue
            data = event.payload
            if event.kind == "warning":
                print("Aviso:", data, flush=True)
            elif event.kind == "info":
                tracker.observe_boot(data["boot_id"])
                print(f"Modelo INT8 | Kit {data['kit']} | normalización incluida | umbral {data['threshold']:.2f}", flush=True)
            elif event.kind == "error":
                print("Error de inferencia:", data, flush=True)
            elif event.kind == "prediction" and tracker.accept(data):
                if data["lag_ms"] > 4000 or time.monotonic() - event.received_at > STALE_SECONDS:
                    continue
                expected = eligible_activity(args.activity, started, event)
                print(f"{data['seq']:5d} | {data['label']:20s} | {data['confidence'] * 100:5.1f} % | "
                      f"DSP {data['dsp_ms']:.3f} ms | NN {data['inference_ms']:.3f} ms", flush=True)
                if logger:
                    logger.write(data, expected)
                count += 1
                if args.limit and count >= args.limit:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
        if logger:
            logger.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="TinyWear: inferencias locales por Wi-Fi/UDP")
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP del ESP32-S3")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Puerto UDP del ESP32")
    parser.add_argument("--local-port", type=int, default=DEFAULT_PORT, help="Puerto UDP local")
    parser.add_argument("--subject", default="S01", help="Identificador del participante")
    parser.add_argument("--demo", action="store_true", help="Interfaz con datos simulados; no usa el modelo")
    parser.add_argument("--console", action="store_true", help="Modo terminal sin interfaz gráfica")
    parser.add_argument("--csv", help="Archivo CSV para el modo terminal")
    parser.add_argument("--activity", choices=CLASSES, default="sin_etiquetar", help="Actividad real en modo terminal")
    parser.add_argument("--limit", type=int, default=0, help="Ventanas antes de finalizar el modo terminal; 0=continuo")
    args = parser.parse_args(argv)
    try:
        if args.console:
            return run_console(args)
        if tk is None:
            print("Falta Tkinter. Instalar Python con Tcl/Tk o utilizar --console.", file=sys.stderr)
            return 1
        root = tk.Tk()
        TinyWearGUI(root, args)
        root.mainloop()
        return 0
    except (OSError, ValueError) as exc:
        print(f"TinyWear: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if tk is not None and isinstance(exc, tk.TclError):
            print(f"No fue posible abrir la interfaz gráfica: {exc}. Utilizar --console si no hay pantalla.", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
