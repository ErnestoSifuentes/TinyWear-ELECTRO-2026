"""
P5_Capturador_Dataset_TinyWear_WIFI.py
TinyWear - ELECTRO 2026

Interfaz para capturar el dataset por Wi-Fi / UDP.

La laptop debe estar conectada a:
    SSID: TinyWear-1
    Password: TinyWear2026

El ESP32-S3 transmite:
    seq,t_ms,ax,ay,az,gx,gy,gz
"""

import csv
import os
import queue
import re
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError:
    FigureCanvasTkAgg = None
    Figure = None


ESP_IP = "192.168.4.1"
UDP_PORT = 5005
FS_HZ = 50

ACTIVITIES = [
    ("reposo", "Reposo / de pie"),
    ("caminar", "Caminar"),
    ("sentarse_levantarse", "Sentarse / levantarse"),
]

SPLITS = [
    ("entrenamiento", "Entrenamiento"),
    ("prueba", "Prueba"),
]


class UDPReceiver:
    def __init__(self):
        self.sock = None
        self.thread = None
        self.running = False

        self.data_queue = queue.Queue(
            maxsize=10000
        )

        self.packet_count = 0
        self.last_ip = ""
        self.last_packet_time = 0.0

        self.ack_received = False

    def start(self):
        if self.running:
            return

        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        self.sock.bind(
            ("0.0.0.0", UDP_PORT)
        )

        self.sock.settimeout(
            0.5
        )

        self.running = True

        self.thread = threading.Thread(
            target=self._worker,
            daemon=True
        )

        self.thread.start()

    def _send_hello(self):
        if self.sock is None:
            return

        try:
            self.sock.sendto(
                b"TINYWEAR_HELLO",
                (ESP_IP, UDP_PORT)
            )
        except OSError:
            pass

    def _send_keepalive(self):
        if self.sock is None:
            return

        try:
            self.sock.sendto(
                b"TINYWEAR_KEEPALIVE",
                (ESP_IP, UDP_PORT)
            )
        except OSError:
            pass

    def _worker(self):
        last_hello = 0.0
        last_keepalive = 0.0

        while self.running:
            now = time.time()

            if (
                not self.ack_received
                and
                now - last_hello >= 1.0
            ):
                self._send_hello()
                last_hello = now

            if (
                self.ack_received
                and
                now - last_keepalive >= 2.0
            ):
                self._send_keepalive()
                last_keepalive = now

            try:
                data, addr = (
                    self.sock.recvfrom(
                        1024
                    )
                )

            except socket.timeout:
                continue

            except OSError:
                break

            text = data.decode(
                "utf-8",
                errors="ignore"
            ).strip()

            if text == "TINYWEAR_ACK":
                self.ack_received = True
                self.last_ip = addr[0]
                continue

            parts = text.split(",")

            if len(parts) != 8:
                continue

            try:
                row = {
                    "seq":
                        int(parts[0]),

                    "device_t_ms":
                        int(parts[1]),

                    "ax":
                        float(parts[2]),

                    "ay":
                        float(parts[3]),

                    "az":
                        float(parts[4]),

                    "gx":
                        float(parts[5]),

                    "gy":
                        float(parts[6]),

                    "gz":
                        float(parts[7]),
                }

            except ValueError:
                continue

            self.packet_count += 1
            self.last_ip = addr[0]
            self.last_packet_time = time.time()

            try:
                self.data_queue.put_nowait(
                    row
                )

            except queue.Full:
                try:
                    self.data_queue.get_nowait()
                except queue.Empty:
                    pass

                try:
                    self.data_queue.put_nowait(
                        row
                    )
                except queue.Full:
                    pass

    def clear_queue(self):
        while True:
            try:
                self.data_queue.get_nowait()

            except queue.Empty:
                break

    def stop(self):
        self.running = False

        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass

            self.sock = None


class TinyWearApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(
            "TinyWear - Capturador de Dataset Wi-Fi FINAL V3"
        )

        self.geometry("1260x790")
        self.minsize(1050, 680)

        self.receiver = UDPReceiver()

        try:
            self.receiver.start()

        except OSError as exc:
            messagebox.showerror(
                "Puerto UDP",
                f"No fue posible abrir el puerto {UDP_PORT}.\n\n{exc}"
            )

        self.subject_var = tk.StringVar(value="S01")
        self.activity_var = tk.StringVar(value="reposo")
        self.split_var = tk.StringVar(value="entrenamiento")

        self.duration_var = tk.IntVar(value=20)
        self.countdown_var = tk.IntVar(value=3)

        self.goal_train_var = tk.IntVar(value=5)
        self.goal_test_var = tk.IntVar(value=2)

        self.base_dir = tk.StringVar(
            value=str(
                Path.cwd() / "Dataset_TinyWear"
            )
        )

        self.network_var = tk.StringVar(
            value="Esperando datos UDP..."
        )

        self.status_var = tk.StringVar(
            value="Conecte Windows a la red TinyWear-1."
        )

        self.samples_var = tk.StringVar(
            value="0 muestras"
        )

        self.capture_thread = None

        self.last_data = {
            "t": [],
            "ax": [],
            "ay": [],
            "az": [],
            "gx": [],
            "gy": [],
            "gz": [],
        }

        self._build_ui()
        self.refresh_progress()

        self.after(
            500,
            self._refresh_network_status
        )

        self.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

    def _build_ui(self):
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Header
        header = ttk.Frame(
            self,
            padding=(18, 12, 18, 8)
        )

        header.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew"
        )

        ttk.Label(
            header,
            text="TinyWear - Capturador de Dataset Wi-Fi FINAL V3",
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=(
                "ESP32-S3 + MPU6050 | Wi-Fi directo + UDP unicast | "
                "Reconocimiento de actividad humana"
            ),
            font=("Segoe UI", 10),
        ).pack(
            anchor="w",
            pady=(3, 0)
        )

        # Left panel
        panel = ttk.Frame(
            self,
            padding=14
        )

        panel.grid(
            row=1,
            column=0,
            sticky="nsw"
        )

        # Right
        right = ttk.Frame(
            self,
            padding=(6, 8, 18, 8)
        )

        right.grid(
            row=1,
            column=1,
            sticky="nsew"
        )

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # Network
        conn = ttk.LabelFrame(
            panel,
            text="1. Comunicación Wi-Fi",
            padding=12
        )

        conn.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        ttk.Label(
            conn,
            text="Red: TinyWear-1",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            conn,
            text="Password: TinyWear2026"
        ).pack(
            anchor="w",
            pady=(3, 0)
        )

        ttk.Label(
            conn,
            text="UDP unicast: puerto 5005"
        ).pack(
            anchor="w",
            pady=(3, 7)
        )

        ttk.Label(
            conn,
            textvariable=self.network_var,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        # Capture config
        cfg = ttk.LabelFrame(
            panel,
            text="2. Configuración de captura",
            padding=12
        )

        cfg.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        ttk.Label(
            cfg,
            text="Participante"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        ttk.Entry(
            cfg,
            textvariable=self.subject_var,
            width=15
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(8, 0)
        )

        ttk.Label(
            cfg,
            text="Actividad"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(10, 2)
        )

        row_idx = 2

        for value, label in ACTIVITIES:
            ttk.Radiobutton(
                cfg,
                text=label,
                value=value,
                variable=self.activity_var,
            ).grid(
                row=row_idx,
                column=0,
                columnspan=2,
                sticky="w"
            )

            row_idx += 1

        ttk.Label(
            cfg,
            text="Destino"
        ).grid(
            row=row_idx,
            column=0,
            sticky="w",
            pady=(10, 2)
        )

        row_idx += 1

        for value, label in SPLITS:
            ttk.Radiobutton(
                cfg,
                text=label,
                value=value,
                variable=self.split_var,
            ).grid(
                row=row_idx,
                column=0,
                columnspan=2,
                sticky="w"
            )

            row_idx += 1

        ttk.Label(
            cfg,
            text="Duración nominal (s)"
        ).grid(
            row=row_idx,
            column=0,
            sticky="w",
            pady=(10, 0)
        )

        ttk.Spinbox(
            cfg,
            from_=5,
            to=60,
            textvariable=self.duration_var,
            width=8
        ).grid(
            row=row_idx,
            column=1,
            sticky="w",
            padx=(8, 0),
            pady=(10, 0)
        )

        row_idx += 1

        ttk.Label(
            cfg,
            text="Cuenta regresiva (s)"
        ).grid(
            row=row_idx,
            column=0,
            sticky="w",
            pady=(6, 0)
        )

        ttk.Spinbox(
            cfg,
            from_=0,
            to=10,
            textvariable=self.countdown_var,
            width=8
        ).grid(
            row=row_idx,
            column=1,
            sticky="w",
            padx=(8, 0),
            pady=(6, 0)
        )

        row_idx += 1

        ttk.Label(
            cfg,
            text="Frecuencia"
        ).grid(
            row=row_idx,
            column=0,
            sticky="w",
            pady=(6, 0)
        )

        ttk.Label(
            cfg,
            text="50 Hz (fija) | N = duración × 50",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=row_idx,
            column=1,
            sticky="w",
            padx=(8, 0),
            pady=(6, 0)
        )

        row_idx += 1

        self.capture_btn = ttk.Button(
            cfg,
            text="CAPTURAR MUESTRA",
            command=self.start_capture
        )

        self.capture_btn.grid(
            row=row_idx,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(14, 0)
        )

        # Folder
        folder = ttk.LabelFrame(
            panel,
            text="3. Carpeta del dataset",
            padding=12
        )

        folder.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        ttk.Entry(
            folder,
            textvariable=self.base_dir,
            width=34
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew"
        )

        ttk.Button(
            folder,
            text="Cambiar carpeta",
            command=self.choose_folder
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(7, 0),
            padx=(0, 4)
        )

        ttk.Button(
            folder,
            text="Abrir carpeta",
            command=self.open_folder
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(7, 0),
            padx=(4, 0)
        )

        # Progress
        progress = ttk.LabelFrame(
            panel,
            text="4. Progreso del dataset",
            padding=12
        )

        progress.grid(
            row=3,
            column=0,
            sticky="ew"
        )

        ttk.Label(
            progress,
            text="Meta entrenamiento/clase"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        ttk.Spinbox(
            progress,
            from_=1,
            to=50,
            textvariable=self.goal_train_var,
            width=6,
            command=self.refresh_progress
        ).grid(
            row=0,
            column=1,
            sticky="e"
        )

        ttk.Label(
            progress,
            text="Meta prueba/clase"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(4, 8)
        )

        ttk.Spinbox(
            progress,
            from_=1,
            to=30,
            textvariable=self.goal_test_var,
            width=6,
            command=self.refresh_progress
        ).grid(
            row=1,
            column=1,
            sticky="e",
            pady=(4, 8)
        )

        self.progress_labels = {}

        for idx, (value, label) in enumerate(
            ACTIVITIES,
            start=2
        ):
            lbl = ttk.Label(
                progress,
                text=f"{label}: E 0/5 | P 0/2",
                font=("Segoe UI", 9, "bold"),
            )

            lbl.grid(
                row=idx,
                column=0,
                columnspan=2,
                sticky="w",
                pady=2
            )

            self.progress_labels[value] = lbl

        # Graphs
        graph_box = ttk.LabelFrame(
            right,
            text="Última muestra capturada",
            padding=8
        )

        graph_box.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        graph_box.columnconfigure(0, weight=1)
        graph_box.rowconfigure(0, weight=1)

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                graph_box,
                text=(
                    "Instale matplotlib para visualizar señales:\n"
                    "python -m pip install matplotlib"
                ),
                justify="center"
            ).grid(
                row=0,
                column=0,
                sticky="nsew"
            )

            self.ax_acc = None
            self.ax_gyro = None

        else:
            notebook = ttk.Notebook(graph_box)

            notebook.grid(
                row=0,
                column=0,
                sticky="nsew"
            )

            # Accelerometer
            tab_acc = ttk.Frame(notebook)
            tab_acc.rowconfigure(0, weight=1)
            tab_acc.columnconfigure(0, weight=1)

            notebook.add(
                tab_acc,
                text="Acelerómetro"
            )

            self.fig_acc = Figure(
                figsize=(8.4, 5.0),
                dpi=100
            )

            self.ax_acc = self.fig_acc.add_subplot(111)

            self.canvas_acc = FigureCanvasTkAgg(
                self.fig_acc,
                master=tab_acc
            )

            self.canvas_acc.get_tk_widget().grid(
                row=0,
                column=0,
                sticky="nsew"
            )

            # Gyroscope
            tab_gyro = ttk.Frame(notebook)
            tab_gyro.rowconfigure(0, weight=1)
            tab_gyro.columnconfigure(0, weight=1)

            notebook.add(
                tab_gyro,
                text="Giroscopio"
            )

            self.fig_gyro = Figure(
                figsize=(8.4, 5.0),
                dpi=100
            )

            self.ax_gyro = self.fig_gyro.add_subplot(111)

            self.canvas_gyro = FigureCanvasTkAgg(
                self.fig_gyro,
                master=tab_gyro
            )

            self.canvas_gyro.get_tk_widget().grid(
                row=0,
                column=0,
                sticky="nsew"
            )

            self._plot_empty()

        # Status
        status = ttk.Frame(
            self,
            padding=(18, 0, 18, 12)
        )

        status.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew"
        )

        ttk.Label(
            status,
            textvariable=self.status_var
        ).pack(side="left")

        ttk.Label(
            status,
            textvariable=self.samples_var,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")

    def _plot_empty(self):
        if self.ax_acc is not None:
            self.ax_acc.clear()
            self.ax_acc.set_title("Acelerómetro")
            self.ax_acc.set_xlabel("Tiempo (s)")
            self.ax_acc.set_ylabel("Aceleración (g)")
            self.ax_acc.grid(True, alpha=0.25)
            self.fig_acc.tight_layout()
            self.canvas_acc.draw_idle()

        if self.ax_gyro is not None:
            self.ax_gyro.clear()
            self.ax_gyro.set_title("Giroscopio")
            self.ax_gyro.set_xlabel("Tiempo (s)")
            self.ax_gyro.set_ylabel("Velocidad angular (°/s)")
            self.ax_gyro.grid(True, alpha=0.25)
            self.fig_gyro.tight_layout()
            self.canvas_gyro.draw_idle()

    def _refresh_network_status(self):
        age = time.time() - self.receiver.last_packet_time

        if (
            self.receiver.packet_count > 0
            and age < 2.0
        ):
            self.network_var.set(
                "RECIBIENDO UNICAST ✓ | "
                f"{self.receiver.last_ip} | "
                f"{self.receiver.packet_count} paquetes"
            )

        elif self.receiver.ack_received:
            self.network_var.set(
                "TinyWear conectado ✓ | esperando datos..."
            )

        else:
            self.network_var.set(
                "Registrando laptop con TinyWear..."
            )

        self.after(
            500,
            self._refresh_network_status
        )

    def start_capture(self):
        age = time.time() - self.receiver.last_packet_time

        if (
            self.receiver.packet_count == 0
            or age >= 2.0
        ):
            messagebox.showwarning(
                "TinyWear",
                (
                    "No se están recibiendo datos UDP.\n\n"
                    "Conecte Windows a TinyWear-1 y verifique "
                    "el firmware del ESP32-S3."
                )
            )
            return

        subject = self.subject_var.get().strip()

        if not subject:
            messagebox.showwarning(
                "Participante",
                "Indique un identificador, por ejemplo S01."
            )
            return

        if (
            self.capture_thread is not None
            and self.capture_thread.is_alive()
        ):
            return

        self.capture_btn.config(
            state="disabled"
        )

        self.capture_thread = threading.Thread(
            target=self._capture_worker,
            daemon=True
        )

        self.capture_thread.start()

    def _capture_worker(self):
        subject = self.subject_var.get().strip()
        activity = self.activity_var.get()
        split = self.split_var.get()

        duration = int(
            self.duration_var.get()
        )

        countdown = int(
            self.countdown_var.get()
        )

        target_samples = duration * FS_HZ

        try:
            for sec in range(
                countdown,
                0,
                -1
            ):
                self._set_status(
                    f"Prepárese: {sec}..."
                )
                time.sleep(1)

            self.receiver.clear_queue()

            activity_name = dict(ACTIVITIES)[activity]

            self._set_status(
                f"CAPTURANDO: {activity_name} | "
                f"{target_samples} muestras"
            )

            rows = []

            # Límite de seguridad:
            # si hay pérdidas importantes no queremos esperar indefinidamente.
            timeout_s = duration + 8
            t0 = time.time()

            while len(rows) < target_samples:
                if time.time() - t0 > timeout_s:
                    break

                try:
                    row = self.receiver.data_queue.get(
                        timeout=0.5
                    )

                except queue.Empty:
                    continue

                rows.append(row)

                if len(rows) % 25 == 0:
                    self._set_sample_count(
                        f"{len(rows)}/{target_samples} muestras"
                    )

            if not rows:
                raise RuntimeError(
                    "No se recibieron muestras durante la captura."
                )

            # Si no se alcanzó el objetivo, no guardamos una muestra incompleta.
            if len(rows) < target_samples:
                raise RuntimeError(
                    f"Captura incompleta: {len(rows)}/{target_samples} muestras.\n"
                    "Repita la medición."
                )

            # Nos aseguramos de guardar exactamente target_samples.
            rows = rows[:target_samples]

            # Calcular pérdidas a partir de la secuencia real.
            lost = 0
            previous = None

            for row in rows:
                current = row["seq"]

                if previous is not None:
                    expected_seq = previous + 1

                    if current > expected_seq:
                        lost += current - expected_seq

                previous = current

            total_transmitted = target_samples + lost

            reception = (
                100.0
                * target_samples
                / total_transmitted
                if total_transmitted > 0
                else 0.0
            )

            out_dir = (
                Path(self.base_dir.get())
                / split
                / activity
            )

            out_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            repetition = self._next_index(
                out_dir,
                subject,
                activity
            )

            filename = (
                f"{subject}_{activity}_{repetition:03d}.csv"
            )

            out_file = out_dir / filename

            first_ms = rows[0]["device_t_ms"]

            with out_file.open(
                "w",
                newline="",
                encoding="utf-8"
            ) as f:
                writer = csv.writer(f)

                writer.writerow([
                    "timestamp",
                    "ax",
                    "ay",
                    "az",
                    "gx",
                    "gy",
                    "gz",
                ])

                for row in rows:
                    t_ms = (
                        row["device_t_ms"]
                        - first_ms
                    )

                    writer.writerow([
                        t_ms,
                        f'{row["ax"]:.6f}',
                        f'{row["ay"]:.6f}',
                        f'{row["az"]:.6f}',
                        f'{row["gx"]:.6f}',
                        f'{row["gy"]:.6f}',
                        f'{row["gz"]:.6f}',
                    ])

            self._append_log(
                subject=subject,
                activity=activity,
                split=split,
                repetition=repetition,
                duration=duration,
                samples=target_samples,
                expected=target_samples,
                reception=reception,
                lost=lost,
                filename=str(out_file),
            )

            self.last_data = {
                "t": [
                    (
                        row["device_t_ms"]
                        - first_ms
                    ) / 1000.0
                    for row in rows
                ],
                "ax": [row["ax"] for row in rows],
                "ay": [row["ay"] for row in rows],
                "az": [row["az"] for row in rows],
                "gx": [row["gx"] for row in rows],
                "gy": [row["gy"] for row in rows],
                "gz": [row["gz"] for row in rows],
            }

            self.after(
                0,
                self._plot_last
            )

            self.after(
                0,
                self.refresh_progress
            )

            self._set_status(
                f"{filename} guardado | "
                f"{target_samples} muestras | "
                f"Recepción {reception:.1f}% | "
                f"Perdidos {lost}"
            )

            self._set_sample_count(
                f"{target_samples}/{target_samples} muestras"
            )

            if reception < 98.0:
                self.after(
                    0,
                    lambda r=reception, l=lost: messagebox.showwarning(
                        "Calidad de captura",
                        (
                            f"Muestras: {target_samples}\n"
                            f"Recepción: {r:.1f}%\n"
                            f"Paquetes perdidos: {l}\n\n"
                            "Conviene repetir esta muestra."
                        )
                    )
                )
            else:
                self.after(
                    0,
                    lambda f=filename, r=reception, l=lost: messagebox.showinfo(
                        "Captura completada",
                        (
                            f"{f}\n\n"
                            f"Muestras válidas: {target_samples}\n"
                            f"Recepción: {r:.1f}%\n"
                            f"Paquetes perdidos: {l}"
                        )
                    )
                )

        except Exception as exc:
            error_text = str(exc).strip() or repr(exc)

            self._set_status(
                "Error durante la captura."
            )

            self.after(
                0,
                lambda e=error_text: messagebox.showerror(
                    "TinyWear",
                    e
                )
            )

        finally:
            self.after(
                0,
                lambda: self.capture_btn.config(
                    state="normal"
                )
            )

    def _next_index(
        self,
        folder,
        subject,
        activity
    ):
        nums = []

        pattern = re.compile(
            rf"^{re.escape(subject)}_"
            rf"{re.escape(activity)}_(\d+)\.csv$"
        )

        for file in folder.glob("*.csv"):
            match = pattern.match(file.name)

            if match:
                nums.append(
                    int(match.group(1))
                )

        return (
            max(nums) + 1
            if nums
            else 1
        )

    def _append_log(
        self,
        subject,
        activity,
        split,
        repetition,
        duration,
        samples,
        expected,
        reception,
        lost,
        filename
    ):
        base = Path(
            self.base_dir.get()
        )

        base.mkdir(
            parents=True,
            exist_ok=True
        )

        log_file = (
            base / "registro_capturas.csv"
        )

        new_file = not log_file.exists()

        with log_file.open(
            "a",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)

            if new_file:
                writer.writerow([
                    "fecha_hora",
                    "subject",
                    "split",
                    "activity",
                    "repetition",
                    "duration_s",
                    "samples",
                    "expected",
                    "reception_percent",
                    "lost_packets",
                    "filename",
                ])

            writer.writerow([
                datetime.now().isoformat(
                    timespec="seconds"
                ),
                subject,
                split,
                activity,
                repetition,
                duration,
                samples,
                expected,
                round(reception, 2),
                lost,
                filename,
            ])

    def refresh_progress(self):
        try:
            train_goal = int(
                self.goal_train_var.get()
            )
        except Exception:
            train_goal = 5

        try:
            test_goal = int(
                self.goal_test_var.get()
            )
        except Exception:
            test_goal = 2

        base = Path(
            self.base_dir.get()
        )

        for value, label in ACTIVITIES:
            train_dir = (
                base
                / "entrenamiento"
                / value
            )

            test_dir = (
                base
                / "prueba"
                / value
            )

            train_count = (
                len(list(train_dir.glob("*.csv")))
                if train_dir.exists()
                else 0
            )

            test_count = (
                len(list(test_dir.glob("*.csv")))
                if test_dir.exists()
                else 0
            )

            self.progress_labels[value].config(
                text=(
                    f"{label}: "
                    f"E {train_count}/{train_goal} | "
                    f"P {test_count}/{test_goal}"
                )
            )

    def choose_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self.base_dir.get()
        )

        if folder:
            self.base_dir.set(folder)
            self.refresh_progress()

    def open_folder(self):
        folder = Path(
            self.base_dir.get()
        )

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        try:
            if os.name == "nt":
                os.startfile(folder)

            elif sys.platform == "darwin":
                os.system(
                    f'open "{folder}"'
                )

            else:
                os.system(
                    f'xdg-open "{folder}"'
                )

        except Exception as exc:
            messagebox.showerror(
                "Carpeta",
                str(exc)
            )

    def _plot_last(self):
        if self.ax_acc is not None:
            self.ax_acc.clear()

            self.ax_acc.plot(
                self.last_data["t"],
                self.last_data["ax"],
                label="Ax"
            )

            self.ax_acc.plot(
                self.last_data["t"],
                self.last_data["ay"],
                label="Ay"
            )

            self.ax_acc.plot(
                self.last_data["t"],
                self.last_data["az"],
                label="Az"
            )

            self.ax_acc.set_title(
                "Acelerómetro"
            )

            self.ax_acc.set_xlabel(
                "Tiempo (s)"
            )

            self.ax_acc.set_ylabel(
                "Aceleración (g)"
            )

            self.ax_acc.grid(
                True,
                alpha=0.25
            )

            self.ax_acc.legend(
                loc="upper right"
            )

            self.fig_acc.tight_layout()
            self.canvas_acc.draw_idle()

        if self.ax_gyro is not None:
            self.ax_gyro.clear()

            self.ax_gyro.plot(
                self.last_data["t"],
                self.last_data["gx"],
                label="Gx"
            )

            self.ax_gyro.plot(
                self.last_data["t"],
                self.last_data["gy"],
                label="Gy"
            )

            self.ax_gyro.plot(
                self.last_data["t"],
                self.last_data["gz"],
                label="Gz"
            )

            self.ax_gyro.set_title(
                "Giroscopio"
            )

            self.ax_gyro.set_xlabel(
                "Tiempo (s)"
            )

            self.ax_gyro.set_ylabel(
                "Velocidad angular (°/s)"
            )

            self.ax_gyro.grid(
                True,
                alpha=0.25
            )

            self.ax_gyro.legend(
                loc="upper right"
            )

            self.fig_gyro.tight_layout()
            self.canvas_gyro.draw_idle()

    def _set_status(self, text):
        self.after(
            0,
            lambda: self.status_var.set(text)
        )

    def _set_sample_count(self, text):
        self.after(
            0,
            lambda: self.samples_var.set(text)
        )

    def on_close(self):
        try:
            self.receiver.stop()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = TinyWearApp()
    app.mainloop()
