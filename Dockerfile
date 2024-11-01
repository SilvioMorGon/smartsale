# Usa una imagen base de Python
FROM python:3.9-slim

# Define el directorio de trabajo
WORKDIR /app

# Copia los archivos de la app
COPY . /app

# Instala las dependencias
RUN pip install -r requirements.txt
RUN pip install --upgrade numpy pandas

# Expone el puerto que usa Streamlit por defecto
EXPOSE 8501

# Comando para ejecutar la app de Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.enableCORS=false"]
