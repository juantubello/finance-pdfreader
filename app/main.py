import re
import json
from datetime import datetime
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import io
import os

# DEBUG remoto si está activo
if os.getenv("DEBUG_MODE") == "1":
    import debugpy
    debugpy.listen(("0.0.0.0", 5680))
    print("🛠 Esperando conexión de debugger...")

app = FastAPI()

# Diccionario de meses en español
meses = {
    'Ene': '01', 'Feb': '02', 'Mar': '03', 'Abr': '04', 'May': '05', 'Jun': '06',
    'Jul': '07', 'Ago': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dic': '12'
}

def convertir_fecha(fecha_str):
    try:
        dia, mes_abreviado, anio_corto = fecha_str.split('-')
        mes = meses.get(mes_abreviado.capitalize(), '01')
        anio = int(anio_corto)
        anio_completo = 2000 + anio if anio < 100 else anio
        fecha_iso = f"{anio_completo:04d}-{mes}-{dia}"
        fecha_obj = datetime.strptime(fecha_iso, "%Y-%m-%d")
        return fecha_str, fecha_obj.isoformat()
    except Exception:
        return fecha_str, None

def extraer_consumos_con_total(texto, nombre_seccion, total_match_string):
    detalles = []
    patron_linea = re.compile(r"^(\d{2}-[A-Za-z]{3}-\d{2})\s+(.*?)(\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
    dentro_de_seccion = False
    total_pesos = ''
    total_dolares = ''

    for linea in texto.splitlines():
        if nombre_seccion in linea:
            dentro_de_seccion = True
            continue
        if total_match_string in linea:
            dentro_de_seccion = False
            partes = linea.split()
            if len(partes) >= 3:
                total_dolares = partes[-1]
                total_pesos = partes[-2]
            continue
        if dentro_de_seccion:
            match = patron_linea.match(linea)
            if match:
                fecha_raw = match.group(1)
                descripcion = match.group(2).strip()
                importe = match.group(3).strip()
                _, fecha_timestamp = convertir_fecha(fecha_raw)
                detalles.append({
                    "fecha": fecha_raw,
                    "fechaTimestamp": fecha_timestamp,
                    "descripcion": descripcion,
                    "importe": importe
                })

    return detalles, {"pesos": total_pesos, "dolares": total_dolares}

def extraer_impuestos(texto):
    detalles = []
    patron_linea = re.compile(
        r"^(\d{2}-[A-Za-z]{3}-\d{2})\s+(.*?)(\d{1,3}(?:\.\d{3})*,\d{2})(?:\s+(\d{1,3}(?:\.\d{3})*,\d{2}))?$"
    )
    dentro_de_seccion = False
    total_pesos = ''
    total_dolares = ''

    for linea in texto.splitlines():
        if "Impuestos, cargos e intereses" in linea:
            dentro_de_seccion = True
            continue
        if "SALDO ACTUAL" in linea:
            dentro_de_seccion = False
            partes = linea.split()
            if len(partes) >= 3:
                total_dolares = partes[-1]
                total_pesos = partes[-2]
            continue
        if dentro_de_seccion:
            match = patron_linea.match(linea)
            if match:
                fecha_raw = match.group(1)
                descripcion = match.group(2).strip()
                pesos = match.group(3).strip()
                dolares = match.group(4).strip() if match.group(4) else ''
                _, fecha_timestamp = convertir_fecha(fecha_raw)
                importe = dolares if dolares else pesos
                detalles.append({
                    "fecha": fecha_raw,
                    "fechaTimestamp": fecha_timestamp,
                    "descripcion": descripcion,
                    "importe": importe
                })

    return detalles, {"pesos": total_pesos, "dolares": total_dolares}

@app.post("/parsePDF")
async def parse_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    try:
        # Leer el contenido del PDF
        contents = await file.read()
        pdf_file = io.BytesIO(contents)
        reader = PdfReader(pdf_file)
        texto_total = "\n".join(page.extract_text() for page in reader.pages)

        # Procesar secciones
        juan_detalles, juan_total = extraer_consumos_con_total(texto_total, "Consumos J Fernandez Tubello", "TOTAL CONSUMOS DE J FERNANDEZ TUBELLO")
        cami_detalles, cami_total = extraer_consumos_con_total(texto_total, "Consumos Camila V Montiel", "TOTAL CONSUMOS DE CAMILA V MONTIEL")
        impuestos_detalles, saldo_total = extraer_impuestos(texto_total)
        
        # Construir JSON final
        resultado = ""
        empty_values = (cami_total['pesos'])
        if (empty_values == ""):
            resultado = {
             "Juan": {
                    "Detail": juan_detalles,
                    "Total": juan_total
                },
             "Total": saldo_total
        }
        else:
            resultado = {
             "Juan": {
                    "Detail": juan_detalles,
                    "Total": juan_total
                },
             "Cami": {
                   "Detail": cami_detalles,
                    "Total": cami_total
                },
             "Total": saldo_total
            }

        return JSONResponse(content=resultado)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)  # Usando puerto 8080 como ejemplo