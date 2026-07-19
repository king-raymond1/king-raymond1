import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
import webbrowser
import threading
import time

# Page config
st.set_page_config(page_title='Sales Analytics Dashboard', layout='wide')

# Attempt to open browser automatically (runs in background so Streamlit can initialize)
def _open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open_new_tab('http://localhost:8501')
    except Exception:
        pass

threading.Thread(target=_open_browser, daemon=True).start()

# Helpers
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'analysis' / 'final_dataset'

@st.cache_data(ttl=600)
def _safe_read_csv(path: Path):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, parse_dates=True)
    except Exception:
        # fallback: try without parsing
        return pd.read_csv(path)

# Load datasets (graceful if missing)
fact_sales = _safe_read_csv(DATA_DIR / 'fact_sales.csv')
sales_by_day = _safe_read_csv(DATA_DIR / 'sales_by_day.csv')
sales_by_month = _safe_read_csv(DATA_DIR / 'sales_by_month.csv')
dim_products = _safe_read_csv(DATA_DIR / 'dim_products.csv')
dim_customers = _safe_read_csv(DATA_DIR / 'dim_customers.csv')
rfm_customers = _safe_read_csv(DATA_DIR / 'rfm_customers.csv')
abc_products = _safe_read_csv(DATA_DIR / 'abc_products.csv')
top_customers = _safe_read_csv(DATA_DIR / 'top_customers.csv')
top_products = _safe_read_csv(DATA_DIR / 'top_products.csv')

# Basic checks
if fact_sales.empty:
    st.warning('fact_sales.csv not found or empty in analysis/final_dataset. The dashboard will show limited data.\nPlease run scripts/prepare_analytical_dataset.py first.')

# Convert date columns where needed
for df, col in [(fact_sales, 'transaction_date'), (sales_by_day, 'date'), (sales_by_month, 'year_month')]:
    if not df.empty and col in df.columns:
        try:
            df[col] = pd.to_datetime(df[col])
        except Exception:
            pass

# Sidebar - filters & navigation
st.sidebar.title('Filters')
# Date filter
min_date = None
max_date = None
if not fact_sales.empty and 'transaction_date' in fact_sales.columns:
    min_date = fact_sales['transaction_date'].min().date()
    max_date = fact_sales['transaction_date'].max().date()
else:
    if not sales_by_day.empty and 'date' in sales_by_day.columns:
        min_date = sales_by_day['date'].min().date()
        max_date = sales_by_day['date'].max().date()

if min_date and max_date:
    date_range = st.sidebar.date_input('Transaction date range', value=(min_date, max_date), min_value=min_date, max_value=max_date)
else:
    date_range = None

# Product category filter
all_categories = []
if not dim_products.empty and 'category' in dim_products.columns:
    all_categories = sorted([c for c in dim_products['category'].fillna('Unknown').unique() if c!='' and str(c)!='nan'])
selected_categories = st.sidebar.multiselect('Product categories', options=all_categories, default=all_categories if len(all_categories)<=10 else [])

# Customer segment filter
all_segments = []
if not rfm_customers.empty and 'segment' in rfm_customers.columns:
    all_segments = sorted(rfm_customers['segment'].fillna('Unknown').unique())
selected_segments = st.sidebar.multiselect('Customer segment (RFM)', options=all_segments, default=all_segments)

# Region filter (store location)
all_stores = []
if not fact_sales.empty and 'store_location' in fact_sales.columns:
    all_stores = sorted([s for s in fact_sales['store_location'].fillna('Unknown').unique() if s!='' and str(s)!='nan'])
selected_stores = st.sidebar.multiselect('Store / Region', options=all_stores, default=all_stores)

st.sidebar.markdown('---')
st.sidebar.markdown('Streamlit + Plotly dashboard built by Senior Data Analyst')

# Apply filters to fact_sales
df = fact_sales.copy()
if not df.empty:
    # date filter
    if date_range and len(date_range) == 2:
        start, end = date_range
        start_dt = pd.to_datetime(start)
        # include end full day
        end_dt = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df = df[(df['transaction_date'] >= start_dt) & (df['transaction_date'] <= end_dt)]
    # category filter: map via product_key join
    if selected_categories and not dim_products.empty:
        prod_keys = dim_products[dim_products['category'].isin(selected_categories)]['product_key'].unique()
        df = df[df['product_key'].isin(prod_keys)]
    # store filter
    if selected_stores:
        df = df[df['store_location'].isin(selected_stores)]

# Customer segment filter: filter customers used in df
if selected_segments and not rfm_customers.empty:
    # get customers in selected segments
    sel_custs = rfm_customers[rfm_customers['segment'].isin(selected_segments)]['customer_id'].unique()
    if not df.empty:
        df = df[df['customer_id'].isin(sel_custs)]

# KPI calculations (handle empty dataframes)
if df.empty:
    total_revenue = 0.0
    total_orders = 0
    total_customers = 0
    avg_order_value = 0.0
    clv = 0.0
else:
    total_revenue = float(df['total_amount'].sum())
    total_orders = int(df['transaction_id'].nunique()) if 'transaction_id' in df.columns else int(len(df))
    total_customers = int(df['customer_id'].nunique()) if 'customer_id' in df.columns else 0
    avg_order_value = total_revenue / total_orders if total_orders>0 else 0.0
    # simplified CLV if available from dim_customers: mean customer total_revenue
    if not dim_customers.empty and 'total_revenue' in dim_customers.columns:
        clv = float(dim_customers['total_revenue'].mean())
    else:
        # fallback: avg revenue per customer
        clv = total_revenue / total_customers if total_customers>0 else 0.0

# Top KPIs
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric('Total Revenue', f"${total_revenue:,.2f}")
kpi2.metric('Total Orders', f"{total_orders:,}")
kpi3.metric('Total Customers', f"{total_customers:,}")
kpi4.metric('Average Order Value', f"${avg_order_value:,.2f}")
kpi5.metric('Customer Lifetime Value (est.)', f"${clv:,.2f}")

st.markdown('---')

# Layout: two columns for main charts
left_col, right_col = st.columns((2,1))

# Monthly Sales Trend (Plotly)
with left_col:
    st.subheader('Monthly Sales Trend')
    # prefer sales_by_month from final dataset, else compute from df
    if not sales_by_month.empty and 'year_month' in sales_by_month.columns:
        mb = sales_by_month.copy()
        try:
            mb['year_month'] = pd.to_datetime(mb['year_month'])
        except Exception:
            pass
        # filter months by date_range
        if date_range and len(date_range)==2:
            start, end = date_range
            mb = mb[(mb['year_month'] >= pd.to_datetime(start)) & (mb['year_month'] <= pd.to_datetime(end))]
        fig_m = px.line(mb, x='year_month', y='revenue', markers=True, title='Monthly Revenue')
        fig_m.update_layout(legend=dict(orientation='h'))
        st.plotly_chart(fig_m, use_container_width=True)
    elif not df.empty:
        tmp = df.copy()
        tmp['year_month'] = tmp['transaction_date'].dt.to_period('M').dt.to_timestamp()
        by_month = tmp.groupby('year_month').agg(revenue=('total_amount','sum')).reset_index()
        fig_m = px.line(by_month, x='year_month', y='revenue', markers=True, title='Monthly Revenue')
        st.plotly_chart(fig_m, use_container_width=True)
    else:
        st.info('No monthly sales data available.')

    # Rolling averages (7/30-day) - use sales_by_day or compute
    st.subheader('Daily Revenue & Rolling Averages')
    if not sales_by_day.empty and 'date' in sales_by_day.columns:
        sd = sales_by_day.copy()
        sd['date'] = pd.to_datetime(sd['date'])
        if date_range and len(date_range)==2:
            sd = sd[(sd['date'] >= pd.to_datetime(date_range[0])) & (sd['date'] <= pd.to_datetime(date_range[1]))]
        sd = sd.sort_values('date')
        sd['sma_7'] = sd['revenue'].rolling(7, min_periods=1).mean()
        sd['sma_30'] = sd['revenue'].rolling(30, min_periods=1).mean()
        fig_d = go.Figure()
        fig_d.add_trace(go.Scatter(x=sd['date'], y=sd['revenue'], mode='lines+markers', name='Daily Revenue', line=dict(color='royalblue')))
        fig_d.add_trace(go.Scatter(x=sd['date'], y=sd['sma_7'], mode='lines', name='7-day SMA', line=dict(color='orange')))
        fig_d.add_trace(go.Scatter(x=sd['date'], y=sd['sma_30'], mode='lines', name='30-day SMA', line=dict(color='green')))
        fig_d.update_layout(title='Daily Revenue with Rolling Averages', xaxis_title='Date', yaxis_title='Revenue')
        st.plotly_chart(fig_d, use_container_width=True)
    elif not df.empty:
        tmp = df.copy()
        tmp['date'] = tmp['transaction_date'].dt.date
        tmp = tmp.groupby('date').agg(revenue=('total_amount','sum')).reset_index()
        tmp['date'] = pd.to_datetime(tmp['date'])
        tmp = tmp.sort_values('date')
        tmp['sma_7'] = tmp['revenue'].rolling(7, min_periods=1).mean()
        fig_d = go.Figure()
        fig_d.add_trace(go.Scatter(x=tmp['date'], y=tmp['revenue'], mode='lines', name='Daily'))
        fig_d.add_trace(go.Scatter(x=tmp['date'], y=tmp['sma_7'], mode='lines', name='7-day SMA'))
        st.plotly_chart(fig_d, use_container_width=True)
    else:
        st.info('No daily sales data available.')

# Right column - Category & Top products
with right_col:
    st.subheader('Revenue by Category')
    if not dim_products.empty and 'category' in dim_products.columns:
        # merge product revenue
        prod = dim_products.copy()
        if 'total_revenue' not in prod.columns and not fact_sales.empty:
            prod = prod.merge(fact_sales.groupby('product_key').total_amount.sum().reset_index().rename(columns={'total_amount':'total_revenue'}), left_on='product_key', right_on='product_key', how='left')
        prod['total_revenue'] = prod['total_revenue'].fillna(0)
        if selected_categories:
            prod = prod[prod['category'].isin(selected_categories)]
        fig_cat = px.pie(prod.sort_values('total_revenue', ascending=False).head(20), names='category', values='total_revenue', title='Revenue by Category (top categories)')
        st.plotly_chart(fig_cat, use_container_width=True)
    elif not df.empty:
        cat_df = df.groupby('category').agg(revenue=('total_amount','sum')).reset_index().sort_values('revenue', ascending=False)
        fig_cat = px.pie(cat_df.head(20), names='category', values='revenue', title='Revenue by Category')
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info('No category data available.')

    st.subheader('Top 10 Products')
    if not top_products.empty:
        tp = top_products.copy()
        # ensure numeric revenue
        if 'total_revenue' not in tp.columns and 'units_sold' in tp.columns:
            tp['total_revenue'] = tp['units_sold']
        fig_tp = px.bar(tp.head(10), x='product_key' if 'product_key' in tp.columns else tp.columns[0], y='total_revenue' if 'total_revenue' in tp.columns else tp.columns[1], title='Top Products by Revenue')
        fig_tp.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_tp, use_container_width=True)
    elif not df.empty:
        prod_tmp = df.groupby('product_key').agg(revenue=('total_amount','sum')).reset_index().sort_values('revenue', ascending=False)
        fig_tp = px.bar(prod_tmp.head(10), x='product_key', y='revenue', title='Top Products by Revenue')
        fig_tp.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_tp, use_container_width=True)
    else:
        st.info('No product data available.')

st.markdown('---')

# Additional analysis: Top customers and RFM
st.subheader('Top Customers')
if not top_customers.empty:
    tc = top_customers.copy()
    fig_tc = px.bar(tc.head(10), x='customer_id', y='total_revenue', title='Top Customers by Revenue')
    fig_tc.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_tc, use_container_width=True)
elif not df.empty:
    cust_tmp = df.groupby('customer_id').agg(revenue=('total_amount','sum')).reset_index().sort_values('revenue', ascending=False)
    fig_tc = px.bar(cust_tmp.head(10), x='customer_id', y='revenue', title='Top Customers by Revenue')
    fig_tc.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_tc, use_container_width=True)
else:
    st.info('No customer data available.')

st.subheader('RFM Customer Segments')
if not rfm_customers.empty:
    rfm = rfm_customers.copy()
    # apply segment filter
    if selected_segments:
        rfm = rfm[rfm['segment'].isin(selected_segments)]
    seg_counts = rfm['segment'].value_counts().reset_index()
    seg_counts.columns = ['segment','count']
    fig_rfm = px.bar(seg_counts, x='segment', y='count', title='RFM Segment Counts', color='segment')
    st.plotly_chart(fig_rfm, use_container_width=True)
else:
    st.info('No RFM data available. Run the advanced analytics script to compute RFM.')

st.markdown('---')

# ABC Product classification
st.subheader('ABC Product Classification')
if not abc_products.empty:
    abc = abc_products.copy()
    if 'abc_class' not in abc.columns and 'cum_pct' in abc.columns:
        # compute class
        abc['abc_class'] = abc['cum_pct'].apply(lambda x: 'A' if x<=0.7 else ('B' if x<=0.9 else 'C'))
    class_counts = abc['abc_class'].value_counts().reset_index()
    class_counts.columns = ['abc_class','count']
    fig_abc = px.pie(class_counts, names='abc_class', values='count', title='ABC classes (product counts)')
    st.plotly_chart(fig_abc, use_container_width=True)
    # show top A products
    st.markdown('Top A-class products')
    if 'product_key' in abc.columns:
        top_a = abc[abc['abc_class']=='A'].sort_values('total_revenue', ascending=False).head(10)[['product_key','total_revenue']]
        st.dataframe(top_a)
else:
    st.info('No ABC product data available.')

st.markdown('---')

# Customer growth over time (unique customers monthly)
st.subheader('Customer Growth Over Time')
if not fact_sales.empty:
    tmp = fact_sales.copy()
    tmp['year_month'] = tmp['transaction_date'].dt.to_period('M').dt.to_timestamp()
    cust_growth = tmp.groupby('year_month').customer_id.nunique().reset_index().rename(columns={'customer_id':'unique_customers'})
    fig_cg = px.line(cust_growth, x='year_month', y='unique_customers', markers=True, title='Unique Customers per Month')
    st.plotly_chart(fig_cg, use_container_width=True)
else:
    st.info('No sales data to compute customer growth.')

st.markdown('---')

# Footer / data source info
st.caption('Data source: analysis/final_dataset (run scripts/prepare_analytical_dataset.py to regenerate).')

# End of app
