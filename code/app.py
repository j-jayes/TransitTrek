import streamlit as st
import pandas as pd
import json
import plotly.express as px
import folium
from streamlit_folium import st_folium

# --- Data Loading ---
@st.cache_data
def load_data():
    with open('data/airports.json', 'r') as f:
        data = json.load(f)
    return data

data = load_data()

# --- Data Transformation: Flattening the transit options ---
rows = []
for airport in data['airports']:
    for option in airport['transit_options']:
        row = {
            "airport_name": airport["name"],
            "city": airport["city"],
            "distance_km": airport["distance_km"],
            "mode": option["mode"],
            "transit_type": option["transit_type"],
            "travel_time_minutes": option["travel_time_minutes"],
            "frequency": option["frequency"],
            "fare_euros": option["fare_euros"],
            "city_lat": airport["city_coords"]["lat"],
            "city_lon": airport["city_coords"]["lon"]
        }
        rows.append(row)
df = pd.DataFrame(rows)


def fare_difference_analysis(df):
    """
    Returns a DataFrame with columns:
      airport_name, city, min_fare, max_fare, fare_diff
    representing the difference between cheapest and most expensive fares per airport.
    """
    grouped = df.groupby(["airport_name", "city"], as_index=False).agg(
        min_fare=("fare_euros", "min"),
        max_fare=("fare_euros", "max")
    )
    grouped["fare_diff"] = grouped["max_fare"] - grouped["min_fare"]
    grouped.sort_values(by="fare_diff", ascending=False, inplace=True)
    return grouped


def taxi_price_per_km_analysis(df):
    """
    Filters only taxi rows, computes 'price_per_km' = fare_euros / distance_km,
    then aggregates by airport + city (in case of multiple taxi rows).
    Returns a DataFrame with columns:
      airport_name, city, distance_km, fare_euros, price_per_km
    """
    # Filter for taxi options
    df_taxi = df[df["transit_type"].str.lower() == "taxi"].copy()

    # Compute price per km (avoid division by zero)
    df_taxi["price_per_km"] = df_taxi["fare_euros"] / df_taxi["distance_km"]
    # Remove infinities or NaNs if distance=0 or missing
    df_taxi.replace([float("inf"), -float("inf")], float("nan"), inplace=True)
    df_taxi.dropna(subset=["price_per_km"], inplace=True)

    # Aggregate in case there are multiple taxi rows for one airport
    agg = df_taxi.groupby(["airport_name", "city"], as_index=False).agg(
        distance_km=("distance_km", "mean"),
        fare_euros=("fare_euros", "mean"),
        price_per_km=("price_per_km", "mean")
    )
    agg.sort_values(by="price_per_km", ascending=False, inplace=True)
    return agg

# --- Human-friendly labels for the axes ---
axis_options = {
    "Distance to City Center (km)": "distance_km",
    "Travel Time (min)": "travel_time_minutes",
    "Fare (Euros)": "fare_euros"
}

# --- App Info ---
st.title("European Airport Transit Options")
st.write(
    "This app displays transit options from a selection of European airports. "
    "The scatterplot shows the relationship between distance to city center, travel time, and fare. "
    "Click on a marker on the map to view the transit options for that airport."
)

# --- Create Tabs ---
tab1, tab2, tab3 = st.tabs(["Scatterplot and Map", "Analysis", "Data"])

with tab1:
    # st.header("Scatterplot and Map")

    # --- Axis selection in sidebar ---
    st.sidebar.header("Select Variables for Scatterplot")
    selected_x_label = st.sidebar.selectbox(
        "X-axis:",
        list(axis_options.keys()),
        index=list(axis_options.keys()).index("Distance to City Center (km)")
    )
    selected_y_label = st.sidebar.selectbox(
        "Y-axis:",
        list(axis_options.keys()),
        index=list(axis_options.keys()).index("Travel Time (min)")
    )

    x_axis = axis_options[selected_x_label]
    y_axis = axis_options[selected_y_label]

    # --- Scatterplot Section ---
    st.write("### Scatterplot of Transit Options")

    # We'll show all columns in the hover. We'll specify them in custom_data, then build a custom hovertemplate.
    # This includes everything from df that might be relevant:
    custom_data_cols = [
        "airport_name", "city", "distance_km", "mode",
        "transit_type", "travel_time_minutes", "frequency", "fare_euros"
    ]

    fig = px.scatter(
        df,
        x=x_axis,
        y=y_axis,
        color="transit_type",
        custom_data=custom_data_cols,
        title=f"Scatterplot: {selected_x_label} vs. {selected_y_label}"
    )

    # Define a hover template that references the custom_data array in order:
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]} – %{customdata[1]}</b><br>"   # airport_name – city
            "Distance: %{customdata[2]} km<br>"               # distance_km
            "Mode: %{customdata[3]}<br>"
            "Transit Type: %{customdata[4]}<br>"
            "Travel Time: %{customdata[5]} min<br>"
            "Frequency: %{customdata[6]}<br>"
            "Fare (€): %{customdata[7]}<br>"
            f"{selected_x_label}: %{{x}}<br>"
            f"{selected_y_label}: %{{y}}<extra></extra>"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- Map Section ---
    st.write("### Map of European Airports")
    st.write("Click on a marker to view the transit options for that airport.")
    
    m = folium.Map(location=[54, 15], zoom_start=4)
    
    # Use a dictionary to avoid duplicate markers per city
    airport_dict = {}
    for airport in data['airports']:
        city = airport["city"]
        if city not in airport_dict:
            city_coords = airport["city_coords"]
            # Build a neat HTML table for the popup
            table_html = """
            <style>
              table { width: 100%; border-collapse: collapse; }
              th, td { border: 1px solid #ddd; padding: 4px; text-align: center; }
              th { background-color: #f2f2f2; }
            </style>
            <table>
              <tr>
                <th>Mode</th>
                <th>Type</th>
                <th>Time (min)</th>
                <th>Fare (€)</th>
                <th>Freq.</th>
              </tr>
            """
            for option in airport["transit_options"]:
                table_html += f"""
                <tr>
                  <td>{option['mode']}</td>
                  <td>{option['transit_type']}</td>
                  <td>{option['travel_time_minutes']}</td>
                  <td>{option['fare_euros']}</td>
                  <td>{option['frequency']}</td>
                </tr>
                """
            table_html += "</table>"
            popup_html = f"<b>{airport['name']} - {city}</b><br>{table_html}"
            
            folium.Marker(
                location=[city_coords["lat"], city_coords["lon"]],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=airport["name"],
                icon=folium.Icon(icon="plane", prefix="fa") # Font Awesome plane icon
            ).add_to(m)
            airport_dict[city] = True

    st_data = st_folium(m, width=700)

with tab2:
    st.header("Analysis")

    # --- 1) Fare Difference Bar Chart ---
    analysis_df = fare_difference_analysis(df)

    st.subheader("Cheapest vs. Most Expensive Fare by Airport")
    st.write("Below is a table showing the cheapest and most expensive fares at each airport, plus the difference:")
    st.dataframe(analysis_df)

    top_airport = analysis_df.iloc[0]
    st.write(
        f"The **largest fare difference** is at **{top_airport['airport_name']}** in {top_airport['city']}, "
        f"where fares range from €{top_airport['min_fare']:.2f} to €{top_airport['max_fare']:.2f} "
        f"(a difference of €{top_airport['fare_diff']:.2f})."
    )

    # Create a bar chart for fare differences
    fig_diff = px.bar(
        analysis_df,
        x="airport_name",
        y="fare_diff",
        title="Difference Between Cheapest and Most Expensive Transit Fares (by Airport)"
    )
    # Add custom hover data
    # We'll attach city, min_fare, max_fare in customdata for a nicer tooltip
    fig_diff.update_traces(
        customdata=analysis_df[["city", "min_fare", "max_fare"]],
        hovertemplate=(
            "Airport: %{x}<br>"
            "City: %{customdata[0]}<br>"
            "Min Fare: €%{customdata[1]:.2f}<br>"
            "Max Fare: €%{customdata[2]:.2f}<br>"
            "Fare Difference: €%{y:.2f}<extra></extra>"
        )
    )
    st.plotly_chart(fig_diff, use_container_width=True)

    # --- 2) Taxi Price per Kilometer Bar Chart ---
    taxi_df = taxi_price_per_km_analysis(df)
    # Round the price per km to 2 decimal places
    taxi_df["price_per_km"] = taxi_df["price_per_km"].round(2)

    st.subheader("Taxi Price per Kilometer")
    st.write("How does the average taxi fare per kilometer compare across airports?")

    # Show results in a table
    st.dataframe(taxi_df)

    # Create a bar chart
    fig_taxi = px.bar(
        taxi_df,
        x="airport_name",
        y="price_per_km",
        title="Taxi Price per Kilometer by Airport"
    )
    fig_taxi.update_traces(
        customdata=taxi_df[["city", "distance_km", "fare_euros"]],
        hovertemplate=(
            "Airport: %{x}<br>"
            "City: %{customdata[0]}<br>"
            "Avg Distance: %{customdata[1]:.1f} km<br>"
            "Avg Taxi Fare: €%{customdata[2]:.2f}<br>"
            "Price per km: €%{y:.2f}<extra></extra>"
        )
    )
    st.plotly_chart(fig_taxi, use_container_width=True)


with tab3:
    st.header("Data")
    st.write("### Raw Airport Data (Sample)")
    st.write(data['airports'][:3])
    st.write("### Flattened Transit Options Data")
    st.write(df)
