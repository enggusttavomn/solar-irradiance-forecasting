"""Cadastro auditavel das localidades de fabricas de veiculos eletricos."""

from __future__ import annotations

import math

import pandas as pd


METODO_COORDENADAS = (
    "Centroide do elemento da fabrica no OpenStreetMap/Nominatim, "
    "validado contra fonte oficial da empresa em 2026-06-06"
)

LOCALIDADES_EV = [
    {
        "nome": "BYD Camacari",
        "pais": "Brasil",
        "lat": -12.6733774,
        "lon": -38.2812339,
        "endereco": "Avenida Henry Ford, Polo Industrial, Camacari, Bahia, Brasil",
        "fonte_localidade": (
            "https://www.byd.com/br/noticias-byd-brasil/"
            "byd-retoma-producao-em-camacari-e-chega-a-quase-20-mil-veiculos-.html"
        ),
        "fonte_coordenadas": "https://www.openstreetmap.org/way/319513382",
        "osm_elemento": "way/319513382",
    },
    {
        "nome": "Tesla Gigafactory Nevada",
        "pais": "EUA",
        "lat": 39.5403926,
        "lon": -119.4390524,
        "endereco": "1 Electric Avenue, Storey County, Nevada 89437, EUA",
        "fonte_localidade": "https://www.tesla.com/contact",
        "fonte_coordenadas": "https://www.openstreetmap.org/way/422015619",
        "osm_elemento": "way/422015619",
    },
    {
        "nome": "Tesla Gigafactory Texas",
        "pais": "EUA",
        "lat": 30.2219321,
        "lon": -97.6187733,
        "endereco": "1 Tesla Road, Austin, Texas 78725, EUA",
        "fonte_localidade": "https://www.tesla.com/giga-texas",
        "fonte_coordenadas": "https://www.openstreetmap.org/way/990257143",
        "osm_elemento": "way/990257143",
    },
    {
        "nome": "Hyundai Metaplant Georgia",
        "pais": "EUA",
        "lat": 32.1605262,
        "lon": -81.4509985,
        "endereco": "1500 Genesis Drive, Ellabell, Georgia 31308, EUA",
        "fonte_localidade": (
            "https://www.hyundaimotorgroup.com/en/news/CONT0000000000173041"
        ),
        "fonte_coordenadas": "https://www.openstreetmap.org/way/1207640268",
        "osm_elemento": "way/1207640268",
    },
    {
        "nome": "Rivian Normal",
        "pais": "EUA",
        "lat": 40.5092914,
        "lon": -89.0545444,
        "endereco": "100 Rivian Motorway, Normal, Illinois 61761, EUA",
        "fonte_localidade": "https://stories.rivian.com/r2-expansion-03-2025",
        "fonte_coordenadas": "https://www.openstreetmap.org/way/438033786",
        "osm_elemento": "way/438033786",
    },
    {
        "nome": "Tesla Fremont Factory",
        "pais": "EUA",
        "lat": 37.4926897,
        "lon": -121.9415083,
        "endereco": "45500 Fremont Boulevard, Fremont, California 94538, EUA",
        "fonte_localidade": "https://www.tesla.com/contact",
        "fonte_coordenadas": "https://www.openstreetmap.org/way/38080584",
        "osm_elemento": "way/38080584",
    },
    {
        "nome": "Lucid AMP 1 Casa Grande",
        "pais": "EUA",
        "lat": 32.8568519,
        "lon": -111.7784376,
        "endereco": "317 S. Thornton Road, Casa Grande, Arizona 85193, EUA",
        "fonte_localidade": (
            "https://ir.lucidmotors.com/news-releases/news-release-details/"
            "lucid-starts-production-groundbreaking-lucid-air-arizona/"
        ),
        "fonte_coordenadas": "https://www.openstreetmap.org/way/1254715766",
        "osm_elemento": "way/1254715766",
    },
    {
        "nome": "GM Factory Zero",
        "pais": "EUA",
        "lat": 42.3815123,
        "lon": -83.0453415,
        "endereco": "2500 East Grand Boulevard, Detroit, Michigan 48211, EUA",
        "fonte_localidade": "https://www.gm.com/company/facilities/factory-zero",
        "fonte_coordenadas": "https://www.openstreetmap.org/way/554307172",
        "osm_elemento": "way/554307172",
    },
    {
        "nome": "Ford Rouge Electric Vehicle Center",
        "pais": "EUA",
        "lat": 42.3056229,
        "lon": -83.1676332,
        "endereco": "Ford River Rouge Complex, Dearborn, Michigan 48120, EUA",
        "fonte_localidade": (
            "https://corporate.ford.com/corporate/articles/products/f-150-lightning"
        ),
        "fonte_coordenadas": "https://www.openstreetmap.org/way/496054397",
        "osm_elemento": "way/496054397",
    },
    {
        "nome": "BMW San Luis Potosi",
        "pais": "Mexico",
        "lat": 21.9682649,
        "lon": -100.8491733,
        "endereco": (
            "Boulevard BMW 655, Parque Industrial Desarrollo Logistik II, "
            "Villa de Reyes, San Luis Potosi 79526, Mexico"
        ),
        "fonte_localidade": (
            "https://www.bmwgroup-werke.com/san-luis-potosi/en/contact.html"
        ),
        "fonte_coordenadas": "https://www.openstreetmap.org/way/553644102",
        "osm_elemento": "way/553644102",
    },
]

for localidade in LOCALIDADES_EV:
    localidade["metodo_coordenadas"] = METODO_COORDENADAS


def distancia_haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calcula a distancia de grande circulo entre dois pontos."""
    raio_terra_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * raio_terra_km * math.asin(math.sqrt(a))


def dataframe_localidades() -> pd.DataFrame:
    """Retorna uma copia tabular do cadastro de localidades."""
    return pd.DataFrame(LOCALIDADES_EV).copy()


__all__ = [
    "LOCALIDADES_EV",
    "METODO_COORDENADAS",
    "dataframe_localidades",
    "distancia_haversine_km",
]
