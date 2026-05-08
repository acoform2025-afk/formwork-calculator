# app.py - Aluminum Formwork Detailed Calculator
# Assumes DXF is in MILLIMETERS (scale factor = 0.001)

import streamlit as st
import ezdxf
from ezdxf import units
import tempfile
import os
import math
import pandas as pd
import numpy as np
from shapely.geometry import LineString, Polygon, MultiLineString
from shapely.ops import polygonize, linemerge

st.set_page_config(page_title="Formwork Calculator", page_icon="📐")
st.title("📐 Aluminum Formwork – Detailed Area & Quote Calculator")
st.markdown("Upload a DXF floor plan (millimeters). The system extracts closed shapes and builds a detailed component table.")

# ------------------------------------------------------------------
# Extract closed polygons from DXF (works with lines, arcs, circles)
# ------------------------------------------------------------------
def extract_polygons_from_dxf(file_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        segments = []

        def add_seg(p1, p2):
            segments.append(LineString([(p1.x, p1.y), (p2.x, p2.y)]))

        # LINES
        for line in msp.query("LINE"):
            add_seg(line.dxf.start, line.dxf.end)

        # POLYLINES
        for poly in msp.query("LWPOLYLINE POLYLINE"):
            pts = []
            if poly.dxftype() == "LWPOLYLINE":
                pts = [(x, y) for x, y in poly.vertices()]
            else:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
            if len(pts) >= 2:
                for i in range(len(pts)-1):
                    segments.append(LineString([pts[i], pts[i+1]]))
                if poly.closed and len(pts) >= 3:
                    segments.append(LineString([pts[-1], pts[0]]))

        # ARCS (approximate by line segments)
        for arc in msp.query("ARC"):
            center = arc.dxf.center
            r = arc.dxf.radius
            sa = arc.dxf.start_angle
            ea = arc.dxf.end_angle
            num = max(4, int(abs(ea - sa) / 10))
            angles = np.linspace(sa, ea, num+1)
            pts = [(center.x + r*math.cos(np.radians(a)), center.y + r*math.sin(np.radians(a))) for a in angles]
            for i in range(len(pts)-1):
                segments.append(LineString([pts[i], pts[i+1]]))

        # CIRCLES
        for circ in msp.query("CIRCLE"):
            center = circ.dxf.center
            r = circ.dxf.radius
            num = 36
            angles = np.linspace(0, 360, num+1)
            pts = [(center.x + r*math.cos(np.radians(a)), center.y + r*math.sin(np.radians(a))) for a in angles]
            for i in range(len(pts)-1):
                segments.append(LineString([pts[i], pts[i+1]]))

        if not segments:
            return [], None

        merged = linemerge(MultiLineString(segments))
        polygons = list(polygonize(merged))
        return polygons, doc.units

    except Exception as e:
        st.error(f"DXF error: {e}")
        return [], None
    finally:
        os.unlink(tmp_path)


# ------------------------------------------------------------------
# Classify polygon based on aspect ratio and size
# ------------------------------------------------------------------
def classify_polygon(poly):
    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    l = maxy - miny
    if w > l:
        w, l = l, w
    aspect = l / w if w > 0 else 1

    if aspect < 1.5 and w < 2.0:       # small, square → column
        return "Column"
    elif aspect >= 3.0 and l > 2.0:    # long, thin → wall
        return "Wall"
    elif aspect >= 0.5 and l > 3.0:    # large, rectangular → slab
        return "Slab"
    else:
        return "Other"


# ------------------------------------------------------------------
# Main UI
# ------------------------------------------------------------------
mode = st.radio("Input mode", ["Manual entry (existing)", "DXF → Component Table (NEW)"])

if mode == "Manual entry (existing)":
    st.info("Manual mode works as before. Switch to DXF mode for automated component extraction.")
    # You can paste your old manual code here if needed

else:
    st.subheader("📂 Upload DXF Drawing (Millimeters)")
    uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])
    default_height = st.number_input("Default column/wall height (meters)", min_value=0.1, value=3.0, step=0.1)

    # Always assume millimeters unless user overrides
    use_mm = st.checkbox("Drawing is in millimeters (default: ON)", value=True)
    custom_scale = st.number_input("Custom scale (1 unit = ? meters). Leave 0 to auto-detect.", min_value=0.0, value=0.0, step=0.0001)

    if uploaded_file is not None:
        polygons, doc_units = extract_polygons_from_dxf(uploaded_file.getvalue())

        if not polygons:
            st.warning("No closed polygons found. The DXF may only contain open lines.")
        else:
            # Determine scale factor
            if custom_scale > 0:
                sf = custom_scale
                scale_desc = f"manual (1 unit = {sf} m)"
            elif use_mm:
                sf = 0.001
                scale_desc = "millimeters (assumed) → 0.001 m per unit"
            else:
                # Auto from DXF header
                if doc_units == units.M:
                    sf = 1.0
                    scale_desc = "meters"
                elif doc_units == units.CM:
                    sf = 0.01
                    scale_desc = "centimeters"
                elif doc_units == units.MM:
                    sf = 0.001
                    scale_desc = "millimeters"
                elif doc_units == units.INCH:
                    sf = 0.0254
                    scale_desc = "inches"
                else:
                    sf = 0.001
                    scale_desc = "unknown – assuming millimeters"

            st.info(f"Scale: 1 drawing unit = {sf*1000:.3f} mm → {sf} m")

            components = []
            for i, poly in enumerate(polygons):
                if poly.is_valid and poly.area > 1e-6:
                    typ = classify_polygon(poly)
                    # Get bounding box dimensions in meters
                    minx, miny, maxx, maxy = poly.bounds
                    w_m = (maxx - minx) * sf
                    l_m = (maxy - miny) * sf
                    # Ensure width <= length for consistency
                    if w_m > l_m:
                        w_m, l_m = l_m, w_m
                    perimeter_m = 2 * (w_m + l_m)

                    if typ in ("Column", "Wall"):
                        formwork_area = perimeter_m * default_height
                        height_val = default_height
                    elif typ == "Slab":
                        formwork_area = w_m * l_m
                        height_val = "N/A"
                    else:
                        formwork_area = poly.area * (sf ** 2)
                        height_val = "N/A"

                    components.append({
                        "SR.NO": i+1,
                        "TYPE": typ,
                        "NAME": f"{typ}_{i+1}",
                        "WIDTH (m)": round(w_m, 3),
                        "LENGTH (m)": round(l_m, 3),
                        "HEIGHT (m)": height_val if typ in ("Column","Wall") else "N/A",
                        "PERIMETER (m)": round(perimeter_m, 3) if typ in ("Column","Wall") else "-",
                        "AREA (m²)": round(formwork_area, 3)
                    })

            df = pd.DataFrame(components)
            st.success(f"Found {len(df)} closed areas. Scale: {scale_desc}")

            # Editable table
            st.subheader("📋 Component List – Edit as needed")
            edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

            # Total area
            total_area = edited_df["AREA (m²)"].sum()
            st.metric("Total Formwork Area (m²)", f"{total_area:,.2f}")

            # Price and quote
            price = st.number_input("Price per m² (USD)", min_value=0.0, value=45.0, step=5.0)
            if st.button("Generate Quote"):
                total_price = total_area * price
                st.success(f"💰 **Estimated Quote: ${total_price:,.2f} USD**")
                csv = edited_df.to_csv(index=False)
                st.download_button("Download Component List as CSV", data=csv, file_name="formwork_components.csv", mime="text/csv")