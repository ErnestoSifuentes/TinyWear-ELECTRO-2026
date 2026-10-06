# TinyWear ELECTRO 2026

Material del curso-taller **Diseño de sistemas TinyML para instrumentación electrónica inteligente**, impartido por **Dr. Ernesto Sifuentes de la Hoya**, Universidad Autónoma de Ciudad Juárez.

TinyWear integra un ESP32-S3 y un MPU6050 para reconocer tres actividades: **reposo/de pie, caminar y sentarse-levantarse**. La inferencia se ejecuta en el microcontrolador; las predicciones se reciben y visualizan en la computadora mediante Wi-Fi y UDP.

**Estado del material:** estructura inicial preparada. La guía de instalación está incluida; los códigos, las presentaciones y los ejemplos de datos se incorporan al completar el repositorio.

## Inicio

1. Se revisa la [preparación del equipo](00_Preparacion/README.md) y se instala el software indicado.
2. Se consultan las [conexiones del kit](Recursos/Conexiones.md).
3. Cuando se agregue la interfaz animada, se ejecuta su demostración con datos simulados para conocer el resultado esperado del taller.
4. Se desarrollan las prácticas P1, P2 y P3 en ese orden.

## Organización

| Carpeta | Propósito | Producto esperado |
|---|---|---|
| [00_Preparacion](00_Preparacion/README.md) | Instalación y comprobación del entorno. | Computadora preparada. |
| [P1_Adquisicion](P1_Adquisicion/README.md) | Conexión, lectura del sensor y comunicación. | Señales visibles y comunicación comprobada. |
| [P2_Dataset](P2_Dataset/README.md) | Captura, etiquetado y revisión de datos. | Archivos CSV organizados y verificados. |
| [P3_Modelo_Inferencia](P3_Modelo_Inferencia/README.md) | Entrenamiento, evaluación, exportación e inferencia. | Modelo embebido y registro de validación. |
| [Documentos](Documentos/README.md) | Guías y presentaciones del curso. | Material de consulta por práctica. |
| [Recursos](Recursos/README.md) | Conexiones, figuras y apoyos. | Referencias del montaje y del flujo TinyML. |

**P1, P2 y P3 identifican prácticas, no días del programa. P2 termina con el dataset revisado y listo; la carga a Edge Impulse y el trabajo con el modelo corresponden a P3.**

## Equipo y programas

- Computadora con Windows 10 u 11 de 64 bits para seguir la guía incluida.
- ESP32-S3, MPU6050 y cable USB de datos.
- Arduino IDE y soporte ESP32 de Espressif Systems.
- Python, Tkinter y Matplotlib para las herramientas del taller.
- Cuenta de Edge Impulse; Google Colab como recurso complementario.
- Excel o LibreOffice Calc para revisar los CSV y la hoja de control.

Las versiones y los pasos de instalación se detallan en [00_Preparacion](00_Preparacion/README.md).

## Descargas y versiones

Se conserva una versión vigente de cada programa y se describen las modificaciones en [CHANGELOG.md](CHANGELOG.md). Cuando se integren y comprueben los programas, se podrá publicar una Release con un ZIP completo del taller. La versión inicial de este esqueleto es **0.1.0**.

## Consultas y aportaciones

Las consultas se registran en la pestaña **Issues**, indicando la práctica, el programa y el mensaje de error cuando corresponda. Para proponer mejoras se siguen las [instrucciones de contribución](CONTRIBUTING.md).

## Autoría y licencias

**Autor y coordinador:** Ernesto Sifuentes de la Hoya. Véanse los [créditos](CREDITOS.md) y el archivo [CITATION.cff](CITATION.cff) para citar el material.

- Código original y archivos de configuración: [MIT](LICENSE).
- Material didáctico original: [Creative Commons Atribución 4.0 Internacional](LICENSES/CC-BY-4.0.txt).
- Componentes de terceros: sus licencias y avisos originales.

El alcance se explica en [LICENCIAS.md](LICENCIAS.md). Para completar y subir el material se utiliza la [guía del responsable del repositorio](GUIA_PARA_COMPLETAR_REPOSITORIO.md).
