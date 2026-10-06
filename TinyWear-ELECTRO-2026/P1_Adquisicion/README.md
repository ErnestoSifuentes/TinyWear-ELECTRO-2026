# P1 Adquisición y comunicación

Se conecta el MPU6050 al ESP32-S3, se observan las señales y se comprueba su recepción en la computadora. Se utiliza el mismo montaje que se conservará durante la captura del dataset y la validación.

| Carpeta | Archivos por incorporar |
|---|---|
| [Arduino](Arduino/README.md) | Sketches de lectura, visualización y envío Wi-Fi del taller. |
| [Python](Python/README.md) | Herramientas de recepción o prueba de comunicación UDP. |

## Procedimiento general

1. Se revisan las [conexiones del kit](../Recursos/Conexiones.md).
2. Se abre y carga el sketch correspondiente al equipo asignado.
3. Se comprueban las señales con el Monitor Serial o la herramienta indicada en la guía de P1.
4. Se verifica la comunicación Wi-Fi y la recepción UDP.
5. Se registra el identificador del kit y la orientación del sensor.

**Producto:** lectura estable y comunicación comprobada. Se continúa con [P2 Dataset](../P2_Dataset/README.md).
