/*
  Inferencia TinyWear: MPU6050 -> DSP -> Standard Scaler -> INT8.
  La normalizacion YA esta incluida en la biblioteca exportada.
  Se conservan unidades, orden de ejes y registros del firmware P1.
  No se resta la gravedad, no se recalibran offsets y no se normaliza
  cada ventana en este programa: hacerlo cambiaria los datos del modelo.
*/
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <Taller_TinyWear_inferencing.h>
#include <math.h>
#include <string.h>
#include "TinyWearConfig.h"
#include "TinyWearApp.h"

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Seleccionar una tarjeta ESP32-S3 en Arduino IDE."
#endif

static_assert(EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME == 6, "El modelo debe usar seis ejes.");
static_assert(EI_CLASSIFIER_RAW_SAMPLE_COUNT == 100, "Esta version requiere ventanas de 100 lecturas.");
static_assert(EI_CLASSIFIER_INTERVAL_MS == 20, "Esta version requiere 50 Hz.");
static_assert(EI_CLASSIFIER_LABEL_COUNT == 3, "El modelo debe tener tres actividades.");
static_assert(EI_CLASSIFIER_HAS_DATA_NORMALIZATION == 1, "Falta la normalizacion exportada.");

namespace {
constexpr uint32_t PERIOD_US = 20000;           // Una lectura de los seis ejes cada 20 ms.
constexpr float ACCEL_SCALE = 8192.0f;         // MPU6050 configurado a +/-4 g.
constexpr float GYRO_SCALE = 65.5f;            // MPU6050 configurado a +/-500 grados/s.
constexpr float THRESHOLD = EI_CLASSIFIER_THRESHOLD; // 0.60 en la biblioteca proporcionada.
constexpr uint32_t STATUS_INTERVAL_MS = 2000;

struct InputWindow {
  float values[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE]; // 100 x 6 = 600 valores, intercalados.
  uint32_t seq;
  uint32_t startMs;
  uint32_t endMs;
  uint32_t maxJitterUs;
};

struct Prediction {
  uint32_t seq, startMs, endMs, maxJitterUs;
  float scores[EI_CLASSIFIER_LABEL_COUNT];
  float dspMs, inferenceMs, totalMs;
  int error;
};

struct AcquisitionStatus {
  uint32_t completedWindows = 0;
  uint32_t rejectedWindows = 0;
  uint32_t i2cErrors = 0;
  uint32_t lateSamples = 0;
  uint32_t queueDrops = 0;
  uint32_t lastSampleMs = 0;
  uint32_t maxJitterUs = 0;
  uint16_t framesInWindow = 0;
};

WiFiUDP udp;                                  // Solo loop() utiliza esta instancia de UDP.
IPAddress clientIP;
uint16_t clientPort = 0;
bool clientRegistered = false;
uint32_t lastHelloMs = 0, lastStatusMs = 0;
uint8_t mpuAddress = 0x68;
char bootID[9];                               // Identifica reinicios para ordenar las predicciones.
char ssid[32];
QueueHandle_t windowQueue = nullptr;
QueueHandle_t predictionQueue = nullptr;
portMUX_TYPE statusMux = portMUX_INITIALIZER_UNLOCKED;
AcquisitionStatus sharedStatus;
static InputWindow inferenceWindow;           // Solo la tarea de inferencia accede a este buffer.

void fatal(const char *message) {
  Serial.println(message);
  while (true) delay(1000);
}

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(mpuAddress, uint8_t(1)) != 1) return false;
  value = uint8_t(Wire.read());
  return true;
}

bool initMPU6050() {
  bool found = false;
  for (uint8_t address : {uint8_t(0x68), uint8_t(0x69)}) {
    mpuAddress = address;
    uint8_t who = 0;
    if (readRegister(0x75, who) && who == 0x68) {
      found = true;
      break;
    }
  }
  if (!found) return false;
  if (!writeRegister(0x6B, 0x00)) return false; // Despierta el sensor igual que en P1.
  delay(100);
  if (!writeRegister(0x1A, 0x03)) return false; // Mismo filtro DLPF de la adquisicion.
  if (!writeRegister(0x19, 19)) return false;   // 1000 Hz / (19 + 1) = 50 Hz.
  if (!writeRegister(0x1B, 0x08)) return false; // Giroscopio: +/-500 grados/s.
  if (!writeRegister(0x1C, 0x08)) return false; // Acelerometro: +/-4 g.
  return true;
}

bool readMPU6050(float *sample) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(0x3B);                            // Primer registro de aceleracion.
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(mpuAddress, uint8_t(14)) != 14) return false;
  int16_t raw[7];
  for (int i = 0; i < 7; ++i) {
    const uint8_t high = uint8_t(Wire.read()); // Lecturas separadas: orden de bytes explicito.
    const uint8_t low = uint8_t(Wire.read());
    raw[i] = int16_t((uint16_t(high) << 8) | low);
  }
  sample[0] = raw[0] / ACCEL_SCALE;            // ax, ay, az en g.
  sample[1] = raw[1] / ACCEL_SCALE;
  sample[2] = raw[2] / ACCEL_SCALE;
  sample[3] = raw[4] / GYRO_SCALE;             // gx, gy, gz en grados/s; se omite temperatura.
  sample[4] = raw[5] / GYRO_SCALE;
  sample[5] = raw[6] / GYRO_SCALE;
  return true;
}

void publishStatus(const AcquisitionStatus &status) {
  portENTER_CRITICAL(&statusMux);
  sharedStatus = status;
  portEXIT_CRITICAL(&statusMux);
}

AcquisitionStatus getStatus() {
  portENTER_CRITICAL(&statusMux);
  AcquisitionStatus copy = sharedStatus;
  portEXIT_CRITICAL(&statusMux);
  return copy;
}

void acquisitionTask(void *) {
  static InputWindow window;                  // Buffer fijo: no se reserva memoria en cada lectura.
  AcquisitionStatus status;
  uint16_t frame = 0;
  int64_t nextUs = esp_timer_get_time() + PERIOD_US;
  while (true) {
    int64_t waitUs = nextUs - esp_timer_get_time();
    if (waitUs > 2000) {
      vTaskDelay(pdMS_TO_TICKS(uint32_t((waitUs - 1000) / 1000)));
      continue;                              // Cede CPU hasta cerca del instante de lectura.
    }
    if (waitUs > 0) delayMicroseconds(uint32_t(waitUs));
    const int64_t actualUs = esp_timer_get_time();
    const uint32_t lateUs = uint32_t(actualUs > nextUs ? actualUs - nextUs : 0);
    const uint32_t jitterUs = lateUs;
    if (lateUs > MAX_SAMPLE_JITTER_US) {
      ++status.lateSamples;
      if (frame > 0) ++status.rejectedWindows;
      frame = 0;                             // No mezcla datos separados por una pausa irregular.
      nextUs = actualUs + PERIOD_US;          // Evita lecturas de recuperacion demasiado cercanas.
    } else {
      nextUs += PERIOD_US;
    }

    float sample[6];
    if (!readMPU6050(sample)) {
      ++status.i2cErrors;
      if (frame > 0) ++status.rejectedWindows;
      frame = 0;                             // Una lectura fallida invalida la ventana parcial.
      status.framesInWindow = 0;
      publishStatus(status);
      continue;                              // Nunca rellena la muestra faltante con ceros.
    }
    const uint32_t sampleMs = millis();
    status.lastSampleMs = sampleMs;
    if (frame == 0) {
      window.startMs = sampleMs;
      window.maxJitterUs = 0;
    }
    memcpy(window.values + size_t(frame) * 6, sample, sizeof(sample));
    if (jitterUs > window.maxJitterUs) window.maxJitterUs = jitterUs;
    if (jitterUs > status.maxJitterUs) status.maxJitterUs = jitterUs;
    ++frame;
    if (frame == EI_CLASSIFIER_RAW_SAMPLE_COUNT) {
      window.seq = status.completedWindows++;
      window.endMs = sampleMs;
      if (xQueueSend(windowQueue, &window, 0) != pdTRUE) ++status.queueDrops;
      frame = 0;                             // Ventanas consecutivas de dos segundos, sin solapamiento.
    }
    status.framesInWindow = frame;
    publishStatus(status);
  }
}

int getSignalData(size_t offset, size_t length, float *out) {
  if (offset > EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE ||
      length > EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE - offset) return -1;
  memcpy(out, inferenceWindow.values + offset, length * sizeof(float));
  return 0;                                  // Valores fisicos; la biblioteca normaliza las features.
}

void inferenceTask(void *) {
  run_classifier_init();
  while (true) {
    if (xQueueReceive(windowQueue, &inferenceWindow, portMAX_DELAY) != pdTRUE) continue;
    signal_t signal;
    signal.total_length = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE;
    signal.get_data = getSignalData;
    ei_impulse_result_t result = {};
    const int64_t startUs = esp_timer_get_time();
    const EI_IMPULSE_ERROR error = run_classifier(&signal, &result, false);
    Prediction prediction = {};
    prediction.seq = inferenceWindow.seq;
    prediction.startMs = inferenceWindow.startMs;
    prediction.endMs = inferenceWindow.endMs;
    prediction.maxJitterUs = inferenceWindow.maxJitterUs;
    prediction.error = int(error);
    prediction.totalMs = float(esp_timer_get_time() - startUs) / 1000.0f;
    if (error == EI_IMPULSE_OK) {
      prediction.dspMs = float(result.timing.dsp_us) / 1000.0f;
      prediction.inferenceMs = float(result.timing.classification_us) / 1000.0f;
      for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; ++i) {
        prediction.scores[i] = result.classification[i].value;
        if (!isfinite(prediction.scores[i])) prediction.error = -999;
      }
    }
    xQueueSend(predictionQueue, &prediction, portMAX_DELAY);
  }
}

bool sendPacket(const char *text) {
  if (!clientRegistered) return false;
  if (!udp.beginPacket(clientIP, clientPort)) return false;
  const size_t length = strlen(text);
  const size_t written = udp.write(reinterpret_cast<const uint8_t *>(text), length);
  return udp.endPacket() == 1 && written == length;
}

void sendInfo() {
  char packet[700];
  snprintf(packet, sizeof(packet),
    "{\"type\":\"info\",\"version\":1,\"boot_id\":\"%s\",\"kit\":%u,"
    "\"model\":\"Taller_TinyWear\",\"model_version\":1,\"fs_hz\":50,"
    "\"window_samples\":100,\"window_ms\":2000,\"features\":78,\"fft_length\":16,"
    "\"normalized\":true,\"quantization\":\"int8\",\"threshold\":%.4f,"
    "\"axes\":[\"ax\",\"ay\",\"az\",\"gx\",\"gy\",\"gz\"],"
    "\"classes\":[\"%s\",\"%s\",\"%s\"]}",
    bootID, unsigned(KIT_ID), double(THRESHOLD),
    ei_classifier_inferencing_categories[0], ei_classifier_inferencing_categories[1],
    ei_classifier_inferencing_categories[2]);
  sendPacket(packet);
}

void checkClient() {
  for (int i = 0; i < 4; ++i) {                // Limita el trabajo de red de cada vuelta.
    const int size = udp.parsePacket();
    if (size <= 0) break;
    const IPAddress sourceIP = udp.remoteIP();
    const uint16_t sourcePort = udp.remotePort();
    char message[64];
    const int length = udp.read(message, sizeof(message) - 1);
    while (udp.available()) udp.read();       // Descarta el sobrante de un datagrama grande.
    if (length <= 0) continue;
    message[length] = '\0';
    const bool hello = strcmp(message, "TINYWEAR_HELLO") == 0;
    const bool keepalive = strcmp(message, "TINYWEAR_KEEPALIVE") == 0;
    if (!hello && !keepalive) continue;
    const bool changed = !clientRegistered || sourceIP != clientIP || sourcePort != clientPort;
    clientIP = sourceIP;
    clientPort = sourcePort;
    clientRegistered = true;
    lastHelloMs = millis();
    sendPacket("TINYWEAR_ACK");               // Conserva la confirmacion del firmware anterior.
    if (hello || changed) {
      sendInfo();
      Serial.printf("Cliente registrado: %s:%u\n", clientIP.toString().c_str(), clientPort);
    }
  }
}

void sendStatus() {
  const AcquisitionStatus status = getStatus();
  const uint32_t age = millis() - status.lastSampleMs;
  char packet[600];
  snprintf(packet, sizeof(packet),
    "{\"type\":\"status\",\"version\":1,\"boot_id\":\"%s\",\"kit\":%u,"
    "\"sensor_ok\":%s,\"frames\":%u,\"completed_windows\":%lu,\"rejected_windows\":%lu,"
    "\"i2c_errors\":%lu,\"late_samples\":%lu,\"queue_drops\":%lu,"
    "\"max_jitter_us\":%lu,\"sample_age_ms\":%lu,\"free_heap\":%lu}",
    bootID, unsigned(KIT_ID), age < 1000 ? "true" : "false", unsigned(status.framesInWindow),
    (unsigned long)status.completedWindows, (unsigned long)status.rejectedWindows,
    (unsigned long)status.i2cErrors, (unsigned long)status.lateSamples,
    (unsigned long)status.queueDrops, (unsigned long)status.maxJitterUs,
    (unsigned long)age, (unsigned long)ESP.getFreeHeap());
  sendPacket(packet);
}

void publishPrediction(const Prediction &prediction) {
  char packet[900];
  if (prediction.error != EI_IMPULSE_OK) {
    snprintf(packet, sizeof(packet),
      "{\"type\":\"error\",\"version\":1,\"boot_id\":\"%s\",\"seq\":%lu,"
      "\"code\":%d,\"message\":\"Fallo durante la inferencia\"}",
      bootID, (unsigned long)prediction.seq, prediction.error);
    sendPacket(packet);
    Serial.printf("ERROR de inferencia: %d\n", prediction.error);
    return;
  }
  size_t best = 0;
  for (size_t i = 1; i < EI_CLASSIFIER_LABEL_COUNT; ++i) {
    if (prediction.scores[i] > prediction.scores[best]) best = i;
  }
  const float confidence = prediction.scores[best];
  const char *label = confidence >= THRESHOLD ? ei_classifier_inferencing_categories[best] : "incierto";
  const uint32_t lagMs = millis() - prediction.endMs;
  const int length = snprintf(packet, sizeof(packet),
    "{\"type\":\"prediction\",\"version\":1,\"boot_id\":\"%s\",\"kit\":%u,"
    "\"seq\":%lu,\"t_start_ms\":%lu,\"t_end_ms\":%lu,\"label\":\"%s\","
    "\"confidence\":%.6f,\"threshold\":%.4f,"
    "\"probabilities\":{\"%s\":%.6f,\"%s\":%.6f,\"%s\":%.6f},"
    "\"dsp_ms\":%.3f,\"inference_ms\":%.3f,\"total_ms\":%.3f,"
    "\"lag_ms\":%lu,\"max_jitter_us\":%lu}",
    bootID, unsigned(KIT_ID), (unsigned long)prediction.seq,
    (unsigned long)prediction.startMs, (unsigned long)prediction.endMs, label,
    double(confidence), double(THRESHOLD),
    ei_classifier_inferencing_categories[0], double(prediction.scores[0]),
    ei_classifier_inferencing_categories[1], double(prediction.scores[1]),
    ei_classifier_inferencing_categories[2], double(prediction.scores[2]),
    double(prediction.dspMs), double(prediction.inferenceMs), double(prediction.totalMs),
    (unsigned long)lagMs, (unsigned long)prediction.maxJitterUs);
  if (length > 0 && size_t(length) < sizeof(packet)) sendPacket(packet);
  if (SERIAL_RESULTS) {
    Serial.printf("Ventana %lu | %s | %.1f %% | DSP %.3f ms | NN %.3f ms | total %.3f ms\n",
      (unsigned long)prediction.seq, label, double(confidence * 100.0f),
      double(prediction.dspMs), double(prediction.inferenceMs), double(prediction.totalMs));
  }
}

void initWiFi() {
  snprintf(ssid, sizeof(ssid), "TinyWear-%u", unsigned(KIT_ID));
  const uint8_t channels[3] = {1, 6, 11};
  const uint8_t channel = channels[(KIT_ID - 1) % 3];
  WiFi.mode(WIFI_OFF);
  delay(250);
  WiFi.mode(WIFI_AP);
  delay(150);
  WiFi.setSleep(false);
  if (!WiFi.softAPConfig(IPAddress(192,168,4,1), IPAddress(192,168,4,1), IPAddress(255,255,255,0)))
    fatal("ERROR: no se pudo asignar la IP 192.168.4.1.");
  if (!WiFi.softAP(ssid, WIFI_PASSWORD, channel, 0, 4)) fatal("ERROR al crear la red Wi-Fi.");
  delay(300);
  const esp_err_t protocol = esp_wifi_set_protocol(WIFI_IF_AP, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
  const esp_err_t bandwidth = esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT20);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  if (protocol != ESP_OK || bandwidth != ESP_OK) Serial.println("Aviso: revisar configuracion de radio.");
  if (!udp.begin(UDP_PORT)) fatal("ERROR al iniciar UDP.");
  snprintf(bootID, sizeof(bootID), "%08lx", (unsigned long)esp_random());
  Serial.printf("SSID: %s | Clave: %s | IP: %s | UDP: %u | Canal: %u\n",
    ssid, WIFI_PASSWORD, WiFi.softAPIP().toString().c_str(), UDP_PORT, channel);
}
} // namespace

void tinywearBegin() {
  Serial.begin(115200);
  delay(600);                                 // No espera indefinidamente la apertura del puerto USB.
  Serial.println("\nTinyWear: inferencia ESP32-S3 + MPU6050 / Wi-Fi");
  if (strcmp(EI_CLASSIFIER_FUSION_AXES_STRING, "ax + ay + az + gx + gy + gz") != 0)
    fatal("ERROR: el orden de ejes del modelo no coincide.");
  const char *expected[] = {"caminar", "reposo", "sentarse_levantarse"};
  for (size_t i = 0; i < 3; ++i) {
    if (strcmp(ei_classifier_inferencing_categories[i], expected[i]) != 0)
      fatal("ERROR: las clases de la biblioteca no coinciden con este paquete.");
  }
  Wire.setPins(SDA_PIN, SCL_PIN);
  Wire.begin();
  Wire.setClock(400000);
  Wire.setTimeOut(10);                         // Un error I2C no debe bloquear varias lecturas.
  if (!initMPU6050()) fatal("ERROR: revisar MPU6050, VCC, GND, SDA/SCL y direccion 0x68/0x69.");
  Serial.printf("MPU6050 0x%02x | +/-4 g | +/-500 grados/s | 50 Hz\n", mpuAddress);
  initWiFi();
  windowQueue = xQueueCreate(1, sizeof(InputWindow));
  predictionQueue = xQueueCreate(4, sizeof(Prediction));
  if (!windowQueue || !predictionQueue) fatal("ERROR: memoria insuficiente para las colas.");
  if (xTaskCreatePinnedToCore(acquisitionTask, "TinyWear_IMU", 4096, nullptr, 3, nullptr, 1) != pdPASS)
    fatal("ERROR: no se pudo crear la tarea de adquisicion.");
  if (xTaskCreatePinnedToCore(inferenceTask, "TinyWear_INT8", 24576, nullptr, 1, nullptr, 0) != pdPASS)
    fatal("ERROR: no se pudo crear la tarea de inferencia.");
  Serial.printf("Modelo INT8 | 600 entradas | 78 features | Standard Scaler incluido | umbral %.2f\n", double(THRESHOLD));
  Serial.println("La inferencia continua aunque no exista un cliente Wi-Fi.");
}

void tinywearUpdate() {
  checkClient();
  if (clientRegistered && uint32_t(millis() - lastHelloMs) > CLIENT_TIMEOUT_MS) {
    clientRegistered = false;
    Serial.println("Cliente Wi-Fi desconectado. La inferencia local continua.");
  }
  Prediction prediction;
  while (xQueueReceive(predictionQueue, &prediction, 0) == pdTRUE) publishPrediction(prediction);
  if (clientRegistered && uint32_t(millis() - lastStatusMs) >= STATUS_INTERVAL_MS) {
    lastStatusMs = millis();
    sendStatus();
  }
  delay(1);                                  // Mantiene disponibles las tareas y la pila de red.
}
