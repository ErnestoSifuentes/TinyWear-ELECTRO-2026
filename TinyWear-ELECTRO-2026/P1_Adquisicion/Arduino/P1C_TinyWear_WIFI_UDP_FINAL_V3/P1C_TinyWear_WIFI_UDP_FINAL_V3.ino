/*
  TinyWear Wi-Fi / UDP UNICAST V2
  ESP32-S3 + MPU6050
  Taller ELECTRO 2026

  Flujo:
    MPU6050 -> ESP32-S3 -> Wi-Fi UDP unicast -> Python -> CSV

  Red:
    SSID: TinyWear-1
    Password: TinyWear2026
    ESP32: 192.168.4.1
    Puerto UDP: 5005

  Formato:
    seq,t_ms,ax,ay,az,gx,gy,gz
  
Autor: Ernesto Sifuentes de la Hoya
*/

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#define KIT_ID 1

#define SDA_PIN 8
#define SCL_PIN 9
#define MPU_ADDR 0x68

const char* WIFI_PASSWORD = "TinyWear2026";

constexpr uint16_t UDP_PORT = 5005;
constexpr uint32_t FS_HZ = 50;
constexpr uint32_t SAMPLE_PERIOD_US = 1000000UL / FS_HZ;

constexpr float ACCEL_SCALE = 8192.0f; // +/-4 g
constexpr float GYRO_SCALE  = 65.5f;   // +/-500 dps

String ssid;
WiFiUDP udp;

IPAddress clientIP;
uint16_t clientPort = 0;

bool clientRegistered = false;

uint32_t seq = 0;
uint32_t lastSampleUs = 0;
uint32_t lastStatusMs = 0;
uint32_t lastClientHelloMs = 0;


// ------------------------------------------------------------
// MPU6050
// ------------------------------------------------------------

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);

  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU_ADDR, (uint8_t)1) != 1) {
    return false;
  }

  value = Wire.read();

  return true;
}

bool initMPU6050() {
  uint8_t who = 0;

  if (!readRegister(0x75, who)) {
    return false;
  }

  if (who != 0x68) {
    Serial.printf(
      "WHO_AM_I inesperado: 0x%02X\n",
      who
    );

    return false;
  }

  if (!writeRegister(0x6B, 0x00)) return false; // Wake up
  delay(100);

  if (!writeRegister(0x1A, 0x03)) return false; // DLPF
  if (!writeRegister(0x19, 19))   return false; // 50 Hz
  if (!writeRegister(0x1B, 0x08)) return false; // +/-500 dps
  if (!writeRegister(0x1C, 0x08)) return false; // +/-4 g

  return true;
}

bool readMPU6050(
  int16_t &ax,
  int16_t &ay,
  int16_t &az,
  int16_t &gx,
  int16_t &gy,
  int16_t &gz
) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU_ADDR, (uint8_t)14) != 14) {
    return false;
  }

  auto read16 = []() -> int16_t {
    return (int16_t)(
      (Wire.read() << 8)
      |
      Wire.read()
    );
  };

  ax = read16();
  ay = read16();
  az = read16();

  (void)read16(); // Temperatura

  gx = read16();
  gy = read16();
  gz = read16();

  return true;
}


// ------------------------------------------------------------
// UDP: registro del cliente
// ------------------------------------------------------------

void checkForClient() {
  int packetSize = udp.parsePacket();

  if (packetSize <= 0) {
    return;
  }

  char buffer[64];

  int len = udp.read(
    buffer,
    sizeof(buffer) - 1
  );

  if (len <= 0) {
    return;
  }

  buffer[len] = '\0';

  if (
    strcmp(buffer, "TINYWEAR_HELLO") == 0
    ||
    strcmp(buffer, "TINYWEAR_KEEPALIVE") == 0
  ) {
    clientIP = udp.remoteIP();
    clientPort = udp.remotePort();

    bool firstRegistration = !clientRegistered;

    clientRegistered = true;
    lastClientHelloMs = millis();

    if (firstRegistration) {
      Serial.println();
      Serial.println("Cliente Python registrado.");

      Serial.print("IP cliente: ");
      Serial.println(clientIP);

      Serial.print("Puerto cliente: ");
      Serial.println(clientPort);

      seq = 0;
    }

    // Respuesta de confirmacion
    udp.beginPacket(
      clientIP,
      clientPort
    );

    udp.print(
      "TINYWEAR_ACK"
    );

    udp.endPacket();
  }
}


// ------------------------------------------------------------
// Wi-Fi
// ------------------------------------------------------------

void initWiFi() {
  ssid =
    "TinyWear-"
    +
    String(KIT_ID);

  WiFi.mode(WIFI_AP);

  if (!WiFi.softAP(
        ssid.c_str(),
        WIFI_PASSWORD
      )) {
    Serial.println(
      "ERROR: no fue posible crear la red Wi-Fi."
    );

    while (true) {
      delay(1000);
    }
  }

  // El ESP32 escucha los HELLO del cliente Python.
  udp.begin(UDP_PORT);

  Serial.println();
  Serial.println("Wi-Fi listo.");

  Serial.print("SSID: ");
  Serial.println(ssid);

  Serial.print("Password: ");
  Serial.println(WIFI_PASSWORD);

  Serial.print("IP ESP32-S3: ");
  Serial.println(WiFi.softAPIP());

  Serial.print("Puerto UDP: ");
  Serial.println(UDP_PORT);

  Serial.println(
    "Esperando registro del capturador Python..."
  );
}


// ------------------------------------------------------------
// SETUP
// ------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(600);

  Serial.println();
  Serial.println(
    "=== TINYWEAR UDP UNICAST V2 ==="
  );

  Wire.setPins(
    SDA_PIN,
    SCL_PIN
  );

  Wire.begin();
  Wire.setClock(400000);

  if (!initMPU6050()) {
    Serial.println(
      "ERROR: MPU6050 no detectado."
    );

    Serial.println(
      "Revise VCC, GND, SDA, SCL y direccion 0x68."
    );

    while (true) {
      delay(1000);
    }
  }

  Serial.println(
    "MPU6050 OK | +/-4 g | +/-500 dps | 50 Hz"
  );

  initWiFi();

  lastSampleUs = micros();
}


// ------------------------------------------------------------
// LOOP
// ------------------------------------------------------------

void loop() {
  // Atiende paquetes HELLO / KEEPALIVE
  checkForClient();

  // Si el cliente desaparece por mas de 6 s,
  // se detiene la transmision hasta un nuevo HELLO.
  if (
    clientRegistered
    &&
    (millis() - lastClientHelloMs > 6000)
  ) {
    clientRegistered = false;

    Serial.println(
      "Cliente Python perdido. Esperando nuevo registro..."
    );
  }

  const uint32_t nowUs = micros();

  if (
    (uint32_t)(
      nowUs - lastSampleUs
    )
    <
    SAMPLE_PERIOD_US
  ) {
    delay(1);
    return;
  }

  lastSampleUs += SAMPLE_PERIOD_US;

  // Sin cliente no enviamos paquetes.
  if (!clientRegistered) {
    return;
  }

  int16_t axRaw, ayRaw, azRaw;
  int16_t gxRaw, gyRaw, gzRaw;

  if (!readMPU6050(
        axRaw,
        ayRaw,
        azRaw,
        gxRaw,
        gyRaw,
        gzRaw
      )) {
    return;
  }

  float ax =
      axRaw / ACCEL_SCALE;

  float ay =
      ayRaw / ACCEL_SCALE;

  float az =
      azRaw / ACCEL_SCALE;

  float gx =
      gxRaw / GYRO_SCALE;

  float gy =
      gyRaw / GYRO_SCALE;

  float gz =
      gzRaw / GYRO_SCALE;


  char packet[190];

  snprintf(
    packet,
    sizeof(packet),
    "%lu,%lu,%.6f,%.6f,%.6f,%.4f,%.4f,%.4f",
    (unsigned long)seq++,
    (unsigned long)millis(),
    ax, ay, az,
    gx, gy, gz
  );


  // UDP UNICAST directamente a la laptop.
  udp.beginPacket(
    clientIP,
    clientPort
  );

  udp.write(
    (const uint8_t*)packet,
    strlen(packet)
  );

  udp.endPacket();


  if (
    millis() - lastStatusMs
    >=
    3000
  ) {
    lastStatusMs = millis();

    Serial.print(
      "Cliente: "
    );

    Serial.print(
      clientIP
    );

    Serial.print(
      " | Paquetes enviados: "
    );

    Serial.println(
      seq
    );
  }
}
