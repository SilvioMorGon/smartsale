import streamlit as st
import openai
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os
from email.mime.base import MIMEBase
from email import encoders
import requests
import logging
from bs4 import BeautifulSoup

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inicializar variables de estado
if 'context' not in st.session_state:
    st.session_state.context = ''
if 'generated_subject' not in st.session_state:
    st.session_state.generated_subject = ''
if 'generated_body' not in st.session_state:
    st.session_state.generated_body = ''
if 'active_tool' not in st.session_state:
    st.session_state.active_tool = None  # Esta variable rastrea qué herramienta está activa

# Configuración de OpenAI y Google Maps API
# Asegúrate de reemplazar las claves de API con tus propias claves de forma segura
openai.api_key = st.secrets["openai"]["api_key"]
GOOGLE_MAPS_API_KEY = st.secrets["google_maps"]["api_key"]

# Configuración del servidor SMTP para Gmail
smtp_server = 'smtp.gmail.com'
smtp_port = 587
smtp_username = st.secrets["smtp"]["username"]
smtp_password = st.secrets["smtp"]["password"]  # Reemplaza con tu contraseña de aplicación
sender_email = smtp_username

# Función para la herramienta "Generador de Mensaje"
def openai_gpt_page():
    st.subheader("Generador de Asunto y Cuerpo de Correo Electrónico")
    st.write("Proporciona información sobre el correo electrónico que deseas enviar. "
             "El asistente te ayudará a generar un asunto y cuerpo de correo adecuados.")

    # Campo de entrada para el contexto
    context = st.text_area("Escribe la información o contexto aquí:", value=st.session_state.context)

    if st.button("Generar Mensaje"):
        if context:
            st.session_state.context = context  # Guardamos el contexto en session_state

            system_prompt = (
                "Eres un asistente que ayuda a vendedores a redactar correos electrónicos. "
                "Con base en la información proporcionada, genera un asunto y cuerpo de correo electrónico "
                "que sea persuasivo y adecuado para la audiencia objetivo. "
                "Proporciona el asunto y el cuerpo en el siguiente formato:\n\n"
                "Asunto: [aquí el asunto]\n"
                "Cuerpo:\n[aquí el cuerpo]\n\n"
                "No incluyas texto adicional, ni tampoco variables para completar por que son correos generales"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ]

            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.7
                )

                assistant_reply = response['choices'][0]['message']['content'].strip()

                # Parsear la respuesta para extraer el asunto y el cuerpo
                subject = ''
                body = ''
                lines = assistant_reply.splitlines()
                i = 0
                while i < len(lines):
                    line = lines[i]
                    if line.startswith('Asunto:'):
                        subject = line[len('Asunto:'):].strip()
                    elif line.startswith('Cuerpo:'):
                        # Recopilar todas las líneas después de 'Cuerpo:'
                        body_lines = []
                        i += 1
                        while i < len(lines):
                            body_lines.append(lines[i])
                            i += 1
                        body = '\n'.join(body_lines).strip()
                        break
                    i += 1

                # Guardamos el asunto y el cuerpo generados en session_state
                st.session_state.generated_subject = subject
                st.session_state.generated_body = body

                st.success("Mensaje generado exitosamente.")

            except Exception as e:
                st.error(f"Error al generar el mensaje: {e}")
        else:
            st.error("Por favor, escribe información o contexto para generar el mensaje.")

    # Mostramos el asunto y el cuerpo generados, si existen
    st.text_input("Asunto generado:", value=st.session_state.generated_subject)
    st.text_area("Cuerpo generado:", value=st.session_state.generated_body, height=300)

# Función para la herramienta "Automatización de Mail"
def emailfree_page():
    st.subheader("Envío de Correos Personalizados")

    # Sección para ingresar el remitente
    from_name = st.text_input("Nombre del remitente", value="Biominer", placeholder="Ingresa el nombre del remitente")

    # Sección para escribir el asunto del correo (campo obligatorio)
    subject = st.text_input("Asunto del Correo", value=st.session_state.get('generated_subject', ''), placeholder="Ingresa el asunto del correo")

    # Sección para escribir el cuerpo del mensaje del correo (opcional)
    body_template = st.text_area("Cuerpo del Correo (opcional)", value=st.session_state.get('generated_body', ''), placeholder="Escribe el cuerpo del correo aquí")

    # Slider para programar la cantidad de correos por hora
    mails_per_hour = st.slider("Cantidad de correos por hora", min_value=1, max_value=50, value=10)

    uploaded_file = st.file_uploader("Sube un archivo Excel con los correos", type=["xlsx"])
    inline_image = st.file_uploader("Sube una imagen para incluir en el cuerpo del correo (opcional)", type=["png", "jpg", "jpeg"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.columns = [col.strip() for col in df.columns]  # Eliminar espacios en blanco
        st.write("Datos cargados:")
        st.write(df)

        include_inline_image = False
        inline_image_path = None

        if inline_image:
            include_inline_image = True
            inline_image_path = inline_image.name
            with open(inline_image_path, "wb") as f:
                f.write(inline_image.getbuffer())

        # Botón para iniciar el envío de correos
        if st.button("Enviar Correos", key="btn_enviar_correos"):
            if subject.strip() == "":
                st.warning("Por favor, ingresa el asunto del correo.")
            elif not body_template.strip() and not include_inline_image:
                st.warning("Por favor, ingresa el cuerpo del correo o sube una imagen para enviar.")
            else:
                # Lista de imágenes (botones) que se incluirán en el correo
                images = [
                    ("/home/silvio/Documentos/Escala/EscalaAnalytica/smartsales/images/whatsapp.png", "wp"),
                    ("/home/silvio/Documentos/Escala/EscalaAnalytica/smartsales/images/mail.png", "email")
                ]

                sent_count = 0
                failed_count = 0

                for i in range(len(df)):
                    to_address = df.iloc[i]['EMAIL']
                    personal_data = df.iloc[i].to_dict()

                    # Generar cuerpo del correo personalizado
                    body = body_template.format(**personal_data)
                    email_body = generate_email_body(body, include_inline_image)

                    if send_email(to_address, subject, email_body, images=images, from_name=from_name, inline_image=inline_image_path):
                        sent_count += 1
                        # Puedes agregar aquí una barra de progreso o mensajes de estado
                    else:
                        failed_count += 1
                        st.write(f"Error al enviar correo a {to_address}")

                    # Controlar la tasa de envío
                    if (i + 1) % mails_per_hour == 0 and (i + 1) != len(df):
                        st.info("Se alcanzó el límite de correos por hora. Esperando para continuar...")
                        st.experimental_rerun()

                st.success(f"Envío completado. Total enviados: {sent_count}, Fallidos: {failed_count}")

# Función para generar el cuerpo del correo electrónico
def generate_email_body(body, include_inline_image):
    email_body = ""

    if body.strip():
        email_body += body + "<br><br>"

    if include_inline_image:
        email_body += '<p><img src="cid:inline_image" alt="Imagen" width="600"/></p>'

    # Agregar botones sin que aparezcan como archivos adjuntos
    email_body += """
    <table>
        <tr>
            <td>
                <a href="https://wa.me/+5492644449090?text=Hola%20recibi%20el%20mail%20escribime">
                    <img src="cid:wp" alt="Escríbeme por WhatsApp" width="150"/>
                </a>
            </td>
            <td>
                <a href="mailto:biominer.online@gmail.com?subject=Podes%20contactarme">
                    <img src="cid:email" alt="Me interesa la promoción, puedes llamarme" width="150"/>
                </a>
            </td>
        </tr>
    </table>
    """

    return email_body

# Función para enviar correos electrónicos
def send_email(to_address, subject, body, images, from_name, inline_image=None):
    try:
        msg = MIMEMultipart('related')
        msg['From'] = f"{from_name} <{sender_email}>"
        msg['To'] = to_address
        msg['Subject'] = subject

        # Parte alternativa en caso de que el cliente de correo no soporte HTML
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)

        # Si no hay cuerpo, proporciona un mensaje predeterminado
        if not body.strip() and not inline_image:
            body = " "

        # Adjuntar el cuerpo del correo en HTML
        msg_text = MIMEText(body, 'html')
        msg_alternative.attach(msg_text)

        # Adjuntar imagen en línea si existe
        if inline_image:
            with open(inline_image, 'rb') as img:
                img_data = img.read()
                mime = MIMEBase('image', 'jpeg')
                mime.set_payload(img_data)
                encoders.encode_base64(mime)
                mime.add_header('Content-ID', '<inline_image>')
                mime.add_header('Content-Disposition', 'inline')
                msg.attach(mime)

        # Adjuntar otras imágenes (botones)
        for img_path, cid in images:
            with open(img_path, 'rb') as img:
                # Determinar el subtipo de imagen según la extensión del archivo
                _, ext = os.path.splitext(img_path)
                ext = ext.lower()
                if ext == '.png':
                    subtype = 'png'
                elif ext == '.jpg' or ext == '.jpeg':
                    subtype = 'jpeg'
                elif ext == '.gif':
                    subtype = 'gif'
                else:
                    subtype = 'octet-stream'

                img_data = img.read()
                mime = MIMEBase('image', subtype)
                mime.set_payload(img_data)
                encoders.encode_base64(mime)
                mime.add_header('Content-ID', f'<{cid}>')
                mime.add_header('Content-Disposition', 'inline')
                msg.attach(mime)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Iniciar conexión segura
            server.login(smtp_username, smtp_password)  # Iniciar sesión en el servidor SMTP
            server.sendmail(sender_email, to_address, msg.as_string())  # Enviar correo

        return True
    except Exception as e:
        print(f"Error al enviar correo a {to_address}: {e}")
        return False

# Función para la herramienta "Google Maps"
def google_maps_search_page():
    st.subheader("Búsqueda de Lugares en Google Maps")

    search_option = st.radio("Selecciona el tipo de búsqueda:", ("Por ubicación/zona", "Por nombre del lugar"))

    # Diccionario de mapeo de tipos de lugares
    place_type_mapping = {
        "Hospital": "hospital",
        "Veterinaria": "veterinary_care",
        "Farmacia": "pharmacy",
        "Consultorio Médico": "doctor",
        "Odontólogo": "dentist"
    }

    # Obtener el tipo de lugar seleccionado y mapearlo al valor de la API
    place_type_display = st.selectbox("Selecciona el tipo de lugar a buscar:", list(place_type_mapping.keys()))
    place_type = place_type_mapping[place_type_display]

    if search_option == "Por ubicación/zona":
        location = st.text_input("Ingresa la ubicación o zona:")
        radius = st.slider("Radio de búsqueda (en metros)", min_value=1000, max_value=50000, value=5000)
        name = None
    else:
        location = None
        name = st.text_input("Ingresa el nombre del lugar:")
        radius = None  # Aquí defines 'radius' como None

    analyze_reviews = st.checkbox("Analizar comentarios", value=True)
    analyze_website = st.checkbox("Analizar sitio web", value=False)

    if st.button("Buscar"):
        if (search_option == "Por ubicación/zona" and location) or (search_option == "Por nombre del lugar" and name):
            st.info("Realizando búsqueda...")
            places = search_places(location=location, radius=radius, name=name, place_type=place_type)
        else:
            st.error("Por favor, ingresa los datos necesarios para la búsqueda.")
            return

        if places:
            st.write(f"Se encontraron {len(places)} lugares:")
            for place in places:
                name = place.get('name', 'N/A')
                address = place.get('formatted_address', 'No especificada')
                rating = place.get('rating', 'No disponible')
                total_ratings = place.get('user_ratings_total', 0)
                place_id = place.get('place_id', 'N/A')
                google_maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id != 'N/A' else 'N/A'
                phone_number = place.get('formatted_phone_number', 'No disponible')
                website = place.get('website', 'No disponible')
                opening_hours = place.get('opening_hours', {}).get('weekday_text', 'No disponible')

                with st.expander(f"{name} - {address}"):
                    st.write(f"**Nombre:** {name}")
                    st.write(f"**Dirección:** {address}")
                    st.write(f"**Calificación:** {rating} ⭐ ({total_ratings} opiniones)")
                    st.write(f"**Teléfono:** {phone_number}")
                    st.write(f"**Sitio web:** {website}")
                    st.write(f"**Horario de apertura:** {opening_hours}")
                    st.write(f"[Ver en Google Maps]({google_maps_url})")
                    logging.info(f"Lugar encontrado: {name} - {address}")

            # Realizar el análisis con GPT
            if analyze_reviews or analyze_website:
                with st.spinner('Analizando información con GPT...'):
                    analysis = analyze_places_with_gpt(places, analyze_reviews=analyze_reviews, analyze_website=analyze_website)
                st.write("### Análisis GPT:")
                st.write(analysis)
        else:
            st.write("No se encontraron lugares con los criterios de búsqueda especificados.")

# Función para buscar lugares
def search_places(location=None, radius=5000, name=None, place_type='hospital'):
    try:
        if name:
            logging.info("Buscando lugar por nombre...")
            places_url = f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input={name}&inputtype=textquery&fields=place_id,name,geometry,formatted_address,types&key={GOOGLE_MAPS_API_KEY}"
            places_response = requests.get(places_url).json()
            if places_response['status'] != 'OK':
                st.error("No se encontraron lugares con ese nombre.")
                return []
        else:
            logging.info("Obteniendo coordenadas para la ubicación proporcionada...")
            geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location}&key={GOOGLE_MAPS_API_KEY}"
            geocode_response = requests.get(geocode_url).json()
            if geocode_response['status'] != 'OK':
                st.error("No se pudieron obtener las coordenadas de la ubicación. Por favor, verifica la ubicación.")
                return []

            coordinates = geocode_response['results'][0]['geometry']['location']
            lat, lng = coordinates['lat'], coordinates['lng']

            logging.info(f"Coordenadas obtenidas: Latitud {lat}, Longitud {lng}")

            logging.info(f"Buscando {place_type} en la zona...")
            places_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type={place_type}&key={GOOGLE_MAPS_API_KEY}"
            places_response = requests.get(places_url).json()
            if places_response['status'] != 'OK':
                st.error(f"No se encontraron {place_type} en la zona especificada.")
                return []

        # Detalles adicionales para cada lugar
        detailed_results = []
        if name:
            place_id = places_response['candidates'][0].get('place_id', 'N/A')
            detail_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={GOOGLE_MAPS_API_KEY}&fields=name,formatted_address,geometry,formatted_phone_number,website,rating,user_ratings_total,reviews,opening_hours"
            detail_response = requests.get(detail_url).json()

            if detail_response['status'] == 'OK':
                details = detail_response['result']
                detailed_results.append(details)
        else:
            for place in places_response['results']:
                place_id = place.get('place_id', 'N/A')
                detail_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={GOOGLE_MAPS_API_KEY}&fields=name,formatted_address,geometry,formatted_phone_number,website,rating,user_ratings_total,reviews,opening_hours"
                detail_response = requests.get(detail_url).json()

                if detail_response['status'] == 'OK':
                    details = detail_response['result']
                    detailed_results.append(details)

        return detailed_results
    except Exception as e:
        logging.error("Error al buscar lugares en Google Maps.")
        logging.error(e)
        st.error("Error al buscar lugares. Por favor, intenta nuevamente.")
        return []

# Función para analizar lugares con GPT
def analyze_places_with_gpt(places, analyze_reviews=False, analyze_website=False):
    prompt = "A continuación se proporciona información sobre varios lugares. Proporcione un análisis detallado basado en la información disponible:\n\n"

    for place in places:
        name = place.get('name', 'N/A')
        address = place.get('formatted_address', 'No especificada')
        rating = place.get('rating', 'No disponible')
        total_ratings = place.get('user_ratings_total', 0)
        phone_number = place.get('formatted_phone_number', 'No disponible')
        website = place.get('website', 'No disponible')

        prompt += f"Nombre: {name}\nDirección: {address}\nCalificación: {rating} ⭐ ({total_ratings} opiniones)\n"
        prompt += f"Teléfono: {phone_number}\nSitio web: {website}\n"

        if analyze_reviews and 'reviews' in place:
            prompt += "Reseñas:\n"
            for review in place['reviews']:
                review_text = review.get('text', 'No disponible')
                prompt += f"- {review_text}\n"

        if analyze_website and website != 'No disponible':
            try:
                logging.info(f"Extrayendo información del sitio web de {name}...")
                website_content = extract_website_content(website)
                prompt += f"Contenido del sitio web de {name}:\n{website_content}\n"
            except Exception as e:
                logging.error(f"Error al extraer información del sitio web de {name}: {e}")
                prompt += f"No se pudo extraer información del sitio web de {name}.\n"

        prompt += "\n"

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",  # Puedes ajustar el modelo según tus necesidades
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return response['choices'][0]['message']['content'].strip()

# Función para extraer contenido del sitio web
def extract_website_content(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extraer texto del sitio web
    texts = soup.find_all(text=True)
    visible_texts = filter(tag_visible, texts)
    content = u" ".join(t.strip() for t in visible_texts)
    return content

def tag_visible(element):
    from bs4 import Comment
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
        return False
    if isinstance(element, Comment):
        return False
    return True

# Función principal
def main():
    st.title("SmartSales")
    st.write("Selecciona una herramienta para comenzar:")

    # Botones para cada herramienta
    col1, col2, col3 = st.columns(3)
    with col1:
         if st.button("📝 Generador de Mensaje 📝", key="btn_generador_mensaje"):
            st.session_state.active_tool = 'generador_mensaje'
    with col2:
        if st.button("📧 Enviar Correos 📧", key="btn_enviar_correos_menu"):
            st.session_state.active_tool = 'enviar_correos'
    with col3:
        if st.button("🗺️ Google Maps 🗺️", key="btn_google_maps"):
            st.session_state.active_tool = 'google_maps'

    # Mostrar la herramienta seleccionada
    if st.session_state.active_tool == 'generador_mensaje':
        openai_gpt_page()
    elif st.session_state.active_tool == 'enviar_correos':
        emailfree_page()
    elif st.session_state.active_tool == 'google_maps':
        google_maps_search_page()
    else:
        st.info("Por favor, selecciona una herramienta.")

if __name__ == "__main__":
    main()
