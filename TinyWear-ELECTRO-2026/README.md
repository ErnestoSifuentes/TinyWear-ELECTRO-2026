# TinyWear ELECTRO 2026

Material del curso-taller **Diseño de sistemas TinyML para instrumentación electrónica inteligente**, impartido por **Dr. Ernesto Sifuentes de la Hoya**, Universidad Autónoma de Ciudad Juárez.

TinyWear utiliza un ESP32-S3 y un MPU6050 para reconocer **reposo/de pie, caminar y sentarse-levantarse**. Las predicciones se reciben y visualizan en la computadora mediante Wi-Fi y UDP.

El material disponible incluye programas Arduino y Python, ejemplos CSV, una biblioteca exportada de Edge Impulse, guías y presentaciones en PDF.

## Acceso y descarga

1. Se descarga el material mediante **Code → Download ZIP** o el [ZIP del repositorio](https://github.com/ErnestoSifuentes/TinyWear-ELECTRO-2026/archive/refs/heads/main.zip).
2. Se extrae el ZIP y se abre la carpeta `TinyWear-ELECTRO-2026` que contiene las prácticas.
3. Se consulta la [guía de instalación en Word](00_Preparacion/Guia_Instalacion_Programas_ELECTRO_2026.docx) y la [preparación del equipo](00_Preparacion/README.md).
4. Se revisan las [conexiones del kit](Recursos/Conexiones.md) y se realizan las prácticas en orden.

## Prácticas

| Práctica | Material | Guía PDF |
|---|---|---|
| P1 Adquisición y comunicación | [Programas e instrucciones](P1_Adquisicion/README.md) | [P1 Adquisición y visualización](Documentos/Guias/P1_Adquisicion_Visualizacion.pdf) |
| P2 Dataset | [Capturador, CSV y registro](P2_Dataset/README.md) | [P2 Dataset](Documentos/Guias/P2_Dataset.pdf) |
| P3 Modelo e inferencia | [Sketch, interfaz y biblioteca](P3_Modelo_Inferencia/README.md) | [P3 Entrenamiento e inferencia](Documentos/Guias/P3_Entrenamiento_Inferencia.pdf) |

**P1, P2 y P3 identifican prácticas, no días. P2 termina con el dataset verificado; la carga a Edge Impulse, el entrenamiento y la inferencia corresponden a P3.**

## Material de consulta

- [Presentaciones del taller](Documentos/Presentaciones/README.md).
- [Guías del taller](Documentos/Guias/README.md).
- [Recursos y conexiones](Recursos/README.md).
- [Historial de cambios](CHANGELOG.md).

## Equipo y programas

Se utilizan ESP32-S3, MPU6050, cable USB de datos, Arduino IDE, soporte ESP32, Python, Tkinter, Matplotlib y una cuenta de Edge Impulse. Los CSV pueden revisarse con Excel o LibreOffice Calc. Las instalaciones se detallan en [00_Preparacion](00_Preparacion/README.md).

## Autoría y licencias

**Autor y coordinador:** Ernesto Sifuentes de la Hoya. Se consultan los [créditos](CREDITOS.md) y el [archivo de citación](CITATION.cff).

- Código y configuración originales: [MIT](LICENSE).
- Material didáctico original: [CC BY 4.0](LICENSES/CC-BY-4.0.txt).
- Componentes externos: sus avisos originales, según [TERCEROS](TERCEROS.md).

El alcance se explica en [LICENCIAS](LICENCIAS.md). Las mejoras se proponen siguiendo [CONTRIBUTING](CONTRIBUTING.md). El instructor dispone de la [guía de mantenimiento](GUIA_PARA_COMPLETAR_REPOSITORIO.md).
