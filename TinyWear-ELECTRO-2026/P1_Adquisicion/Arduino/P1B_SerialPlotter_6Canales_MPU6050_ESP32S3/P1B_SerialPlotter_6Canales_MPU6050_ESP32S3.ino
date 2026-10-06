/*
  P1B_SerialPlotter_6Canales_MPU6050_ESP32S3.ino
  TinyWear - ELECTRO 2026

  Objetivo:
  adquirir y visualizar en Arduino Serial Plotter las seis
  señales de la IMU:

    ax, ay, az  [g]
    gx, gy, gz  [deg/s]

  Frecuencia:
    50 Hz

   Autor: Ernesto Sifuentes de la Hoya
*/

#include <Arduino.h>
#include <Wire.h>

#define SDA_PIN 8
#define SCL_PIN 9

uint8_t mpuAddress = 0x68;

constexpr uint32_t FS_HZ = 50;
constexpr uint32_t SAMPLE_PERIOD_US = 1000000UL / FS_HZ;

constexpr float ACCEL_SCALE = 8192.0f;  // +/-4 g
constexpr float GYRO_SCALE  = 65.5f;    // +/-500 deg/s

uint32_t lastSampleUs = 0;

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
  for (uint8_t address : { (uint8_t)0x68, (uint8_t)0x69 }) {
    Wire.beginTransmission(address);

    if (Wire.endTransmission() == 0) {
      mpuAddress = address;
      return true;
    }
  }

  return false;
}

bool initMPU6050() {
  uint8_t who = 0;

  if (!readRegister(0x75, who)) {
    return false;
  }

  if (who != 0x68) {
    return false;
  }

  if (!writeRegister(0x6B, 0x00)) return false;
  delay(100);

  if (!writeRegister(0x1A, 0x03)) return false;
  if (!writeRegister(0x19, 19))   return false;
  if (!writeRegister(0x1B, 0x08)) return false;
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

  Wire.setPins(SDA_PIN, SCL_PIN);
  Wire.begin();
  Wire.setClock(400000);

  if (!findMPU6050()) {
    Serial.println("ERROR: MPU6050 no detectado en 0x68/0x69.");
    while (true) delay(1000);
  }

  if (!initMPU6050()) {
    Serial.println("ERROR: no fue posible inicializar el MPU6050.");
    while (true) delay(1000);
  }

  // Dar tiempo para abrir el Serial Plotter.
  delay(500);

  lastSampleUs = micros();
}

void loop() {
  uint32_t nowUs = micros();

  if ((uint32_t)(nowUs - lastSampleUs) < SAMPLE_PERIOD_US) {
    delay(1);
    return;
  }

  lastSampleUs += SAMPLE_PERIOD_US;

  float ax, ay, az;
  float gx, gy, gz;

  if (!readMPU(ax, ay, az, gx, gy, gz)) {
    return;
  }

  /*
    Formato compatible con Arduino Serial Plotter.
    Cada etiqueta genera una serie independiente.
  */
  Serial.print("ax:");
  Serial.print(ax, 3);

  Serial.print("\tay:");
  Serial.print(ay, 3);

  Serial.print("\taz:");
  Serial.print(az, 3);

  Serial.print("\tgx:");
  Serial.print(gx, 2);

  Serial.print("\tgy:");
  Serial.print(gy, 2);

  Serial.print("\tgz:");
  Serial.println(gz, 2);
}
