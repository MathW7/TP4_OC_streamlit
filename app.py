# **************************************************************************************************************
# Nom......... : app.py
# Rôle ....... : Application Streamlit pour visualiser, modifier les métadonnées EXIF d’images ainsi que visualisé sur une carte les endroits déjà visités ou les destinations de rêve
# Auteur ..... : Mathilde Wattiez
# Version .... : V1.0 du 30/07/2025
# Licence .... : Réalisé dans le cadre du cours d’Outils Collaboratifs
# Usage ...... : Exécuter avec Python 3.11 : python -m streamlit run app.py
# **************************************************************************************************************

import streamlit as st           
from PIL import Image, ExifTags          
import piexif                            
import io                                
import folium                           
from streamlit_folium import st_folium  
from geopy.geocoders import Nominatim    
from geopy.exc import GeocoderTimedOut   
import time                              


st.set_page_config(page_title="Chapitre 4 - Exercice 4.2", layout="centered")

def get_exif(img):
    """Récupère les métadonnées EXIF sous forme de dictionnaire lisible"""
    try:
        raw = img._getexif() or {}
        exif = {
            (ExifTags.TAGS.get(k, k)): (
                {ExifTags.GPSTAGS.get(t, t): v[t] for t in v} if ExifTags.TAGS.get(k) == "GPSInfo" else v
            ) for k, v in raw.items()
        }
        return exif
    except AttributeError:
        return {}

def get_decimal_from_dms(dms, ref):
    """Convertit une coordonnée DMS (degrés, minutes, secondes) en décimale"""
    deg, mn, sec = dms
    decimal = deg + mn / 60 + sec / 3600
    return -decimal if ref in ['S', 'W'] else decimal

def get_gps_coords(exif):
    """Extrait les coordonnées GPS (lat, lon) depuis les métadonnées EXIF"""
    # récupère les infos GPS
    gps = exif.get("GPSInfo")
    try:
        return (
            # permet de transformer les données GPS (au format DMS)en degrés décimaux via la fonction get_decimal_from_dms en prenant en compte les références latitude et longitude pour définir le signe 
            get_decimal_from_dms(gps["GPSLatitude"], gps["GPSLatitudeRef"]),
            get_decimal_from_dms(gps["GPSLongitude"], gps["GPSLongitudeRef"]),
        )
    except (TypeError, KeyError):
        return None, None

def deg_to_dms_rational(deg):
    """Convertit une coordonnée décimale en format EXIF"""
    d = abs(deg) # prend la valeur absolue
    m, s = divmod(d * 3600, 60) #Convertion en minutes et secondes (la partie décimale)
    d, m = divmod(m, 60) #Convertion en degrés et minutes (la partie entière)
    #Retourne le résultat dans le format attendu par EXIF (degrés, minutes et seconde exprimés en fractions)
    return ((int(d),1), (int(m),1), (int(s*100),100))

def geocode_retry(geolocator, query, attempts=3):
    """Tente plusieurs fois de géocoder une adresse pour éviter les timeouts"""
    # permet d'essayer de géocoder l'adresse via 3 essais
    for _ in range(attempts):
        try:
            return geolocator.geocode(query, timeout=10)
        except GeocoderTimedOut:
            time.sleep(1) #Si la requête dépasse le timeout, on attend 1 seconde
    return None

def reverse_geocode_retry(geolocator, coords, attempts=3):
    """Effectue un reverse geocoding avec plusieurs tentatives en cas d'échec"""
    for _ in range(attempts):
        try:
            return geolocator.reverse(coords, timeout=10)
        except GeocoderTimedOut:
            time.sleep(1)
    return None

st.title("Chapitre 4 - Exercice 4.2")

file = st.file_uploader("Téléversez une image JPG", type=["jpg", "jpeg"])
if not file:
    st.stop()

img = Image.open(file)
exif = get_exif(img)

st.image(img, caption="Aperçu", use_container_width=True)

lat, lon = get_gps_coords(exif)
st.session_state.setdefault("lat", lat)
st.session_state.setdefault("lon", lon)


if exif:
    st.subheader("Métadonnées trouvées")
    for k, v in exif.items():
        if k != "GPSInfo":
            st.text(f"{k} : {v}")

    if lat and lon:
        geolocator = Nominatim(user_agent="exif_app")
        location = reverse_geocode_retry(geolocator, (float(lat), float(lon)))#permet d'obtenir l'adresse via les coordonnées GPS
        if location:
            adresse = location.address
        else:
            adresse = "Adresse inconnue"

        st.success(f"Coordonnées : {float(lat):.6f}, {float(lon):.6f} ({adresse})")

    else:
        st.warning("Pas de coordonnées GPS détectées.")


st.subheader("Modifier les métadonnées")

# les champs du formulaires pour modifier les informations de l'image
adresse = st.text_input("Nouvelle adresse GPS :")
artist = st.text_input("Auteur :", exif.get("Artist", ""))
description = st.text_input("Description :", exif.get("ImageDescription", ""))
copyright = st.text_input("Copyright :", exif.get("Copyright", ""))
software = st.text_input("Logiciel :", exif.get("Software", ""))

if st.button("Appliquer les modifications"):
    # Initialisation des coordonnées GPS avec les valeurs actuelles
    new_lat, new_lon = lat, lon
    gps_ifd = {}  # Dictionnaire qui contiendra les nouvelles données GPS

    # Si une adresse a été saisie 
    if adresse:
        # On tente de géocoder l'adresse 
        loc = geocode_retry(Nominatim(user_agent="exif_app_edit"), adresse)

        if loc:
            # Si l'adresse a été trouvée, les coordonnées sont mise à jour
            new_lat, new_lon = loc.latitude, loc.longitude

            # Permet de construire les données EXIF
            gps_ifd = {
                piexif.GPSIFD.GPSLatitudeRef: "N" if new_lat >= 0 else "S",
                piexif.GPSIFD.GPSLatitude: deg_to_dms_rational(new_lat),
                piexif.GPSIFD.GPSLongitudeRef: "E" if new_lon >= 0 else "W",
                piexif.GPSIFD.GPSLongitude: deg_to_dms_rational(new_lon),
            }

            st.success(f"Adresse trouvée : {loc.address}")
        else:
            st.warning("Adresse introuvable, coordonnées GPS non modifiées.")


    try:
        # Chargement des données EXIF de l'image
        exif_dict = piexif.load(img.info.get("exif", b""))

        #mise à jour des champs textes dans la section "0th"
        exif_dict["0th"].update({
            piexif.ImageIFD.Artist: artist.encode(),
            piexif.ImageIFD.ImageDescription: description.encode(),
            piexif.ImageIFD.Copyright: copyright.encode(),
            piexif.ImageIFD.Software: software.encode(),
        })

        # Si de nouvelles données GPS sont données alors cela met à jour les données GPS 
        if gps_ifd:
            exif_dict["GPS"] = gps_ifd

        # permet d'enregistrer l'image dans un tampon mémoire
        output = io.BytesIO()
        img.save(output, format="jpeg", exif=piexif.dump(exif_dict))

        # Mise à jour de l’état de l'image 
        st.session_state.image_modifiee = output.getvalue()
        st.session_state.lat, st.session_state.lon = new_lat, new_lon
        st.success("Modifications appliquées.")

    except piexif.InvalidImageDataError as e:
        st.error(f"Erreur EXIF : {e}")
    except Exception as e:
        st.error(f"Erreur inconnue : {e}")



lat, lon = st.session_state.get("lat"), st.session_state.get("lon")
if lat and lon:
    st.subheader("Carte GPS")
    m = folium.Map(location=[lat, lon], zoom_start=13)
    folium.Marker([lat, lon], tooltip="Position GPS", icon=folium.Icon(color="red")).add_to(m)
    st_folium(m, width=700, height=500)



if "image_modifiee" in st.session_state:
    st.download_button("Télécharger l’image modifiée", st.session_state.image_modifiee, "photo_modifiee.jpg", "image/jpeg")


st.subheader("Ajouter des lieux que vous avez visité ou vos destinations de rêve")

st.markdown("""
Format possible :
- `Ville`, `Pays` ou `Adresse`
- `Nom, Adresse`
- `Nom, latitude, longitude `
""")

poi_input = st.text_area("Lieux à ajouter (un par ligne) :")

if poi_input:
    geolocator = Nominatim(user_agent="poi_app")
    poi_map = folium.Map(zoom_start=2)
    coords = []

# Traite chaque ligne saisie par l'utilisateur comme un lieu en retirant les espaces et les vigules
# 3 cas de figures : 
# si 3 arguments alors on considère que c'est nom, latitude, longitude
# Si 2 arguments alors on considère que c'est nom et un lieu (par exemple une ville)
# Si 1 argument alors on considère que c'est une adresse, une ville, un pays 
# Convertit au besoin les adresses en coordonnées GPS via géocodage
# place un marqueur rouge pour chaque lieu sur la carte
# Ajout d’un délai pour éviter de surcharger l’API de géocodage.

    for line in poi_input.strip().split("\n"):
        try:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 3:
                name, lat, lon = parts[0], float(parts[1]), float(parts[2])
            elif len(parts) == 2:
                name, query = parts
                loc = geocode_retry(geolocator, query)
                if not loc: raise ValueError(f"Lieu introuvable : {query}")
                lat, lon = loc.latitude, loc.longitude
            else:
                loc = geocode_retry(geolocator, parts[0])
                if not loc: raise ValueError(f"Lieu introuvable : {parts[0]}")
                name, lat, lon = loc.address, loc.latitude, loc.longitude

            folium.Marker([lat, lon], tooltip=name, icon=folium.Icon(color="red")).add_to(poi_map)
            coords.append([lat, lon])
            time.sleep(1)  # Anti-spam API

        except Exception as e:
            st.warning(f"Erreur : {line} → {e}")

    if coords:
        if len(coords) >= 2:
            folium.PolyLine(coords, color="red").add_to(poi_map)
        poi_map.fit_bounds([min(coords), max(coords)])
        st_folium(poi_map, width=700, height=500)
