import numpy as np
import pandas as pd
import re
import streamlit as st
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go

#Extracting dates from file names
def extract_date(filename):
    filename = str(filename)
    
    #For Pattern Type FY26_detentionStats12032025 
    m1 = re.search(r'(\d{2})(\d{2})(\d{4})\.xlsx$', filename)
    if not m1 and not filename.endswith('.xlsx'):
        m1 = re.search(r'(\d{2})(\d{2})(\d{4})$', filename)
    if m1:
        month, day, year = m1.groups()
        return f"{year}-{month}-{day}"

    #For Pattern Type: 20210113002029-FY21 
    m2 = re.match(r'^(\d{4})(\d{2})(\d{2})', filename)
    if m2:
        year, month, day = m2.groups()
        return f"{year}-{month}-{day}"
        
    return None







tech_list_raw = [ 'GPS', 'SmartLINK', 'TR', 'No Tech',
       'VeriWatch', 'Veriwatch', 'VoiceID', 'Dual Tech', 'Ankle Monitor',
       'Wristworn']

tech_mapping = {'Ankle Monitor': 'GPS',
'TR': 'VoiceID',
'Wristworn': 'VeriWatch'}

def getting_cleaned_tech_aor(df, tech_list):


    #Getting non tech values (AOR)
    df['aor_cleaned'] = np.where(~df['aor'].isin(tech_list), df['aor'], np.nan)

    #Forward filling AOR values
    df['aor_cleaned'] = df['aor_cleaned'].ffill()

    #Cleaning technology column 
    df['technology'] = np.where(df['aor'].isin(tech_list), df['aor'], np.nan)

    #Filtering out the 'Total' rows and section header rows to leave raw data
    df_cleaned = df[~df['technology'].isin(['Total', np.nan])].copy()

    #Cleaning tech values from old to new ones
    df_cleaned['tech_cleaned'] = df_cleaned['technology'].replace(tech_mapping).str.upper()

    return df_cleaned


def getting_monthly_data(df):
    df['year_month'] = df['date'].dt.to_period('M')
    df_monthly = df.groupby(['year_month', 'tech_cleaned', 'aor_cleaned'])['count'].mean().reset_index()
    df_monthly['date'] = df_monthly['year_month'].dt.to_timestamp()

    return df_monthly



# Helper function to add rectangular borders around subplots
def add_subplot_borders(fig, rows=3):
    shapes = []
    # Loop over each row's y-axis domain to draw border boxes
    for r in range(1, rows + 1):
        yaxis_name = f'yaxis{r}' if r > 1 else 'yaxis'
        y_domain = fig.layout[yaxis_name].domain
        shapes.append(
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0,
                x1=1,
                y0=y_domain[0] - 0.050,
                y1=y_domain[1] + 0.028,
                line=dict(color="#4A5568", width=1.5),
                fillcolor="rgba(0,0,0,0)"
            )
        )
    fig.update_layout(shapes=shapes)





@st.cache_data
def load_and_preprocess_data():
    atd = pd.read_csv("ATD_combined.csv")
    atd['date'] = pd.to_datetime(atd['filename'].apply(extract_date))
    atd['date_str'] = atd['date'].dt.strftime('%d-%m-%Y')

    atd_cleaned = getting_cleaned_tech_aor(atd, tech_list_raw)
    atd_monthly = getting_monthly_data(atd_cleaned)
    return atd_monthly






st.set_page_config(
    page_title="ATD Technology & AOR Dashboard",
    layout="wide"
)

st.title("ATD Monthly Analytics Dashboard")
# st.markdown("Analyze monthly trends, volume distribution, and MoM rate of growth by technology and AOR.")

#Loading Data
try:
    df_monthly = load_and_preprocess_data()
except Exception as e:
    st.error(f"Error loading ATD_combined.csv: {e}")
    st.stop()

#Sidebar









# --- Top Navigation Tabs ---
tab1, tab2 = st.tabs(["Technology", "Area Of Responsibility"])

# ==========================================
# TAB 1: TECH VIEW (Filter by Tech)
# ==========================================
with tab1:
    with st.form(key="tech_form"):
        col1, col2 = st.columns(2)
        with col1:
            available_techs = sorted(df_monthly['tech_cleaned'].unique().tolist())
            selected_tech = st.selectbox("Select Technology", available_techs)
        with col2:
            top_n = st.slider("Select Top N AORs by Volume", min_value=3, max_value=20, value=5)
            
        submit_tech = st.form_submit_button(label="Get Results", use_container_width=True)

    if submit_tech:
        df_tech = df_monthly[df_monthly['tech_cleaned'] == selected_tech].copy()

        if not df_tech.empty:
            top_n_aors = (
                df_tech.groupby('aor_cleaned')['count']
                .sum().nlargest(top_n).index.tolist()
            )
            df_tech['aor_grouped'] = df_tech['aor_cleaned'].apply(
                lambda x: x if x in top_n_aors else 'OTHERS'
            )

            df_grouped_monthly = (
                df_tech.groupby(['date', 'year_month', 'aor_grouped'])['count']
                .sum().reset_index().sort_values('date')
            )
            df_grouped_monthly['pct_change'] = (
                df_grouped_monthly.groupby('aor_grouped')['count'].pct_change() * 100
            )

            df_grouped_monthly['pct_change'] = (
                df_grouped_monthly['pct_change']
                .replace([np.inf, -np.inf], np.nan)
                .fillna(0)
            )

            total_tech_vol = df_grouped_monthly['count'].sum()
            summary_share = (
                df_grouped_monthly.groupby('aor_grouped')['count']
                .sum().reset_index().rename(columns={'count': 'Total_Count'})
            )
            summary_share['Percentage'] = (summary_share['Total_Count'] / total_tech_vol) * 100
            summary_share = summary_share.sort_values(by='Percentage', ascending=True)

            ordered_categories = top_n_aors + (['OTHERS'] if 'OTHERS' in df_tech['aor_grouped'].values else [])
            palette = px.colors.qualitative.Plotly
            color_map = {cat: palette[i % len(palette)] for i, cat in enumerate(top_n_aors)}
            color_map['OTHERS'] = '#7f7f7f'

            fig = make_subplots(
                rows=3, cols=1,
                row_heights=[0.36, 0.36, 0.28],
                subplot_titles=(
                    f"1. Monthly Mean Count For {selected_tech} — Top {top_n} AORs vs. OTHERS",
                    f"2. Monthly MoM % Change For {selected_tech}",
                    f"3. Total Volume % Share for {selected_tech}"
                ),
                vertical_spacing=0.12
            )

            for category in ordered_categories:
                cat_data = df_grouped_monthly[df_grouped_monthly['aor_grouped'] == category]
                fig.add_trace(
                    go.Scatter(
                        x=cat_data['date'], y=cat_data['count'], mode='lines+markers',
                        name=str(category), legendgroup=str(category),
                        line=dict(color=color_map[category], width=3 if category == 'OTHERS' else 2),
                        marker=dict(color=color_map[category])
                    ), row=1, col=1
                )
                fig.add_trace(
                    go.Scatter(
                        x=cat_data['date'], y=cat_data['pct_change'], mode='lines+markers',
                        name=str(category), legendgroup=str(category), showlegend=False,
                        line=dict(color=color_map[category], dash='dot'),
                        marker=dict(color=color_map[category])
                    ), row=2, col=1
                )

            for _, row in summary_share.iterrows():
                cat_val = row['aor_grouped']
                pct_val = row['Percentage']
                fig.add_trace(
                    go.Bar(
                        x=[pct_val], y=[str(cat_val)], orientation='h', name=str(cat_val),
                        legendgroup=str(cat_val), showlegend=False, text=[f"{pct_val:.1f}%"],
                        textposition='auto', marker=dict(color=color_map[cat_val])
                    ), row=3, col=1
                )

            fig.update_layout(
                height=1200, hovermode='x unified', margin=dict(t=60, b=40, l=40, r=40),
                legend=dict(title=dict(text="<b>AOR</b>"), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_xaxes(title_text="Date", row=1, col=1, showgrid=True)
            fig.update_yaxes(title_text="Mean Count", row=1, col=1, showgrid=True)
            fig.update_xaxes(title_text="Date", row=2, col=1, showgrid=True)
            fig.update_yaxes(title_text="% Change MoM", row=2, col=1, showgrid=True)
            
            max_pct = summary_share['Percentage'].max()
            fig.update_xaxes(title_text="% Share of Total Volume", range=[0, max_pct * 1.20], row=3, col=1, showgrid=True)
            fig.update_yaxes(title_text="AOR", row=3, col=1, showgrid=True)

            # Add borders around all 3 subplots
            add_subplot_borders(fig, rows=3)

            fig.update_layout(
                title=dict(
                    text=f"<b>{selected_tech} — Monthly Analytics Dashboard</b>",
                    font=dict(size=22, color="black"),
                    x=0.0,
                    xanchor="left"
                ),
                font=dict(size=13, color="black"),
                height=1200,
                hovermode='x unified',
                margin=dict(t=80, b=40, l=40, r=40),  # Increased top margin slightly to fit title nicely
                legend=dict(
                    title=dict(text="<b>AOR</b>", font=dict(size=13, color="black")),
                    font=dict(size=12, color="black"),
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )

            # 2. Update subplot title annotations to black without overwriting the main title
            for annotation in fig['layout']['annotations']:
                annotation.update(font=dict(size=15, color="black"))

            # Set subplot titles and all text annotations to black (font size 15)
            fig.for_each_annotation(lambda a: a.update(font=dict(size=15, color="black")))

            # Ensure x and y axis title and tick labels are black as well
            fig.update_xaxes(title_font=dict(color="black"), tickfont=dict(color="black"))
            fig.update_yaxes(title_font=dict(color="black"), tickfont=dict(color="black"))
            st.plotly_chart(fig, use_container_width=True)

            # --- Descriptions under Tab 1 Charts ---
            st.markdown("### Explanations")
            st.info(f"""
            * **Graph 1 (Monthly Mean Count):** This shows the average monthly count for **{selected_tech}** across the top {top_n} AORs along with aggregated baseline of all other remaining AORs.
            * **Graph 2 (Monthly MoM % Change):** This shows the month-over-month growth/decline rate percentage for top {top_n} AORs for **{selected_tech}**.
            * **Graph 3 (Total Volume % Share):** Shows the cumulative share of each top AOR for **{selected_tech}**.
            """)
        else:
            st.warning("No data found for this selection.")
    else:
        st.info("Select parameters above and click **Get Results**.")

# ==========================================
# TAB 2: AOR VIEW (Filter by AOR)
# ==========================================
with tab2:
    with st.form(key="aor_form"):
        available_aors = sorted(df_monthly['aor_cleaned'].unique().tolist())
        selected_aor = st.selectbox("Select Area of Responsibility (AOR)", available_aors)
        
        submit_aor = st.form_submit_button(label="Get Results", use_container_width=True)

    if submit_aor:
        df_aor = df_monthly[df_monthly['aor_cleaned'] == selected_aor].copy()

        if not df_aor.empty:
            df_aor_monthly = df_aor.sort_values('date')
            df_aor_monthly['pct_change'] = (
                df_aor_monthly.groupby('tech_cleaned')['count']
                .pct_change() * 100
            )

            total_aor_vol = df_aor['count'].sum()
            aor_tech_share = (
                df_aor.groupby('tech_cleaned')['count']
                .sum().reset_index().rename(columns={'count': 'Local_Count'})
            )
            aor_tech_share['Local_Percentage'] = (aor_tech_share['Local_Count'] / total_aor_vol) * 100
            aor_tech_share = aor_tech_share.sort_values(by='Local_Percentage', ascending=True)

            global_tech_totals = df_monthly.groupby('tech_cleaned')['count'].sum().to_dict()
            aor_tech_share['Global_Total'] = aor_tech_share['tech_cleaned'].map(global_tech_totals)
            aor_tech_share['Global_Share_Percentage'] = (aor_tech_share['Local_Count'] / aor_tech_share['Global_Total']) * 100

            tech_categories = sorted(df_aor['tech_cleaned'].unique().tolist())
            palette = px.colors.qualitative.Plotly
            color_map = {tech: palette[i % len(palette)] for i, tech in enumerate(tech_categories)}

            fig_aor = make_subplots(
                rows=4, cols=1,
                row_heights=[0.27, 0.27, 0.23, 0.23],
                subplot_titles=(
                    f"1. Monthly Count by Technology in {selected_aor}",
                    f"2. Monthly MoM % Growth Rate by Technology in {selected_aor}",
                    f"3. Technology % Share within {selected_aor}",
                    f"4. Total Technology % Share of {selected_aor}"
                ),
                vertical_spacing=0.09
            )

            # Subplot 1
            for tech in tech_categories:
                tech_data = df_aor_monthly[df_aor_monthly['tech_cleaned'] == tech]
                fig_aor.add_trace(
                    go.Scatter(
                        x=tech_data['date'], y=tech_data['count'], mode='lines+markers',
                        name=str(tech), legendgroup=str(tech),
                        line=dict(color=color_map[tech], width=2),
                        marker=dict(color=color_map[tech])
                    ), row=1, col=1
                )

            # Subplot 2
            for tech in tech_categories:
                tech_data = df_aor_monthly[df_aor_monthly['tech_cleaned'] == tech]
                fig_aor.add_trace(
                    go.Scatter(
                        x=tech_data['date'], y=tech_data['pct_change'], mode='lines+markers',
                        name=str(tech), legendgroup=str(tech), showlegend=False,
                        line=dict(color=color_map[tech], dash='dot'),
                        marker=dict(color=color_map[tech])
                    ), row=2, col=1
                )

            # Subplot 3
            for _, row in aor_tech_share.iterrows():
                tech_val = row['tech_cleaned']
                pct_val = row['Local_Percentage']
                fig_aor.add_trace(
                    go.Bar(
                        x=[pct_val], y=[str(tech_val)], orientation='h', name=str(tech_val),
                        legendgroup=str(tech_val), showlegend=False, text=[f"{pct_val:.1f}%"],
                        textposition='auto', marker=dict(color=color_map[tech_val])
                    ), row=3, col=1
                )

            # Subplot 4
            for _, row in aor_tech_share.iterrows():
                tech_val = row['tech_cleaned']
                global_pct = row['Global_Share_Percentage']
                fig_aor.add_trace(
                    go.Bar(
                        x=[global_pct], y=[str(tech_val)], orientation='h', name=str(tech_val),
                        legendgroup=str(tech_val), showlegend=False, text=[f"{global_pct:.1f}%"],
                        textposition='auto', marker=dict(color=color_map[tech_val], opacity=0.85)
                    ), row=4, col=1
                )

            fig_aor.update_layout(
                height=1400,
                hovermode='x unified',
                margin=dict(t=60, b=40, l=40, r=40),
                legend=dict(
                    title=dict(text="<b>Technology</b>"),
                    orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1
                )
            )

            fig_aor.update_xaxes(title_text="Date", row=1, col=1, showgrid=True)
            fig_aor.update_yaxes(title_text="Mean Count", row=1, col=1, showgrid=True)
            fig_aor.update_xaxes(title_text="Date", row=2, col=1, showgrid=True)
            fig_aor.update_yaxes(title_text="% Change MoM", row=2, col=1, showgrid=True)

            max_local_pct = aor_tech_share['Local_Percentage'].max()
            fig_aor.update_xaxes(title_text="% Internal Share", range=[0, max_local_pct * 1.20], row=3, col=1, showgrid=True)
            fig_aor.update_yaxes(title_text="Technology", row=3, col=1, showgrid=True)

            max_global_pct = aor_tech_share['Global_Share_Percentage'].max()
            fig_aor.update_xaxes(title_text="% Total Tech Volume of selected AOR", range=[0, max_global_pct * 1.25], row=4, col=1, showgrid=True)
            fig_aor.update_yaxes(title_text="Technology", row=4, col=1, showgrid=True)

            # Add borders around all 4 subplots
            add_subplot_borders(fig_aor, rows=4)

            st.plotly_chart(fig_aor, use_container_width=True)

            # --- Descriptions under Tab 2 Charts ---
            st.markdown("### Explanations")
            st.info(f"""
            * **Graph 1 (Monthly Count):** Shows monthly average counts for every technology in **{selected_aor}**.
            * **Graph 2 (MoM % Growth Rate):** Shows month-over-month percentage change per technology in **{selected_aor}**.
            * **Graph 3 (Technology % Share):** Shows the total technology share % in **{selected_aor}**.
            * **Graph 4 (Total Technology % Share):** Shows what percentage of each technology's overall volume is driven by **{selected_aor}**.
            """)

            # with st.expander("View AOR Processed Data Table"):
            #     st.dataframe(df_aor_monthly[['date', 'tech_cleaned', 'count', 'pct_change']], use_container_width=True)
        else:
            st.warning("No data found for this AOR.")
    else:
        st.info("Select an AOR above and click **Get Results**.")














# # --- Top Navigation Tabs ---
# tab1, tab2 = st.tabs(["Technology", "Area Of Responsibility"])

# # ==========================================
# # TAB 1: TECH VIEW (Filter by Tech)
# # ==========================================
# with tab1:
#     with st.form(key="tech_form"):
#         col1, col2 = st.columns(2)
#         with col1:
#             available_techs = sorted(df_monthly['tech_cleaned'].unique().tolist())
#             selected_tech = st.selectbox("Select Technology", available_techs)
#         with col2:
#             top_n = st.slider("Select Top N AORs by Volume", min_value=3, max_value=20, value=5)
            
#         submit_tech = st.form_submit_button(label="Get Results", use_container_width=True)

#     if submit_tech:
#         df_tech = df_monthly[df_monthly['tech_cleaned'] == selected_tech].copy()

#         if not df_tech.empty:
#             top_n_aors = (
#                 df_tech.groupby('aor_cleaned')['count']
#                 .sum().nlargest(top_n).index.tolist()
#             )
#             df_tech['aor_grouped'] = df_tech['aor_cleaned'].apply(
#                 lambda x: x if x in top_n_aors else 'OTHERS'
#             )

#             df_grouped_monthly = (
#                 df_tech.groupby(['date', 'year_month', 'aor_grouped'])['count']
#                 .sum().reset_index().sort_values('date')
#             )
#             df_grouped_monthly['pct_change'] = (
#                 df_grouped_monthly.groupby('aor_grouped')['count'].pct_change() * 100
#             )

#             total_tech_vol = df_grouped_monthly['count'].sum()
#             summary_share = (
#                 df_grouped_monthly.groupby('aor_grouped')['count']
#                 .sum().reset_index().rename(columns={'count': 'Total_Count'})
#             )
#             summary_share['Percentage'] = (summary_share['Total_Count'] / total_tech_vol) * 100
#             summary_share = summary_share.sort_values(by='Percentage', ascending=True)

#             ordered_categories = top_n_aors + (['OTHERS'] if 'OTHERS' in df_tech['aor_grouped'].values else [])
#             palette = px.colors.qualitative.Plotly
#             color_map = {cat: palette[i % len(palette)] for i, cat in enumerate(top_n_aors)}
#             color_map['OTHERS'] = '#7f7f7f'

#             fig = make_subplots(
#                 rows=3, cols=1,
#                 row_heights=[0.38, 0.38, 0.24],
#                 subplot_titles=(
#                     f"Monthly Mean Count For {selected_tech} — Top {top_n} AORs vs. OTHERS",
#                     f"Monthly MoM % Change For {selected_tech}",
#                     f"Total Volume % Share for {selected_tech}"
#                 ),
#                 vertical_spacing=0.09
#             )

#             for category in ordered_categories:
#                 cat_data = df_grouped_monthly[df_grouped_monthly['aor_grouped'] == category]
#                 fig.add_trace(
#                     go.Scatter(
#                         x=cat_data['date'], y=cat_data['count'], mode='lines+markers',
#                         name=str(category), legendgroup=str(category),
#                         line=dict(color=color_map[category], width=3 if category == 'OTHERS' else 2),
#                         marker=dict(color=color_map[category])
#                     ), row=1, col=1
#                 )
#                 fig.add_trace(
#                     go.Scatter(
#                         x=cat_data['date'], y=cat_data['pct_change'], mode='lines+markers',
#                         name=str(category), legendgroup=str(category), showlegend=False,
#                         line=dict(color=color_map[category], dash='dot'),
#                         marker=dict(color=color_map[category])
#                     ), row=2, col=1
#                 )

#             for _, row in summary_share.iterrows():
#                 cat_val = row['aor_grouped']
#                 pct_val = row['Percentage']
#                 fig.add_trace(
#                     go.Bar(
#                         x=[pct_val], y=[str(cat_val)], orientation='h', name=str(cat_val),
#                         legendgroup=str(cat_val), showlegend=False, text=[f"{pct_val:.1f}%"],
#                         textposition='auto', marker=dict(color=color_map[cat_val])
#                     ), row=3, col=1
#                 )

#             fig.update_layout(
#                 height=1100, hovermode='x unified', margin=dict(t=50, b=40, l=40, r=40),
#                 legend=dict(title=dict(text="<b>AOR</b>"), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
#             )
#             fig.update_xaxes(title_text="Date", row=1, col=1)
#             fig.update_yaxes(title_text="Mean Count", row=1, col=1)
#             fig.update_xaxes(title_text="Date", row=2, col=1)
#             fig.update_yaxes(title_text="% Change MoM", row=2, col=1)
            
#             max_pct = summary_share['Percentage'].max()
#             fig.update_xaxes(title_text="% Share of Total Volume", range=[0, max_pct * 1.20], row=3, col=1)
#             fig.update_yaxes(title_text="AOR", row=3, col=1)

#             st.plotly_chart(fig, use_container_width=True)
#         else:
#             st.warning("No data found for this selection.")
#     else:
#         st.info("Select parameters above and click **Get Results**.")

# # ==========================================
# # TAB 2: AOR VIEW (Filter by AOR)
# # ==========================================
# with tab2:
#     with st.form(key="aor_form"):
#         available_aors = sorted(df_monthly['aor_cleaned'].unique().tolist())
#         selected_aor = st.selectbox("Select Area of Responsibility (AOR)", available_aors)
        
#         submit_aor = st.form_submit_button(label="Get Results", use_container_width=True)

#     if submit_aor:
#         df_aor = df_monthly[df_monthly['aor_cleaned'] == selected_aor].copy()

#         if not df_aor.empty:
#             # 1. Monthly Counts & MoM % Change per Tech in this AOR
#             df_aor_monthly = df_aor.sort_values('date')
#             df_aor_monthly['pct_change'] = (
#                 df_aor_monthly.groupby('tech_cleaned')['count']
#                 .pct_change() * 100
#             )

#             # 2. Local Mix Share (% of this AOR's internal volume)
#             total_aor_vol = df_aor['count'].sum()
#             aor_tech_share = (
#                 df_aor.groupby('tech_cleaned')['count']
#                 .sum().reset_index().rename(columns={'count': 'Local_Count'})
#             )
#             aor_tech_share['Local_Percentage'] = (aor_tech_share['Local_Count'] / total_aor_vol) * 100
#             aor_tech_share = aor_tech_share.sort_values(by='Local_Percentage', ascending=True)

#             # 3. Global Tech Share (% of global total tech volume driven by this specific AOR)
#             global_tech_totals = df_monthly.groupby('tech_cleaned')['count'].sum().to_dict()
#             aor_tech_share['Global_Total'] = aor_tech_share['tech_cleaned'].map(global_tech_totals)
#             aor_tech_share['Global_Share_Percentage'] = (aor_tech_share['Local_Count'] / aor_tech_share['Global_Total']) * 100

#             tech_categories = sorted(df_aor['tech_cleaned'].unique().tolist())
#             palette = px.colors.qualitative.Plotly
#             color_map = {tech: palette[i % len(palette)] for i, tech in enumerate(tech_categories)}

#             # 4. Build 4 Subplots for AOR Analysis
#             fig_aor = make_subplots(
#                 rows=4, cols=1,
#                 row_heights=[0.30, 0.30, 0.20, 0.20],
#                 subplot_titles=(
#                     f"Monthly Count by Technology in {selected_aor}",
#                     f"Monthly MoM % Growth Rate by Technology in {selected_aor}",
#                     f"Technology % Share within {selected_aor}",
#                     f"Global Technology % Share of {selected_aor}"
#                 ),
#                 vertical_spacing=0.07
#             )

#             # Subplot 1: Monthly Volume Line Chart
#             for tech in tech_categories:
#                 tech_data = df_aor_monthly[df_aor_monthly['tech_cleaned'] == tech]
#                 fig_aor.add_trace(
#                     go.Scatter(
#                         x=tech_data['date'], y=tech_data['count'], mode='lines+markers',
#                         name=str(tech), legendgroup=str(tech),
#                         line=dict(color=color_map[tech], width=2),
#                         marker=dict(color=color_map[tech])
#                     ), row=1, col=1
#                 )

#             # Subplot 2: MoM % Change Line Chart
#             for tech in tech_categories:
#                 tech_data = df_aor_monthly[df_aor_monthly['tech_cleaned'] == tech]
#                 fig_aor.add_trace(
#                     go.Scatter(
#                         x=tech_data['date'], y=tech_data['pct_change'], mode='lines+markers',
#                         name=str(tech), legendgroup=str(tech), showlegend=False,
#                         line=dict(color=color_map[tech], dash='dot'),
#                         marker=dict(color=color_map[tech])
#                     ), row=2, col=1
#                 )

#             # Subplot 3: Local Mix Bar Chart (% of AOR)
#             for _, row in aor_tech_share.iterrows():
#                 tech_val = row['tech_cleaned']
#                 pct_val = row['Local_Percentage']
#                 fig_aor.add_trace(
#                     go.Bar(
#                         x=[pct_val], y=[str(tech_val)], orientation='h', name=str(tech_val),
#                         legendgroup=str(tech_val), showlegend=False, text=[f"{pct_val:.1f}%"],
#                         textposition='auto', marker=dict(color=color_map[tech_val])
#                     ), row=3, col=1
#                 )

#             # Subplot 4: Global Market Share Bar Chart (% of Worldwide Tech Total)
#             for _, row in aor_tech_share.iterrows():
#                 tech_val = row['tech_cleaned']
#                 global_pct = row['Global_Share_Percentage']
#                 fig_aor.add_trace(
#                     go.Bar(
#                         x=[global_pct], y=[str(tech_val)], orientation='h', name=str(tech_val),
#                         legendgroup=str(tech_val), showlegend=False, text=[f"{global_pct:.1f}%"],
#                         textposition='auto', marker=dict(color=color_map[tech_val], opacity=0.85)
#                     ), row=4, col=1
#                 )

#             fig_aor.update_layout(
#                 height=1300,
#                 hovermode='x unified',
#                 margin=dict(t=50, b=40, l=40, r=40),
#                 legend=dict(
#                     title=dict(text="<b>Technology</b>"),
#                     orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1
#                 )
#             )

#             # Axis Labels
#             fig_aor.update_xaxes(title_text="Date", row=1, col=1)
#             fig_aor.update_yaxes(title_text="Mean Count", row=1, col=1)

#             fig_aor.update_xaxes(title_text="Date", row=2, col=1)
#             fig_aor.update_yaxes(title_text="% Change MoM", row=2, col=1)

#             max_local_pct = aor_tech_share['Local_Percentage'].max()
#             fig_aor.update_xaxes(title_text="% Internal Share", range=[0, max_local_pct * 1.20], row=3, col=1)
#             fig_aor.update_yaxes(title_text="Technology", row=3, col=1)

#             max_global_pct = aor_tech_share['Global_Share_Percentage'].max()
#             fig_aor.update_xaxes(title_text="% Global Tech Volume Driven by this AOR", range=[0, max_global_pct * 1.25], row=4, col=1)
#             fig_aor.update_yaxes(title_text="Technology", row=4, col=1)

#             st.plotly_chart(fig_aor, use_container_width=True)

#             with st.expander("View AOR Processed Data Table"):
#                 st.dataframe(df_aor_monthly[['date', 'tech_cleaned', 'count', 'pct_change']], use_container_width=True)
#         else:
#             st.warning("No data found for this AOR.")
#     else:
#         st.info("Select an AOR above and click **Get Results**.")