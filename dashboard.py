import os
import json
import requests
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, HeatMapWithTime

# --------------------------------------------------
# 1. Streamlit 설정 및 API 키 로드
# --------------------------------------------------
st.set_page_config(page_title="성수동 단기체류 외국인 대시보드", layout="wide")
API_KEY = st.secrets["SEOUL_API_KEY"]

# --------------------------------------------------
# 2. 성수동 집계구 접두사 정의
# --------------------------------------------------
VALID_PREFIXES = {"1104065", "1104066", "1104067", "1104068"}

# --------------------------------------------------
# 3. 사이드바: 사용자 입력
# --------------------------------------------------
st.sidebar.header("필터 설정")
date = st.sidebar.date_input("기준일자", value=pd.to_datetime("2025-09-05"))
hour = st.sidebar.slider("시간대 (시)", 0, 23, 14)
viz_type = st.sidebar.selectbox("시각화 유형", ["포인트", "히트맵", "타임 히트맵"])

# --------------------------------------------------
# 4. GeoJSON 파일 업로드 및 필터링
# --------------------------------------------------
uploaded_file = st.sidebar.file_uploader("집계구 경계 GeoJSON 업로드", type="geojson")
if not uploaded_file:
    st.warning("GeoJSON 파일을 업로드해주세요.")
    st.stop()

gdf = gpd.read_file(uploaded_file)
# OA_CD 필드가 다를 경우 실제 필드명으로 변경
gdf = gdf[gdf["OA_CD"].str[:7].isin(VALID_PREFIXES)]

# --------------------------------------------------
# 5. API 데이터 조회 함수
# --------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_data(date_str, hour_str):
    """
    서울시 열린데이터 API에서 단기체류 외국인 데이터 조회
    """
    url = (
        f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/"
        f"TEMP_FOREIGNER/1/1000/{date_str}/{hour_str}/"
    )
    resp = requests.get(url)
    resp.raise_for_status()
    items = resp.json().get("TEMP_FOREIGNER", {}).get("row", [])
    df = pd.DataFrame(items)
    # 앞7자리 필터링
    df = df[df["OA_CD"].str[:7].isin(VALID_PREFIXES)]
    return df

# --------------------------------------------------
# 6. 데이터 로드
# --------------------------------------------------
date_str = date.strftime("%Y%m%d")
hour_str = f"{hour:02d}"
df = fetch_data(date_str, hour_str)

# --------------------------------------------------
# 7. 기본 지도 생성
# --------------------------------------------------
m = folium.Map(
    location=[37.5445, 127.0557],
    zoom_start=15,
    tiles="CartoDB dark_matter"
)
# 성수동 경계 추가
folium.GeoJson(
    gdf.to_json(),
    name="성수동 경계",
    style_function=lambda feat: {
        "color": "white",
        "weight": 2,
        "fillOpacity": 0
    }
).add_to(m)

# --------------------------------------------------
# 8. 시각화
# --------------------------------------------------
if viz_type == "포인트":
    for _, row in df.iterrows():
        tract = gdf[gdf["OA_CD"] == row["OA_CD"]]
        centroid = tract.geometry.centroid.iloc[0]
        folium.CircleMarker(
            location=[centroid.y, centroid.x],
            radius=max(int(row["TOT_LVPOP_CO"]) / 50, 3),
            color="red",
            fill=True,
            fill_opacity=0.7,
            popup=(
                f"집계구: {row['OA_CD']}<br>"
                f"총생활인구: {row['TOT_LVPOP_CO']}"
            )
        ).add_to(m)

elif viz_type == "히트맵":
    heat_data = [
        [gdf[gdf["OA_CD"] == row["OA_CD"]].geometry.centroid.iloc[0].y,
         gdf[gdf["OA_CD"] == row["OA_CD"]].geometry.centroid.iloc[0].x,
         int(row["TOT_LVPOP_CO"])]
        for _, row in df.iterrows()
    ]
    HeatMap(heat_data, radius=25, max_zoom=15).add_to(m)

else:  # 타임 히트맵
    all_heat = []
    for h in range(24):
        df_h = fetch_data(date_str, f"{h:02d}")
        layer = [
            [
                gdf[gdf["OA_CD"] == row["OA_CD"]].geometry.centroid.iloc[0].y,
                gdf[gdf["OA_CD"] == row["OA_CD"]].geometry.centroid.iloc[0].x,
                int(row["TOT_LVPOP_CO"])
            ]
            for _, row in df_h.iterrows()
        ]
        all_heat.append(layer)
    HeatMapWithTime(
        all_heat,
        index=[f"{h:02d}" for h in range(24)],
        auto_play=False,
        max_opacity=0.8
    ).add_to(m)

# --------------------------------------------------
# 9. 대시보드 레이아웃
# --------------------------------------------------
st.title("🗺️ 성수동 단기체류 외국인 방문객 대시보드")
st.markdown(f"**기준일자:** {date_str}  **시간:** {hour_str}시  **시각화:** {viz_type}")

col1, col2 = st.columns((3, 1))
with col1:
    st_folium(m, width=800, height=600)
with col2:
    st.subheader("데이터 요약")
    st.write(f"총 레코드 수: {len(df)}")
    st.dataframe(
        df[[
            "STDR_DE_ID", "TMZON_PD_SE", "ADSTRD_CODE_SE",
            "OA_CD", "TOT_LVPOP_CO", "CHINA_STAYPOP_CO", "OTHER_STAYPOP_CO"
        ]]
    )

