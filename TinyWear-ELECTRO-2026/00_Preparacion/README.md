# Preparación del equipo

Se configura la computadora antes de las prácticas presenciales. La conexión física y la selección del puerto COM se completan cuando se disponga del kit.

## Guía de instalación

Se utiliza la [guía editable en Word](Guia_Instalacion_Programas_ELECTRO_2026.docx), que incluye descargas oficiales, comandos y comprobaciones para Windows de 64 bits.

| Programa o recurso | Uso en el taller |
|---|---|
| Arduino IDE 2.x y soporte ESP32 2.0.17 | Compilar y cargar los programas. |
| Python 3.13.x, o una instalación 3.10 o posterior que pase las comprobaciones | Ejecutar las herramientas de adquisición e inferencia. |
| Tkinter | Interfaz gráfica. |
| Matplotlib | Gráficas del capturador del dataset. |
| Edge Impulse | Entrenamiento, evaluación y exportación del modelo en P3. |
| Google Colab | Recurso complementario. |
| Excel o LibreOffice Calc | Revisión de archivos CSV. |

La versión 2.0.17 se refiere al soporte de la placa ESP32, con el que se verificó el programa de inferencia del taller. Los programas se incorporan posteriormente a sus carpetas.

## Comprobación

Se abre Símbolo del sistema y se ejecutan los comandos uno por uno:

```bat
py -3 --version
py -3 -m tkinter
py -3 -m pip install matplotlib
py -3 -c "import matplotlib; print(matplotlib.__version__)"
```

La comprobación de Tkinter debe abrir una ventana, que se cierra antes de continuar. La última instrucción debe mostrar la versión de Matplotlib.

En Arduino IDE se selecciona **ESP32S3 Dev Module**, se habilita **USB CDC On Boot** y se verifica el ejemplo **BareMinimum**.

**Resultado esperado:** entorno instalado y comprobado. Se regresa al [inicio del repositorio](../README.md).
