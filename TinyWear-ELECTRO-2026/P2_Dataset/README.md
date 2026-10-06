# P2 Construcción y verificación del dataset

Se capturan y etiquetan las señales de reposo/de pie, caminar y sentarse-levantarse. Se revisan los archivos y se organizan para utilizarlos posteriormente en Edge Impulse.

| Carpeta | Contenido por incorporar |
|---|---|
| [Python](Python/README.md) | Capturador del dataset y sus módulos. |
| [EjemplosCSV](EjemplosCSV/README.md) | Archivos de ejemplo revisados. |
| [Plantillas](Plantillas/README.md) | Hoja de control de capturas. |

## Procedimiento general

1. Se comprueba la comunicación con el kit y se conserva el montaje de P1.
2. Se realizan capturas por actividad y se registran las condiciones de adquisición.
3. Se revisan los encabezados, la cantidad de muestras, las etiquetas y las unidades.
4. Se identifican capturas incompletas o dudosas y se repiten cuando corresponda.
5. Se organizan los CSV y se completa la hoja de control.

Se documentan la frecuencia de muestreo y el tratamiento de los datos, incluida cualquier normalización aplicada. Las etiquetas deben conservarse al pasar a P3.

**Producto:** dataset verificado y archivos listos para cargar en Edge Impulse. El entrenamiento se realiza en [P3](../P3_Modelo_Inferencia/README.md).
