/*
  P1A_Diagnostico_I2C_MPU6050_ESP32S3.ino
  TinyWear - ELECTRO 2026

  Objetivos:
  1) Verificar el cableado I2C.
  2) Detectar el MPU6050 en 0x68 o 0x69.
  3) Confirmar WHO_AM_I = 0x68.
  4) Configurar:
       acelerometro +/-4 g
       giroscopio  +/-500 deg/s
  5) Mostrar lecturas de diagnostico a 10 Hz.

  Conexion:
    MPU6050 VCC -> 3.3 V
    MPU6050 GND -> GND
    MPU6050 SDA -> GPIO 8
    MPU6050 SCL -> GPIO 9
    
  Autor: Ernesto Sifuentes de la Hoya
*/

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#define SDA_PIN 8
#define SCL_PIN 9

uint8_t mpuAddress = 0x68;

constexpr float ACCEL_SCALE = 8192.0f;  // +/-4 g
constexpr float GYRO_SCALE  = 65.5f;    // +/-500 deg/s

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(mpuAddress, (uint8_t)1) != 1) {
    return false;
  }

  value = Wire.read();
  return true;
}

bool findMPU6050() {
  Serial.println("Escaneo I2C:");

  bool foundAny = false;
  bool foundMPU = false;

  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();

    if (error == 0) {
      foundAny = true;

      Serial.print("  Dispositivo encontrado en 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);

      if (address == 0x68 || address == 0x69) {
        mpuAddress = address;
        foundMPU = true;
      }
    }
  }

  if (!foundAny) {
    Serial.println("  No se encontraron dispositivos I2C.");
  }

  return foundMPU;
}

bool initMPU6050() {
  uint8_t who = 0;

  if (!readRegister(0x75, who)) {
    return false;
  }

  Serial.print("WHO_AM_I = 0x");
  if (who < 16) Serial.print("0");
  Serial.println(who, HEX);

  if (who != 0x68) {
    return false;
  }

  // Despertar
  if (!writeRegister(0x6B, 0x00)) return false;
  delay(100);

  // DLPF
  if (!writeRegister(0x1A, 0x03)) return false;

  // Divisor interno: 1 kHz / (1 + 19) = 50 Hz
  if (!writeRegister(0x19, 19)) return false;

  // Gyro +/-500 deg/s
  if (!writeRegister(0x1B, 0x08)) return false;

  // Accel +/-4 g
  if (!writeRegister(0x1C, 0x08)) return false;

  return true;
}

bool readMPU(
  float &ax, float &ay, float &az,
  float &gx, float &gy, float &gz
) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(0x3B);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(mpuAddress, (uint8_t)14) != 14) {
    return false;
  }

  auto read16 = []() -> int16_t {
    return (int16_t)((Wire.read() << 8) | Wire.read());
  };

  int16_t axRaw = read16();
  int16_t ayRaw = read16();
  int16_t azRaw = read16();

  (void)read16();  // temperatura

  int16_t gxRaw = read16();
  int16_t gyRaw = read16();
  int16_t gzRaw = read16();

  ax = axRaw / ACCEL_SCALE;
  ay = ayRaw / ACCEL_SCALE;
  az = azRaw / ACCEL_SCALE;

  gx = gxRaw / GYRO_SCALE;
  gy = gyRaw / GYRO_SCALE;
  gz = gzRaw / GYRO_SCALE;

  return true;
}

void setup() {
  Serial.begin(115200);
  delay(700);

  Serial.println();
  Serial.println("========================================");
  Serial.println("P1A - Diagnostico ESP32-S3 + MPU6050");
  Serial.println("========================================");
  Serial.printf("SDA = GPIO %d\n", SDA_PIN);
  Serial.printf("SCL = GPIO %d\n", SCL_PIN);
  Serial.println();

  Wire.setPins(SDA_PIN, SCL_PIN);
  Wire.begin();
  Wire.setClock(400000);

  if (!findMPU6050()) {
    Serial.println();
    Serial.println("ERROR: no se encontro MPU6050 en 0x68/0x69.");
    Serial.println("Revise VCC, GND, SDA y SCL.");
    while (true) delay(1000);
  }

  Serial.println();
  Serial.print("Direccion seleccionada: 0x");
  Serial.println(mpuAddress, HEX);

  if (!initMPU6050()) {
    Serial.println("ERROR: WHO_AM_I/configuracion incorrecta.");
    while (true) delay(1000);
  }

  Serial.println("[OK] MPU6050 identificado.");
  Serial.println("[OK] Acelerometro: +/-4 g");
  Serial.println("[OK] Giroscopio: +/-500 deg/s");
  Serial.println("[OK] Muestreo interno: 50 Hz");
  Serial.println();
  Serial.println("Lecturas de diagnostico a 10 Hz:");
  Serial.println("ax[g]\tay[g]\taz[g]\tgx[deg/s]\tgy[deg/s]\tgz[deg/s]\t|a|[g]");
}

void loop() {
  static uint32_t lastMs = 0;

  if (millis() - lastMs < 100) {
    delay(1);
    return;
  }

  lastMs += 100;

  float ax, ay, az;
  float gx, gy, gz;

  if (!readMPU(ax, ay, az, gx, gy, gz)) {
    Serial.println("ERROR de lectura I2C");
    return;
  }

  float amag = sqrtf(
    ax * ax +
    ay * ay +
    az * az
  );

 /*Serial.printf(
    "%.3f\t%.3f\t%.3f\t%.2f\t%.2f\t%.2f\t%.3f\n",
    ax, ay, az,
    gx, gy, gz,
    amag
  );*/
}
