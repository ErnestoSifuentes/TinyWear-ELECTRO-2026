# P3 Modelo e inferencia embebida

Se carga el dataset verificado en Edge Impulse, se configura el impulso, se entrena y evalúa el modelo y se exporta la biblioteca Arduino. Después se integra la inferencia en el ESP32-S3 y se validan las predicciones mediante las interfaces Python.

| Carpeta | Contenido por incorporar |
|---|---|
| [Arduino](Arduino/README.md) | Sketch de inferencia con sus archivos `.cpp` y `.h`. |
| [Python](Python/README.md) | Interfaces UDP, registro de pruebas y versión animada. |
| [Modelo](Modelo/README.md) | Configuración, métricas y referencia de la biblioteca exportada. |

## Procedimiento general

1. Se carga el dataset y se verifican las etiquetas y la separación de entrenamiento y prueba.
2. Se documentan la ventana, el procesamiento y la configuración del modelo.
3. Se comparan los resultados de entrenamiento y Model Testing.
4. Se exporta e instala la biblioteca Arduino completa del modelo.
5. Se carga el sketch de inferencia en el ESP32-S3.
6. Se reciben las predicciones en Python mediante Wi-Fi y UDP.
7. Se realizan pruebas físicas y se registran la clase real, la predicción, la confianza y los errores.

La frecuencia de muestreo, las unidades, el orden de los canales y la normalización deben corresponder a los utilizados para preparar el modelo. Se documenta qué etapa aplica cada transformación.

**Producto:** inferencia local y registro de validación experimental. Se regresa al [inicio](../README.md).
