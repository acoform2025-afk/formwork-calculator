# app.py - Aluminum Formwork Calculator with Detailed Component Table

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
st.title("📐 Aluminum Formwork – Detailed Area Calculator")
st.markdown("Upload a DXF floor plan. The app will detect closed areas and list them like a bill of quantities.")

# ------------------------------------------------------------------
# Helper: extract all closed polygons from DXF
# ------------------------------------------------------------------
def extract_polygons_from_dxf(file_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        segments = []

        # Helper to add line segment
        def add_seg(p1, p2):
            segments.append(LineString([(p1.x, p1.y), (p2.x, p2.y)]))

        # 1. LINES
        for line in msp.query("LINE"):
            add_seg(line.dxf.start, line.dxf.end)

        # 2. POLYLINES / LWPOLYLINES
        for poly in msp.query("LWPOLYLINE POLYLINE"):
            points = []
            if poly.dxftype() == "LWPOLYLINE":
                points = [(x, y) for x, y in poly.vertices()]
            else:
                points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
            if len(points) >= 2:
                for i in range(len(points)-1):
                    segments.append(LineString([points[i], points[i+1]]))
                if poly.closed and len(points) >= 3:
                    segments.append(LineString([points[-1], points[0]]))

        # 3. ARCS (approximate by line segments)
        for arc in msp.query("ARC"):
            center = arc.dxf.center
            radius = arc.dxf.radius
            start_angle = arc.dxf.start_angle
            end_angle = arc.dxf.end_angle
            num_seg = max(4, int(abs(end_angle - start_angle) / 10))
            angles = np.linspace(start_angle, end_angle, num_seg+1)
            pts = [(center.x + radius*math.cos(np.radians(a)),
                    center.y + radius*math.sin(np.radians(a))) for a in angles]
            for i in range(len(pts)-1):
                segments.append(LineString([pts[i], pts[i+1]]))

        # 4. CIRCLES (polygon approximation)
        for circle in msp.query("CIRCLE"):
            center = circle.dxf.center
            radius = circle.dxf.radius
            num_seg = 36
            angles = np.linspace(0, 360, num_seg+1)
            pts = [(center.x + radius*math.cos(np.radians(a)),
                    center.y + radius*math.sin(np.radians(a))) for a in angles]
            for i in range(len(pts)-1):
                segments.append(LineString([pts[i], pts[i+1]]))

        if not segments:
            return [], None

        # Merge and polygonize
        merged = linemerge(MultiLineString(segments))
        polygons = list(polygonize(merged))
        # Remove tiny artifacts (area < 1e-6 after scaling will be filtered later)
        return polygons, doc.units

    except Exception as e:
        st.error(f"DXF parsing error: {e}")
        return [], None
    finally:
        os.unlink(tmp_path)


# ------------------------------------------------------------------
# Classify each polygon as Column / Wall / Slab / Other
# ------------------------------------------------------------------
def classify_polygon(poly, tol=0.1):
    minx, miny, maxx, maxy = poly.bounds
    width = abs(maxx - minx)
    length = abs(maxy - miny)
    # Sort so width <= length
    if width > length:
        width, length = length, width
    aspect = length / width if width > 0 else 1

    if aspect < 1.5 and width < 2.0:   # compact and small → column
        return "Column", width, length
    elif aspect >= 3.0 and length > 2.0:   # long thin → wall
        return "Wall", width, length
    elif aspect >= 0.5 and length > 3.0:   # large area → slab (or floor)
        return "Slab", width, length
    else:
        return "Other", width, length


# ------------------------------------------------------------------
# Main app
# ------------------------------------------------------------------
mode = st.radio("Input mode", ["Manual entry (as before)", "DXF → Detailed Table (New)"])

if mode == "Manual entry (as before)":
    # Keep your existing manual code (not shown here for brevity, but you can paste it)
    st.info("Manual mode works as before. Switch to DXF mode for detailed table.")

else:
    st.subheader("📂 Upload DXF Floor Plan")
    uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])
    height_default = st.number_input("Default column/wall height (meters)", min_value=0.1, value=3.0, step=0.1)
    scale_override = st.number_input("Scale factor (1 drawing unit = ? meters).\nLeave 0 to auto-detect, or set manually:\n0.001 for mm, 0.0254 for inches, 1 for meters",
                                     min_value=0.0, value=0.0, step=0.0001, format="%f")

    if uploaded_file is not None:
        polygons, doc_units = extract_polygons_from_dxf(uploaded_file.getvalue())

        if not polygons:
            st.warning("No closed polygons found. The DXF may contain only open lines.")
        else:
            # Determine scale factor
            if scale_override > 0:
                sf = scale_override
                unit_desc = f"manual (1 unit = {sf} m)"
            else:
                if doc_units == units.M:
                    sf = 1.0
                    unit_desc = "meters"
                elif doc_units == units.CM:
                    sf = 0.01
                    unit_desc = "centimeters"
                elif doc_units == units.MM:
                    sf = 0.001
                    unit_desc = "millimeters"
                elif doc_units == units.INCH:
                    sf = 0.0254
                    unit_desc = "inches"
                else:
                    sf = 1.0
                    unit_desc = "unknown (assuming meters) – adjust scale manually if needed"
                    st.warning(unit_desc)

            # Build component list
            components = []
            for i, poly in enumerate(polygons):
                if poly.is_valid and not poly.is_empty and poly.area > 1e-6:
                    typ, w, l = classify_polygon(poly)
                    # Convert drawing units to meters
                    w_m = w * sf
                    l_m = l * sf
                    area_2d = poly.area * (sf ** 2)   # horizontal area
                    # For formwork, we need perimeter * height for columns/walls
                    perimeter_m = (2 * (w_m + l_m))
                    # For columns/walls, formwork area = perimeter * height
                    # For slabs, just the bottom area
                    if typ in ("Column", "Wall"):
                        formwork_area = perimeter_m * height_default
                    elif typ == "Slab":
                        formwork_area = w_m * l_m   # bottom only
                    else:
                        formwork_area = area_2d      # fallback
                    components.append({
                        "SR.NO": i+1,
                        "TYPE": typ,
                        "NAME": f"{typ}_{i+1}",
                        "WIDTH (m)": round(w_m, 3),
                        "LENGTH (m)": round(l_m, 3),
                        "HEIGHT (m)": height_default if typ in ("Column","Wall") else "N/A",
                        "PERIMETER (m)": round(perimeter_m, 3) if typ in ("Column","Wall") else "-",
                        "AREA (m²)": round(formwork_area, 3)
                    })

            df = pd.DataFrame(components)
            st.success(f"Found {len(df)} closed areas. Scale: {unit_desc}")

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
                # Option to download as CSV
                csv = edited_df.to_csv(index=False)
                st.download_button("Download as CSV", data=csv, file_name="formwork_components.csv", mime="text/csv")