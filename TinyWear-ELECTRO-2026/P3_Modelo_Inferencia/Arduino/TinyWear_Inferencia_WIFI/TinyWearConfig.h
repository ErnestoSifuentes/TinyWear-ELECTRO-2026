#pragma once
#include <stdint.h>

// Configuracion conservada de la practica de adquisicion.
constexpr uint16_t KIT_ID = 1;                  // Kit 1 -> red TinyWear-1; cambiar por equipo.
constexpr int SDA_PIN = 8;                     // Mantener el mismo cableado utilizado en P1/P2.
constexpr int SCL_PIN = 9;
constexpr const char *WIFI_PASSWORD = "TinyWear2026";
constexpr uint16_t UDP_PORT = 5005;             // Mismo puerto y registro HELLO/ACK de P1.
constexpr uint32_t CLIENT_TIMEOUT_MS = 6000;    // Python renueva el registro cada dos segundos.
constexpr uint32_t MAX_SAMPLE_JITTER_US = 5000;// Descarta la ventana si una lectura llega tarde.
constexpr bool SERIAL_RESULTS = true;          // Tambien muestra inferencias sin computadora Wi-Fi.
static_assert(KIT_ID >= 1, "KIT_ID debe ser mayor o igual a 1");
