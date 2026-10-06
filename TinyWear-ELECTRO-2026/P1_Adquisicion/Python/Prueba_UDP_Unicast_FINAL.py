"""
TinyWear - Receptor UDP UNICAST V2

1. Conecte Windows a:
       TinyWear-1

2. Password:
       TinyWear2026

3. Ejecute este programa.

El programa registra automaticamente la laptop
con el ESP32-S3 y recibe datos unicast.
"""

import socket
import time

ESP_IP = "192.168.4.1"
UDP_PORT = 5005

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

sock.bind(
    ("0.0.0.0", UDP_PORT)
)

sock.settimeout(1.0)

print(
    "Registrando laptop con TinyWear..."
)

sock.sendto(
    b"TINYWEAR_HELLO",
    (ESP_IP, UDP_PORT)
)

last_keepalive = time.time()
count = 0
first_seq = None
last_seq = None
lost = 0
t0 = time.time()

print(
    "Escuchando datos UDP unicast..."
)
print()

try:
    while True:
        now = time.time()

        if now - last_keepalive >= 2.0:
            sock.sendto(
                b"TINYWEAR_KEEPALIVE",
                (ESP_IP, UDP_PORT)
            )

            last_keepalive = now

        try:
            data, addr = sock.recvfrom(
                1024
            )

        except socket.timeout:
            print(
                "Sin datos. Verifique que Windows esté conectado a TinyWear-1."
            )

            sock.sendto(
                b"TINYWEAR_HELLO",
                (ESP_IP, UDP_PORT)
            )

            continue

        text = data.decode(
            "utf-8",
            errors="ignore"
        ).strip()

        if text == "TINYWEAR_ACK":
            print(
                "TinyWear ACK recibido ✓"
            )
            continue

        parts = text.split(",")

        if len(parts) != 8:
            continue

        try:
            seq = int(parts[0])

        except ValueError:
            continue

        count += 1

        if first_seq is None:
            first_seq = seq

        if last_seq is not None:
            expected = last_seq + 1

            if seq > expected:
                lost += (
                    seq - expected
                )

        last_seq = seq

        if count <= 10 or count % 50 == 0:
            elapsed = time.time() - t0

            rate = (
                count / elapsed
                if elapsed > 0
                else 0.0
            )

            print(
                f"{count:6d} | "
                f"seq={seq:6d} | "
                f"{rate:5.1f} pkt/s | "
                f"perdidos={lost}"
            )

except KeyboardInterrupt:
    pass

finally:
    sock.close()

print()
print(
    "Paquetes recibidos:",
    count
)

print(
    "Paquetes perdidos:",
    lost
)
