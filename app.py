import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os

# ============================================
# CONFIGURACIÓN DE LA PÁGINA
# ============================================
st.set_page_config(
    page_title="Cartera Algoritmos Genéticos",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# ESTILOS CSS
# ============================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #0ea5e9, #6366f1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 1rem;
        padding: 1.5rem;
        border: 1px solid #334155;
    }
    .positive { color: #10b981; }
    .negative { color: #ef4444; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f1f5f9;
        color: #1e293b;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0ea5e9, #6366f1);
        color: white;
    }
    /* Mejorar visibilidad del texto en pestañas */
    [data-testid="stMarkdownContainer"] {
        color: #1e293b;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# CONSTANTES
# ============================================
SYSTEMS = ['CEG', 'DGSE', 'DDG', 'EIR', 'Colossus']
DATA_FILE = 'portfolio_data.json'

# ============================================
# FUNCIONES DE DATOS
# ============================================
@st.cache_data(ttl=300)
def search_ticker(query: str) -> list:
    """Busca tickers en Yahoo Finance"""
    if len(query) < 1:
        return []
    try:
        import requests
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        results = []
        for quote in data.get('quotes', []):
            if quote.get('quoteType') in ['ETF', 'EQUITY', 'INDEX']:
                results.append({
                    'symbol': quote.get('symbol', ''),
                    'name': quote.get('shortname', quote.get('longname', '')),
                    'type': quote.get('quoteType', ''),
                    'exchange': quote.get('exchange', '')
                })
        return results
    except Exception as e:
        st.error(f"Error buscando: {e}")
        return []

@st.cache_data(ttl=60)
def get_quote(symbol: str, date: str = None) -> dict:
    """Obtiene cotización de Yahoo Finance para una fecha específica o actual"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if date:
            # Obtener precio de apertura para fecha específica
            start_date = datetime.strptime(date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1)
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                # Si no hay datos para esa fecha, buscar el día anterior más cercano
                hist = ticker.history(period="5d", end=end_date)
            
            if not hist.empty:
                current_price = hist['Open'].iloc[-1]  # Usar precio de apertura
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            else:
                return None
        else:
            # Precio actual
            hist = ticker.history(period="5d")
            if hist.empty:
                return None
            current_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        
        return {
            'symbol': symbol,
            'name': info.get('shortName', info.get('longName', symbol)),
            'price': current_price,
            'prev_close': prev_close,
            'change': current_price - prev_close,
            'change_pct': ((current_price - prev_close) / prev_close * 100) if prev_close else 0,
            'currency': info.get('currency', 'EUR'),
            'exchange': info.get('exchange', ''),
            'success': True
        }
    except Exception as e:
        return {'symbol': symbol, 'success': False, 'error': str(e)}

@st.cache_data(ttl=300)
def get_exchange_rate(date: str = None) -> float:
    """Obtiene tipo de cambio EUR/USD para una fecha específica o actual"""
    try:
        ticker = yf.Ticker("EURUSD=X")
        
        if date:
            start_date = datetime.strptime(date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1)
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                hist = ticker.history(period="5d", end=end_date)
            
            if not hist.empty:
                return hist['Open'].iloc[-1]  # Usar precio de apertura
        else:
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
    except:
        pass
    return 1.08

def load_data() -> dict:
    """Carga datos desde archivo JSON"""
    default_data = {
        'settings': {'capital': 15000},
        'etfs': {},
        'signals': {},
        'orders': [],
        'snapshots': []
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return default_data

def save_data(data: dict):
    """Guarda datos en archivo JSON"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def get_session_state():
    """Inicializa y devuelve el estado de la sesión"""
    if 'data' not in st.session_state:
        st.session_state.data = load_data()
    if 'exchange_rate' not in st.session_state:
        st.session_state.exchange_rate = get_exchange_rate()
    return st.session_state.data

# ============================================
# FUNCIONES DE CÁLCULO
# ============================================
def calculate_positions(data: dict) -> dict:
    """Calcula posiciones actuales basadas en órdenes"""
    positions = {}
    exchange_rate = st.session_state.get('exchange_rate', 1.08)
    
    # Ordenar por fecha
    sorted_orders = sorted(data['orders'], key=lambda x: x['date'])
    
    for order in sorted_orders:
        ticker = order['ticker']
        if ticker not in positions:
            positions[ticker] = {
                'units': 0,
                'total_cost': 0,
                'avg_price': 0,
                'current_price': 0,
                'market_value': 0,
                'pnl': 0,
                'pnl_pct': 0,
                'systems': []
            }
        
        pos = positions[ticker]
        
        if order['type'] == 'BUY':
            pos['total_cost'] += order['total']
            pos['units'] += order['units']
            if order.get('system'):
                for s in order['system'].split(', '):
                    if s and s not in pos['systems']:
                        pos['systems'].append(s)
        else:  # SELL
            if pos['units'] > 0:
                ratio = order['units'] / pos['units']
                pos['total_cost'] -= pos['total_cost'] * ratio
                pos['units'] -= order['units']
    
    # Calcular valores actuales
    for ticker, pos in list(positions.items()):
        if pos['units'] <= 0:
            del positions[ticker]
            continue
        
        # Obtener precio actual
        etf_data = data['etfs'].get(ticker, {})
        if etf_data.get('price'):
            price = etf_data['price']
            currency = etf_data.get('currency', 'EUR')
            if currency == 'USD':
                price = price / exchange_rate
            elif currency == 'GBP':
                price = price * 1.17
            pos['current_price'] = price
        else:
            pos['current_price'] = pos['total_cost'] / pos['units'] if pos['units'] > 0 else 0
        
        pos['avg_price'] = pos['total_cost'] / pos['units'] if pos['units'] > 0 else 0
        pos['market_value'] = pos['units'] * pos['current_price']
        pos['pnl'] = pos['market_value'] - pos['total_cost']
        pos['pnl_pct'] = (pos['pnl'] / pos['total_cost'] * 100) if pos['total_cost'] > 0 else 0
    
    return positions

def calculate_allocation(data: dict, month: int, year: int) -> dict:
    """Calcula asignación basada en señales"""
    key = f"{year}-{month}"
    signals = data['signals'].get(key, {})
    capital = data['settings']['capital']
    exchange_rate = st.session_state.get('exchange_rate', 1.08)
    
    allocation = {}
    cap_per_system = capital / len(SYSTEMS)
    
    for system in SYSTEMS:
        sys_signals = signals.get(system, {'buy': [], 'hold': [], 'sell': []})
        active_etfs = sys_signals.get('buy', []) + sys_signals.get('hold', [])
        
        if not active_etfs:
            continue
        
        cap_per_etf = cap_per_system / len(active_etfs)
        
        for ticker in active_etfs:
            etf_data = data['etfs'].get(ticker, {})
            price = etf_data.get('price', 0)
            currency = etf_data.get('currency', 'EUR')
            
            # Convertir a EUR
            price_eur = price
            if currency == 'USD' and price > 0:
                price_eur = price / exchange_rate
            elif currency == 'GBP' and price > 0:
                price_eur = price * 1.17
            
            units = int(cap_per_etf / price_eur) if price_eur > 0 else 0
            
            if ticker not in allocation:
                allocation[ticker] = {
                    'systems': [],
                    'total_capital': 0,
                    'price': price,
                    'price_eur': price_eur,
                    'currency': currency,
                    'total_units': 0,
                    'weight': 0,
                    'name': etf_data.get('name', ticker)
                }
            
            allocation[ticker]['systems'].append(system)
            allocation[ticker]['total_capital'] += cap_per_etf
    
    # Recalcular unidades consolidadas
    for ticker, item in allocation.items():
        if item['price_eur'] > 0:
            item['total_units'] = int(item['total_capital'] / item['price_eur'])
        item['weight'] = (item['total_capital'] / capital * 100)
    
    return allocation

def calculate_stats(data: dict, positions: dict) -> dict:
    """Calcula estadísticas del portfolio"""
    capital = data['settings']['capital']
    
    total_value = 0
    total_invested = 0
    
    for pos in positions.values():
        total_value += pos['market_value']
        total_invested += pos['total_cost']
    
    cash = max(0, capital - total_invested)
    pnl = total_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
    
    return {
        'total_value': total_value + cash,
        'total_invested': total_invested,
        'cash': cash,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'num_positions': len(positions)
    }

# ============================================
# COMPONENTES UI
# ============================================
def render_metric_card(title: str, value: str, delta: str = None, delta_color: str = "normal"):
    """Renderiza una tarjeta de métrica"""
    st.metric(label=title, value=value, delta=delta, delta_color=delta_color)

def render_header():
    """Renderiza el header de la aplicación"""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown('<p class="main-header">🧬 Cartera Algoritmos Genéticos</p>', unsafe_allow_html=True)
        st.caption("Gestión de cartera multi-sistema con datos de Yahoo Finance")
    
    with col2:
        rate = st.session_state.get('exchange_rate', 1.08)
        st.metric("EUR/USD", f"{rate:.4f}")
    
    with col3:
        data = get_session_state()
        st.metric("Capital", f"{data['settings']['capital']:,.0f} €")

# ============================================
# PÁGINAS
# ============================================
def page_dashboard():
    """Página principal - Dashboard"""
    data = get_session_state()
    positions = calculate_positions(data)
    stats = calculate_stats(data, positions)
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "💰 Valor Total",
            f"{stats['total_value']:,.2f} €",
            f"{stats['pnl_pct']:+.2f}%" if stats['total_invested'] > 0 else None,
            delta_color="normal" if stats['pnl'] >= 0 else "inverse"
        )
    
    with col2:
        color = "normal" if stats['pnl'] >= 0 else "inverse"
        st.metric(
            "📊 P&L Total",
            f"{stats['pnl']:+,.2f} €",
            f"Invertido: {stats['total_invested']:,.0f} €",
            delta_color=color
        )
    
    with col3:
        st.metric(
            "💵 Liquidez",
            f"{stats['cash']:,.2f} €",
            f"{(stats['cash']/data['settings']['capital']*100):.1f}% del capital"
        )
    
    with col4:
        st.metric(
            "📦 Posiciones",
            stats['num_positions'],
            f"{len(data['orders'])} órdenes"
        )
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Evolución del Portfolio")
        
        if data['snapshots']:
            df_snapshots = pd.DataFrame(data['snapshots'])
            df_snapshots['date'] = pd.to_datetime(df_snapshots['date'])
            
            fig = px.line(
                df_snapshots, x='date', y='total_value',
                labels={'date': 'Fecha', 'total_value': 'Valor (€)'},
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#94a3b8',
                showlegend=False
            )
            fig.update_traces(line_color='#0ea5e9', fill='tozeroy', fillcolor='rgba(14,165,233,0.1)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay snapshots guardados. Usa el botón 'Guardar Snapshot' para empezar a trackear la evolución.")
            if st.button("📸 Guardar Snapshot"):
                data['snapshots'].append({
                    'date': datetime.now().isoformat(),
                    'total_value': stats['total_value'],
                    'total_invested': stats['total_invested'],
                    'pnl': stats['pnl']
                })
                save_data(data)
                st.rerun()
    
    with col2:
        st.subheader("🎯 Distribución por Sistema")
        
        if positions:
            system_values = {s: 0 for s in SYSTEMS}
            for pos in positions.values():
                for sys in pos['systems']:
                    if sys in system_values:
                        system_values[sys] += pos['market_value'] / len(pos['systems'])
            
            # Añadir capital no invertido
            for sys in SYSTEMS:
                if system_values[sys] == 0:
                    system_values[sys] = data['settings']['capital'] / len(SYSTEMS)
            
            fig = px.pie(
                values=list(system_values.values()),
                names=list(system_values.keys()),
                hole=0.6,
                color_discrete_sequence=['#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444']
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#94a3b8',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay posiciones para mostrar distribución.")
    
    # Tabla de posiciones
    st.subheader("📋 Posiciones Actuales")
    
    if positions:
        pos_data = []
        for ticker, pos in positions.items():
            etf_info = data['etfs'].get(ticker, {})
            pos_data.append({
                'Ticker': ticker,
                'Nombre': etf_info.get('name', ticker)[:40],
                'Unidades': pos['units'],
                'P. Medio': f"{pos['avg_price']:.2f} €",
                'P. Actual': f"{pos['current_price']:.2f} €",
                'Valor': f"{pos['market_value']:.2f} €",
                'P&L': f"{pos['pnl']:+.2f} €",
                'P&L %': f"{pos['pnl_pct']:+.2f}%",
                'Sistemas': ', '.join(pos['systems'])
            })
        
        df = pd.DataFrame(pos_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay posiciones en cartera. Registra órdenes para comenzar.")

def page_signals():
    """Página de gestión de señales"""
    data = get_session_state()
    
    st.subheader("📊 Gestión de Señales Mensuales")
    
    # Selector de mes/año
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        month = st.selectbox(
            "Mes",
            range(1, 13),
            format_func=lambda x: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][x-1],
            index=datetime.now().month - 1
        )
    
    with col2:
        year = st.selectbox("Año", range(2024, 2031), index=datetime.now().year - 2024)
    
    key = f"{year}-{month}"
    if key not in data['signals']:
        data['signals'][key] = {sys: {'buy': [], 'hold': [], 'sell': []} for sys in SYSTEMS}
    
    # Buscador de ETFs
    st.markdown("---")
    st.subheader("🔍 Buscar ETF en Yahoo Finance")
    
    search_query = st.text_input("Buscar ticker (ej: CSPX, IWDA, VWCE, AAPL...)", key="signal_search")
    
    if search_query:
        with st.spinner("Buscando..."):
            results = search_ticker(search_query)
        
        if results:
            st.write("**Resultados:**")
            for result in results[:8]:
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.code(result['symbol'])
                with col2:
                    st.caption(f"{result['name'][:50]} ({result['exchange']})")
                with col3:
                    if st.button("➕", key=f"add_{result['symbol']}"):
                        # Obtener datos del ETF
                        quote = get_quote(result['symbol'])
                        if quote and quote.get('success'):
                            data['etfs'][result['symbol']] = {
                                'yahooSymbol': result['symbol'],
                                'name': quote['name'],
                                'price': quote['price'],
                                'currency': quote['currency'],
                                'change_pct': quote['change_pct']
                            }
                            save_data(data)
                            st.success(f"✅ {result['symbol']} añadido")
                            st.rerun()
                        else:
                            st.error("Error obteniendo datos")
        elif search_query:
            st.warning("No se encontraron resultados")
    
    st.markdown("---")
    
    # Grid de sistemas
    for i in range(0, len(SYSTEMS), 2):
        cols = st.columns(2)
        
        for j, col in enumerate(cols):
            if i + j < len(SYSTEMS):
                system = SYSTEMS[i + j]
                
                with col:
                    st.markdown(f"### 🎯 {system}")
                    
                    sys_signals = data['signals'][key].get(system, {'buy': [], 'hold': [], 'sell': []})
                    
                    # COMPRAR
                    st.markdown("**🟢 COMPRAR**")
                    buy_options = list(data['etfs'].keys())
                    current_buy = [t for t in sys_signals.get('buy', []) if t in buy_options]
                    new_buy = st.multiselect(
                        "ETFs a comprar",
                        options=buy_options,
                        default=current_buy,
                        key=f"buy_{system}_{key}",
                        label_visibility="collapsed"
                    )
                    
                    # MANTENER
                    st.markdown("**🟡 MANTENER**")
                    current_hold = [t for t in sys_signals.get('hold', []) if t in buy_options]
                    new_hold = st.multiselect(
                        "ETFs a mantener",
                        options=buy_options,
                        default=current_hold,
                        key=f"hold_{system}_{key}",
                        label_visibility="collapsed"
                    )
                    
                    # VENDER
                    st.markdown("**🔴 VENDER**")
                    current_sell = [t for t in sys_signals.get('sell', []) if t in buy_options]
                    new_sell = st.multiselect(
                        "ETFs a vender",
                        options=buy_options,
                        default=current_sell,
                        key=f"sell_{system}_{key}",
                        label_visibility="collapsed"
                    )
                    
                    # Actualizar signals
                    data['signals'][key][system] = {
                        'buy': new_buy,
                        'hold': new_hold,
                        'sell': new_sell
                    }
                    
                    st.markdown("---")
    
    # Botón guardar
    if st.button("💾 Guardar Señales", type="primary", use_container_width=True):
        save_data(data)
        st.success("✅ Señales guardadas correctamente")

def page_allocation():
    """Página de asignación calculada"""
    data = get_session_state()
    
    st.subheader("📊 Asignación Calculada")
    
    # Selector de mes
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        month = st.selectbox(
            "Mes",
            range(1, 13),
            format_func=lambda x: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                                   'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'][x-1],
            index=datetime.now().month - 1,
            key="alloc_month"
        )
    
    with col2:
        year = st.selectbox("Año", range(2024, 2031), index=datetime.now().year - 2024, key="alloc_year")
    
    with col3:
        st.metric("Capital", f"{data['settings']['capital']:,.0f} €")
    
    with col4:
        st.metric("Por Sistema", f"{data['settings']['capital']/5:,.0f} €")
    
    # Calcular asignación
    allocation = calculate_allocation(data, month, year)
    
    if allocation:
        st.markdown("---")
        st.subheader("📋 Asignación Consolidada por ETF")
        
        alloc_data = []
        for ticker, item in allocation.items():
            alloc_data.append({
                'Ticker': ticker,
                'Nombre': item['name'][:35] if item['name'] else ticker,
                'Capital': f"{item['total_capital']:,.2f} €",
                'Precio': f"{item['price_eur']:.2f} €",
                'Unidades': item['total_units'],
                'Peso': f"{item['weight']:.1f}%",
                'Sistemas': ', '.join(item['systems']),
                'Moneda': item['currency']
            })
        
        df = pd.DataFrame(alloc_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Botones de acción rápida
        st.markdown("---")
        st.subheader("⚡ Registro Rápido de Compras")
        
        for ticker, item in allocation.items():
            if item['total_units'] > 0:
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                
                with col1:
                    st.write(f"**{ticker}** - {item['name'][:25]}")
                
                with col2:
                    st.write(f"{item['total_units']} uds")
                
                with col3:
                    st.write(f"{item['price_eur']:.2f} €")
                
                with col4:
                    st.write(f"{item['total_units'] * item['price_eur']:.2f} €")
                
                with col5:
                    if st.button("Comprar", key=f"buy_alloc_{ticker}"):
                        order = {
                            'id': int(datetime.now().timestamp() * 1000),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'type': 'BUY',
                            'ticker': ticker,
                            'units': item['total_units'],
                            'price': round(item['price_eur'], 2),
                            'total': round(item['total_units'] * item['price_eur'], 2),
                            'system': ', '.join(item['systems'])
                        }
                        data['orders'].insert(0, order)
                        save_data(data)
                        st.success(f"✅ Compra de {item['total_units']} {ticker} registrada")
                        st.rerun()
    else:
        st.info("No hay señales cargadas para este mes. Ve a la pestaña 'Señales' para añadirlas.")

def page_orders():
    """Página de registro de órdenes"""
    data = get_session_state()
    
    st.subheader("📝 Registro de Órdenes")
    
    # Formulario nueva orden
    with st.expander("➕ Nueva Orden", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            order_type = st.radio("Tipo", ["BUY", "SELL"], horizontal=True)
        
        with col2:
            order_date = st.date_input("Fecha", datetime.now(), key="order_date_input")
        
        # Buscador de ticker
        search = st.text_input("🔍 Buscar ETF/Acción", key="order_search")
        
        selected_ticker = None
        selected_price = 0.0
        order_date_str = order_date.strftime('%Y-%m-%d')
        
        if search:
            results = search_ticker(search)
            if results:
                options = [f"{r['symbol']} - {r['name'][:30]}" for r in results[:5]]
                selected = st.selectbox("Seleccionar", options, key="order_select")
                if selected:
                    selected_ticker = selected.split(" - ")[0]
                    
                    # Obtener precio para la fecha seleccionada
                    with st.spinner("Obteniendo precio..."):
                        quote = get_quote(selected_ticker, order_date_str)
                        # Obtener tipo de cambio para esa fecha
                        date_exchange_rate = get_exchange_rate(order_date_str)
                    
                    if quote and quote.get('success'):
                        # Guardar ETF en la base de datos
                        data['etfs'][selected_ticker] = {
                            'yahooSymbol': selected_ticker,
                            'name': quote['name'],
                            'price': quote['price'],
                            'currency': quote['currency'],
                            'change_pct': quote.get('change_pct', 0)
                        }
                        
                        # Convertir precio a EUR
                        price = quote['price']
                        if quote['currency'] == 'USD':
                            price = price / date_exchange_rate
                        elif quote['currency'] == 'GBP':
                            price = price * 1.17
                        selected_price = price
                        
                        st.info(f"💰 Precio apertura {order_date_str}: {quote['price']:.2f} {quote['currency']} = {price:.2f} € | EUR/USD: {date_exchange_rate:.4f}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            units = st.number_input("Unidades", min_value=1, value=1)
        
        with col2:
            price = st.number_input("Precio (€)", min_value=0.01, value=selected_price if selected_price > 0 else 100.0, format="%.2f")
        
        with col3:
            system = st.selectbox("Sistema (opcional)", [""] + SYSTEMS)
        
        total = units * price
        st.metric("Total", f"{total:,.2f} €")
        
        if st.button("✅ Registrar Orden", type="primary", disabled=not selected_ticker):
            order = {
                'id': int(datetime.now().timestamp() * 1000),
                'date': order_date_str,
                'type': order_type,
                'ticker': selected_ticker,
                'units': units,
                'price': round(price, 2),
                'total': round(total, 2),
                'system': system
            }
            data['orders'].insert(0, order)
            save_data(data)
            st.success(f"✅ Orden de {order_type} registrada: {units} {selected_ticker} @ {price:.2f} €")
            st.rerun()
    
    # Resumen
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    total_bought = sum(o['total'] for o in data['orders'] if o['type'] == 'BUY')
    total_sold = sum(o['total'] for o in data['orders'] if o['type'] == 'SELL')
    
    with col1:
        st.metric("🟢 Total Comprado", f"{total_bought:,.2f} €")
    with col2:
        st.metric("🔴 Total Vendido", f"{total_sold:,.2f} €")
    with col3:
        st.metric("📊 Neto Invertido", f"{total_bought - total_sold:,.2f} €")
    
    # Tabla de órdenes
    st.markdown("---")
    st.subheader("📋 Historial de Órdenes")
    
    if data['orders']:
        orders_df = []
        for i, order in enumerate(data['orders']):
            orders_df.append({
                'Fecha': order['date'],
                'Tipo': '🟢 COMPRA' if order['type'] == 'BUY' else '🔴 VENTA',
                'Ticker': order['ticker'],
                'Unidades': order['units'],
                'Precio': f"{order['price']:.2f} €",
                'Total': f"{order['total']:.2f} €",
                'Sistema': order.get('system', '-'),
                'ID': i
            })
        
        df = pd.DataFrame(orders_df)
        
        # Mostrar tabla con opción de eliminar
        for i, row in df.iterrows():
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.2, 1, 1, 0.8, 1, 1, 1, 0.5])
            
            with col1:
                st.write(row['Fecha'])
            with col2:
                st.write(row['Tipo'])
            with col3:
                st.write(row['Ticker'])
            with col4:
                st.write(row['Unidades'])
            with col5:
                st.write(row['Precio'])
            with col6:
                st.write(row['Total'])
            with col7:
                st.write(row['Sistema'])
            with col8:
                if st.button("🗑️", key=f"del_order_{row['ID']}"):
                    data['orders'].pop(row['ID'])
                    save_data(data)
                    st.rerun()
    else:
        st.info("No hay órdenes registradas.")

def page_portfolio():
    """Página de cartera"""
    data = get_session_state()
    positions = calculate_positions(data)
    
    st.subheader("💼 Cartera Actual")
    
    # Botón actualizar precios
    if st.button("🔄 Actualizar Precios", type="primary"):
        with st.spinner("Actualizando precios..."):
            st.session_state.exchange_rate = get_exchange_rate()
            
            for ticker in data['etfs'].keys():
                quote = get_quote(ticker)
                if quote and quote.get('success'):
                    data['etfs'][ticker].update({
                        'price': quote['price'],
                        'currency': quote['currency'],
                        'change_pct': quote.get('change_pct', 0),
                        'name': quote['name']
                    })
            
            save_data(data)
            st.success("✅ Precios actualizados")
            st.rerun()
    
    st.markdown("---")
    
    if positions:
        # Tabla de posiciones
        for ticker, pos in positions.items():
            etf_info = data['etfs'].get(ticker, {})
            
            with st.container():
                col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1, 1, 1, 1.2, 1.2, 1])
                
                with col1:
                    st.write(f"**{ticker}**")
                    st.caption(etf_info.get('name', '')[:30])
                
                with col2:
                    st.metric("Unidades", pos['units'])
                
                with col3:
                    st.metric("P. Medio", f"{pos['avg_price']:.2f} €")
                
                with col4:
                    st.metric("P. Actual", f"{pos['current_price']:.2f} €")
                
                with col5:
                    st.metric("Valor", f"{pos['market_value']:.2f} €")
                
                with col6:
                    color = "normal" if pos['pnl'] >= 0 else "inverse"
                    st.metric("P&L", f"{pos['pnl']:+.2f} €", f"{pos['pnl_pct']:+.2f}%", delta_color=color)
                
                with col7:
                    if st.button("Vender", key=f"sell_{ticker}"):
                        st.session_state.selling_ticker = ticker
                        st.session_state.selling_pos = pos
                
                st.markdown("---")
        
        # Modal de venta
        if hasattr(st.session_state, 'selling_ticker') and st.session_state.selling_ticker:
            ticker = st.session_state.selling_ticker
            pos = st.session_state.selling_pos
            
            st.warning(f"📤 Vender {ticker}")
            
            col1, col2 = st.columns(2)
            with col1:
                sell_units = st.number_input("Unidades a vender", min_value=1, max_value=pos['units'], value=pos['units'])
            with col2:
                sell_price = st.number_input("Precio (€)", min_value=0.01, value=pos['current_price'], format="%.2f")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Confirmar Venta", type="primary"):
                    order = {
                        'id': int(datetime.now().timestamp() * 1000),
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'type': 'SELL',
                        'ticker': ticker,
                        'units': sell_units,
                        'price': round(sell_price, 2),
                        'total': round(sell_units * sell_price, 2),
                        'system': ''
                    }
                    data['orders'].insert(0, order)
                    save_data(data)
                    del st.session_state.selling_ticker
                    del st.session_state.selling_pos
                    st.success(f"✅ Venta registrada")
                    st.rerun()
            
            with col2:
                if st.button("❌ Cancelar"):
                    del st.session_state.selling_ticker
                    del st.session_state.selling_pos
                    st.rerun()
    else:
        st.info("No hay posiciones en cartera.")

def page_etfs():
    """Página de gestión de ETFs"""
    data = get_session_state()
    
    st.subheader("📚 Base de Datos de ETFs")
    
    # Buscador
    st.markdown("### 🔍 Buscar y Añadir ETF")
    search = st.text_input("Buscar en Yahoo Finance (ticker o nombre)", key="etf_search")
    
    if search:
        with st.spinner("Buscando..."):
            results = search_ticker(search)
        
        if results:
            for result in results[:10]:
                col1, col2, col3, col4 = st.columns([1.5, 3, 1, 1])
                
                with col1:
                    st.code(result['symbol'])
                
                with col2:
                    st.write(result['name'][:45])
                    st.caption(f"{result['type']} - {result['exchange']}")
                
                with col3:
                    # Obtener precio
                    if st.button("Ver", key=f"view_{result['symbol']}"):
                        quote = get_quote(result['symbol'])
                        if quote and quote.get('success'):
                            st.session_state[f"quote_{result['symbol']}"] = quote
                
                with col4:
                    if st.button("➕ Añadir", key=f"add_etf_{result['symbol']}"):
                        quote = get_quote(result['symbol'])
                        if quote and quote.get('success'):
                            data['etfs'][result['symbol']] = {
                                'yahooSymbol': result['symbol'],
                                'name': quote['name'],
                                'price': quote['price'],
                                'currency': quote['currency'],
                                'change_pct': quote.get('change_pct', 0)
                            }
                            save_data(data)
                            st.success(f"✅ {result['symbol']} añadido")
                            st.rerun()
                
                # Mostrar quote si existe
                if f"quote_{result['symbol']}" in st.session_state:
                    q = st.session_state[f"quote_{result['symbol']}"]
                    st.info(f"💰 {q['price']:.2f} {q['currency']} | Cambio: {q.get('change_pct', 0):+.2f}%")
        
        elif search:
            st.warning("No se encontraron resultados")
    
    st.markdown("---")
    
    # Actualizar todos
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Actualizar Todos"):
            progress = st.progress(0)
            tickers = list(data['etfs'].keys())
            
            for i, ticker in enumerate(tickers):
                quote = get_quote(ticker)
                if quote and quote.get('success'):
                    data['etfs'][ticker].update({
                        'price': quote['price'],
                        'currency': quote['currency'],
                        'change_pct': quote.get('change_pct', 0),
                        'name': quote['name']
                    })
                progress.progress((i + 1) / len(tickers))
            
            save_data(data)
            st.success("✅ Todos actualizados")
            st.rerun()
    
    # Tabla de ETFs
    st.markdown("### 📋 ETFs Guardados")
    
    if data['etfs']:
        for ticker, etf in data['etfs'].items():
            col1, col2, col3, col4, col5, col6 = st.columns([1.5, 3, 1, 1.2, 1, 0.5])
            
            with col1:
                st.code(ticker)
            
            with col2:
                st.write(etf.get('name', '-')[:40])
            
            with col3:
                st.write(etf.get('currency', 'EUR'))
            
            with col4:
                if etf.get('price'):
                    st.write(f"{etf['price']:.2f}")
                else:
                    st.write("-")
            
            with col5:
                change = etf.get('change_pct', 0)
                color = "🟢" if change >= 0 else "🔴"
                st.write(f"{color} {change:+.2f}%")
            
            with col6:
                if st.button("🗑️", key=f"del_etf_{ticker}"):
                    del data['etfs'][ticker]
                    save_data(data)
                    st.rerun()
    else:
        st.info("No hay ETFs guardados. Usa el buscador para añadir.")

def page_settings():
    """Página de configuración"""
    data = get_session_state()
    
    st.subheader("⚙️ Configuración")
    
    # Capital
    new_capital = st.number_input(
        "Capital Total (€)",
        min_value=1000,
        value=data['settings']['capital'],
        step=1000
    )
    
    if new_capital != data['settings']['capital']:
        data['settings']['capital'] = new_capital
        save_data(data)
        st.success("✅ Capital actualizado")
    
    st.markdown("---")
    
    # Snapshot
    st.subheader("📸 Gestión de Snapshots")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📸 Guardar Snapshot Ahora"):
            positions = calculate_positions(data)
            stats = calculate_stats(data, positions)
            
            data['snapshots'].append({
                'date': datetime.now().isoformat(),
                'total_value': stats['total_value'],
                'total_invested': stats['total_invested'],
                'pnl': stats['pnl']
            })
            save_data(data)
            st.success("✅ Snapshot guardado")
    
    with col2:
        if st.button("🗑️ Borrar Todos los Snapshots"):
            data['snapshots'] = []
            save_data(data)
            st.success("Snapshots borrados")
            st.rerun()
    
    st.markdown("---")
    
    # Export/Import
    st.subheader("💾 Exportar / Importar Datos")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Descargar Backup (JSON)",
            data=json.dumps(data, indent=2, default=str),
            file_name=f"portfolio_backup_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )
    
    with col2:
        uploaded = st.file_uploader("📤 Importar Backup", type=['json'])
        if uploaded:
            try:
                imported = json.load(uploaded)
                st.session_state.data = imported
                save_data(imported)
                st.success("✅ Datos importados")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.markdown("---")
    
    # Reset
    st.subheader("⚠️ Zona de Peligro")
    
    if st.button("🗑️ Borrar TODOS los Datos", type="secondary"):
        if st.checkbox("Confirmo que quiero borrar todo"):
            st.session_state.data = {
                'settings': {'capital': 15000},
                'etfs': {},
                'signals': {},
                'orders': [],
                'snapshots': []
            }
            save_data(st.session_state.data)
            st.success("Datos borrados")
            st.rerun()

# ============================================
# MAIN
# ============================================
def main():
    render_header()
    
    # Navegación
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Dashboard",
        "📈 Señales",
        "📐 Asignación",
        "📝 Órdenes",
        "💼 Cartera",
        "📚 ETFs",
        "⚙️ Config"
    ])
    
    with tab1:
        page_dashboard()
    
    with tab2:
        page_signals()
    
    with tab3:
        page_allocation()
    
    with tab4:
        page_orders()
    
    with tab5:
        page_portfolio()
    
    with tab6:
        page_etfs()
    
    with tab7:
        page_settings()

if __name__ == "__main__":
    main()
