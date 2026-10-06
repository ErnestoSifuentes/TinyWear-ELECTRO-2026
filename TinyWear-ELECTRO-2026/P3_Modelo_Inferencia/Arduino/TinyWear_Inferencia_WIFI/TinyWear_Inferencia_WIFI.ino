/*
  TinyWear: inferencia local por Wi-Fi / UDP.
  ESP32-S3 + MPU6050 | Taller ELECTRO 2026.
  Elaborado para Ernesto Sifuentes de la Hoya.

  Abrir ESTE archivo en Arduino IDE. Los archivos .h y .cpp de
  esta misma carpeta son parte del programa y deben conservarse.
  Ajustar KIT_ID y los pines en TinyWearConfig.h.
*/
#include <Arduino.h>
#include "TinyWearApp.h"

void setup() {
  tinywearBegin();                              // Inicia sensor, modelo, tareas y Wi-Fi.
}

void loop() {
  tinywearUpdate();                             // Atiende la red y publica las predicciones.
}
