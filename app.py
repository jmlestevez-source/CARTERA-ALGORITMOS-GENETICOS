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
DEFAULT_COMMISSION_USD = 2.0  # Comisión por defecto en USD

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
            start_date = datetime.strptime(date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1)
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                hist = ticker.history(period="5d", end=end_date)
            
            if not hist.empty:
                current_price = hist['Open'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            else:
                return None
        else:
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
                return hist['Open'].iloc[-1]
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
        'settings': {
            'capital': 15000,
            'reserve': 500
        },
        'etfs': {},
        'signals': {},
        'orders': [],
        'snapshots': []
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                loaded_data = json.load(f)
                # Asegurar que existe 'reserve' en settings (migración)
                if 'reserve' not in loaded_data.get('settings', {}):
                    loaded_data['settings']['reserve'] = 500
                return loaded_data
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

def get_effective_capital(data: dict) -> float:
    """Devuelve el capital efectivo (capital total - reserva de liquidez)"""
    reserve = data['settings'].get('reserve', 500)
    return data['settings']['capital'] - reserve

def get_reserve(data: dict) -> float:
    """Devuelve la reserva de liquidez"""
    return data['settings'].get('reserve', 500)

# ============================================
# FUNCIONES DE CÁLCULO
# ============================================
def calculate_positions(data: dict) -> dict:
    """Calcula posiciones actuales basadas en órdenes"""
    positions = {}
    exchange_rate = st.session_state.get('exchange_rate', 1.08)
    
    sorted_orders = sorted(data['orders'], key=lambda x: x['date'])
    
    for order in sorted_orders:
        ticker = order['ticker']
        if ticker not in positions:
            positions[ticker] = {
                'units': 0,
                'total_cost': 0,
                'total_commission': 0,
                'avg_price': 0,
                'current_price': 0,
                'market_value': 0,
                'pnl': 0,
                'pnl_pct': 0,
                'systems': []
            }
        
        pos = positions[ticker]
        commission = order.get('commission', 0)
        
        if order['type'] == 'BUY':
            pos['total_cost'] += order['total'] + commission
            pos['total_commission'] += commission
            pos['units'] += order['units']
            if order.get('system'):
                for s in order['system'].split(', '):
                    if s and s not in pos['systems']:
                        pos['systems'].append(s)
        else:
            if pos['units'] > 0:
                ratio = order['units'] / pos['units']
                pos['total_cost'] -= pos['total_cost'] * ratio
                pos['units'] -= order['units']
                pos['total_commission'] += commission
    
    for ticker, pos in list(positions.items()):
        if pos['units'] <= 0:
            del positions[ticker]
            continue
        
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
    effective_capital = get_effective_capital(data)
    exchange_rate = st.session_state.get('exchange_rate', 1.08)
    
    allocation = {}
    cap_per_system = effective_capital / len(SYSTEMS)
    
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
    
    for ticker, item in allocation.items():
        if item['price_eur'] > 0:
            item['total_units'] = int(item['total_capital'] / item['price_eur'])
        item['weight'] = (item['total_capital'] / effective_capital * 100)
    
    return allocation

def calculate_stats(data: dict, positions: dict) -> dict:
    """Calcula estadísticas del portfolio"""
    capital = data['settings']['capital']
    effective_capital = get_effective_capital(data)
    reserve = get_reserve(data)
    
    total_value = 0
    total_invested = 0
    total_commissions = 0
    
    for pos in positions.values():
        total_value += pos['market_value']
        total_invested += pos['total_cost']
        total_commissions += pos.get('total_commission', 0)
    
    total_commissions = sum(o.get('commission', 0) for o in data['orders'])
    
    cash = max(0, capital - total_invested)
    available_cash = max(0, cash - reserve)
    pnl = total_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
    
    return {
        'total_value': total_value + cash,
        'total_invested': total_invested,
        'cash': cash,
        'available_cash': available_cash,
        'reserve': reserve,
        'total_commissions': total_commissions,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'num_positions': len(positions),
        'effective_capital': effective_capital
    }

def calculate_drawdown(snapshots: list) -> dict:
    """Calcula el drawdown máximo y actual"""
    if not snapshots or len(snapshots) < 1:
        return {'max_drawdown': 0, 'max_drawdown_pct': 0, 'current_drawdown_pct': 0}
    
    values = [s['total_value'] for s in snapshots]
    
    # Calcular máximo acumulado (peak)
    peak = values[0]
    max_drawdown = 0
    max_drawdown_pct = 0
    
    for value in values:
        if value > peak:
            peak = value
        
        drawdown = peak - value
        drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
        
        if drawdown_pct > max_drawdown_pct:
            max_drawdown = drawdown
            max_drawdown_pct = drawdown_pct
    
    # Drawdown actual
    current_peak = max(values)
    current_value = values[-1]
    current_drawdown_pct = ((current_peak - current_value) / current_peak * 100) if current_peak > 0 else 0
    
    return {
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': max_drawdown_pct,
        'current_drawdown_pct': current_drawdown_pct,
        'peak': current_peak
    }

# ============================================
# COMPONENTES UI
# ============================================
def render_metric_card(title: str, value: str, delta: str = None, delta_color: str = "normal"):
    """Renderiza una tarjeta de métrica"""
    st.metric(label=title, value=value, delta=delta, delta_color=delta_color)

def render_header():
    """Renderiza el header de la aplicación"""
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
    with col1:
        st.markdown('<p class="main-header">🧬 Cartera Algoritmos Genéticos</p>', unsafe_allow_html=True)
        st.caption("Gestión de cartera multi-sistema con datos de Yahoo Finance")
    
    with col2:
        rate = st.session_state.get('exchange_rate', 1.08)
        st.metric("EUR/USD", f"{rate:.4f}")
    
    with col3:
        data = get_session_state()
        st.metric("Capital Total", f"{data['settings']['capital']:,.0f} €")
    
    with col4:
        data = get_session_state()
        effective = get_effective_capital(data)
        reserve = get_reserve(data)
        st.metric("Capital Efectivo", f"{effective:,.0f} €", f"-{reserve:.0f}€ reserva")

# ============================================
# PÁGINAS
# ============================================
def page_dashboard():
    """Página principal - Dashboard"""
    data = get_session_state()
    positions = calculate_positions(data)
    stats = calculate_stats(data, positions)
    drawdown_stats = calculate_drawdown(data['snapshots'])
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
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
            "💵 Liquidez Disponible",
            f"{stats['available_cash']:,.2f} €",
            f"Reserva: {stats['reserve']:.0f}€"
        )
    
    with col4:
        st.metric(
            "💸 Comisiones Totales",
            f"{stats['total_commissions']:,.2f} €",
            f"{len(data['orders'])} órdenes"
        )
    
    with col5:
        st.metric(
            "📦 Posiciones",
            stats['num_positions'],
            f"Cap. efectivo: {stats['effective_capital']:,.0f}€"
        )
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Evolución del Portfolio")
        
        if data['snapshots']:
            df_snapshots = pd.DataFrame(data['snapshots'])
            df_snapshots['date'] = pd.to_datetime(df_snapshots['date'])
            df_snapshots = df_snapshots.sort_values('date')
            
            # Calcular máximo acumulado para drawdown
            df_snapshots['peak'] = df_snapshots['total_value'].cummax()
            df_snapshots['drawdown'] = (df_snapshots['peak'] - df_snapshots['total_value']) / df_snapshots['peak'] * 100
            
            # Crear figura con dos ejes Y
            fig = go.Figure()
            
            # Curva de equity
            fig.add_trace(go.Scatter(
                x=df_snapshots['date'],
                y=df_snapshots['total_value'],
                mode='lines+markers',
                name='Valor Portfolio',
                line=dict(color='#0ea5e9', width=2),
                marker=dict(size=8, color='#0ea5e9'),
                fill='tozeroy',
                fillcolor='rgba(14,165,233,0.1)',
                hovertemplate='%{x|%d/%m/%Y}<br>Valor: %{y:,.2f}€<extra></extra>'
            ))
            
            # Línea de máximo (peak)
            fig.add_trace(go.Scatter(
                x=df_snapshots['date'],
                y=df_snapshots['peak'],
                mode='lines',
                name='Máximo Histórico',
                line=dict(color='#10b981', width=1, dash='dash'),
                hovertemplate='%{x|%d/%m/%Y}<br>Peak: %{y:,.2f}€<extra></extra>'
            ))
            
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#94a3b8',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode='x unified',
                yaxis=dict(title='Valor (€)', tickformat=','),
                xaxis=dict(title='')
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Métricas de drawdown
            col_dd1, col_dd2, col_dd3 = st.columns(3)
            with col_dd1:
                st.metric("📉 Max Drawdown", f"{drawdown_stats['max_drawdown_pct']:.2f}%", 
                         f"-{drawdown_stats['max_drawdown']:,.2f}€")
            with col_dd2:
                st.metric("📊 Drawdown Actual", f"{drawdown_stats['current_drawdown_pct']:.2f}%")
            with col_dd3:
                st.metric("🏔️ Peak", f"{drawdown_stats['peak']:,.2f}€")
        else:
            st.info("No hay snapshots guardados. Usa el botón 'Guardar Snapshot' para empezar a trackear la evolución.")
            if st.button("📸 Guardar Snapshot", key="snapshot_dashboard"):
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
            
            for sys in SYSTEMS:
                if system_values[sys] == 0:
                    system_values[sys] = get_effective_capital(data) / len(SYSTEMS)
            
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
    
    for i in range(0, len(SYSTEMS), 2):
        cols = st.columns(2)
        
        for j, col in enumerate(cols):
            if i + j < len(SYSTEMS):
                system = SYSTEMS[i + j]
                
                with col:
                    st.markdown(f"### 🎯 {system}")
                    
                    sys_signals = data['signals'][key].get(system, {'buy': [], 'hold': [], 'sell': []})
                    
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
                    
                    st.markdown("**🟡 MANTENER**")
                    current_hold = [t for t in sys_signals.get('hold', []) if t in buy_options]
                    new_hold = st.multiselect(
                        "ETFs a mantener",
                        options=buy_options,
                        default=current_hold,
                        key=f"hold_{system}_{key}",
                        label_visibility="collapsed"
                    )
                    
                    st.markdown("**🔴 VENDER**")
                    current_sell = [t for t in sys_signals.get('sell', []) if t in buy_options]
                    new_sell = st.multiselect(
                        "ETFs a vender",
                        options=buy_options,
                        default=current_sell,
                        key=f"sell_{system}_{key}",
                        label_visibility="collapsed"
                    )
                    
                    data['signals'][key][system] = {
                        'buy': new_buy,
                        'hold': new_hold,
                        'sell': new_sell
                    }
                    
                    st.markdown("---")
    
    if st.button("💾 Guardar Señales", type="primary", use_container_width=True):
        save_data(data)
        st.success("✅ Señales guardadas correctamente")

def page_allocation():
    """Página de asignación calculada"""
    data = get_session_state()
    effective_capital = get_effective_capital(data)
    reserve = get_reserve(data)
    
    st.subheader("📊 Asignación Calculada")
    
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
        st.metric("Capital Efectivo", f"{effective_capital:,.0f} €", f"Reserva: {reserve:.0f}€")
    
    with col4:
        st.metric("Por Sistema", f"{effective_capital/5:,.0f} €")
    
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
                        exchange_rate = st.session_state.get('exchange_rate', 1.08)
                        commission_eur = DEFAULT_COMMISSION_USD / exchange_rate
                        
                        order = {
                            'id': int(datetime.now().timestamp() * 1000),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'type': 'BUY',
                            'ticker': ticker,
                            'units': item['total_units'],
                            'price': round(item['price_eur'], 2),
                            'total': round(item['total_units'] * item['price_eur'], 2),
                            'commission': round(commission_eur, 2),
                            'system': ', '.join(item['systems'])
                        }
                        data['orders'].insert(0, order)
                        save_data(data)
                        st.success(f"✅ Compra de {item['total_units']} {ticker} registrada (comisión: {commission_eur:.2f}€)")
                        st.rerun()
    else:
        st.info("No hay señales cargadas para este mes. Ve a la pestaña 'Señales' para añadirlas.")

def page_orders():
    """Página de registro de órdenes"""
    data = get_session_state()
    exchange_rate = st.session_state.get('exchange_rate', 1.08)
    
    st.subheader("📝 Registro de Órdenes")
    
    with st.expander("➕ Nueva Orden", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            order_type = st.radio("Tipo", ["BUY", "SELL"], horizontal=True)
        
        with col2:
            order_date = st.date_input("Fecha", datetime.now(), key="order_date_input")
        
        search = st.text_input("🔍 Buscar ETF/Acción", key="order_search")
        
        selected_ticker = None
        selected_price = 0.0
        order_date_str = order_date.strftime('%Y-%m-%d')
        date_exchange_rate = exchange_rate
        
        if search:
            results = search_ticker(search)
            if results:
                options = [f"{r['symbol']} - {r['name'][:30]}" for r in results[:5]]
                selected = st.selectbox("Seleccionar", options, key="order_select")
                if selected:
                    selected_ticker = selected.split(" - ")[0]
                    
                    with st.spinner("Obteniendo precio..."):
                        quote = get_quote(selected_ticker, order_date_str)
                        date_exchange_rate = get_exchange_rate(order_date_str)
                    
                    if quote and quote.get('success'):
                        data['etfs'][selected_ticker] = {
                            'yahooSymbol': selected_ticker,
                            'name': quote['name'],
                            'price': quote['price'],
                            'currency': quote['currency'],
                            'change_pct': quote.get('change_pct', 0)
                        }
                        
                        price = quote['price']
                        if quote['currency'] == 'USD':
                            price = price / date_exchange_rate
                        elif quote['currency'] == 'GBP':
                            price = price * 1.17
                        selected_price = price
                        
                        st.info(f"💰 Precio apertura {order_date_str}: {quote['price']:.2f} {quote['currency']} = {price:.2f} € | EUR/USD: {date_exchange_rate:.4f}")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            units = st.number_input("Unidades", min_value=1, value=1)
        
        with col2:
            price = st.number_input("Precio (€)", min_value=0.01, value=selected_price if selected_price > 0 else 100.0, format="%.2f")
        
        with col3:
            default_commission_eur = DEFAULT_COMMISSION_USD / date_exchange_rate
            commission = st.number_input(
                f"Comisión (€)", 
                min_value=0.0, 
                value=round(default_commission_eur, 2), 
                format="%.2f",
                help=f"Por defecto: {DEFAULT_COMMISSION_USD} USD = {default_commission_eur:.2f} EUR"
            )
        
        with col4:
            system = st.selectbox("Sistema (opcional)", [""] + SYSTEMS)
        
        subtotal = units * price
        total = subtotal + commission
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Subtotal", f"{subtotal:,.2f} €")
        with col2:
            st.metric("Comisión", f"{commission:,.2f} €")
        with col3:
            st.metric("Total", f"{total:,.2f} €")
        
        if st.button("✅ Registrar Orden", type="primary", disabled=not selected_ticker):
            order = {
                'id': int(datetime.now().timestamp() * 1000),
                'date': order_date_str,
                'type': order_type,
                'ticker': selected_ticker,
                'units': units,
                'price': round(price, 2),
                'total': round(subtotal, 2),
                'commission': round(commission, 2),
                'system': system
            }
            data['orders'].insert(0, order)
            save_data(data)
            st.success(f"✅ Orden de {order_type} registrada: {units} {selected_ticker} @ {price:.2f} € + {commission:.2f}€ comisión")
            st.rerun()
    
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    total_bought = sum(o['total'] for o in data['orders'] if o['type'] == 'BUY')
    total_sold = sum(o['total'] for o in data['orders'] if o['type'] == 'SELL')
    total_commissions = sum(o.get('commission', 0) for o in data['orders'])
    
    with col1:
        st.metric("🟢 Total Comprado", f"{total_bought:,.2f} €")
    with col2:
        st.metric("🔴 Total Vendido", f"{total_sold:,.2f} €")
    with col3:
        st.metric("📊 Neto Invertido", f"{total_bought - total_sold:,.2f} €")
    with col4:
        st.metric("💸 Total Comisiones", f"{total_commissions:,.2f} €")
    
    st.markdown("---")
    st.subheader("📋 Historial de Órdenes")
    
    if data['orders']:
        orders_to_delete = None
        
        for idx, order in enumerate(data['orders']):
            col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1.1, 0.9, 1, 0.7, 0.9, 0.9, 0.7, 0.9, 0.4])
            
            with col1:
                st.write(order['date'])
            with col2:
                tipo = '🟢 COMPRA' if order['type'] == 'BUY' else '🔴 VENTA'
                st.write(tipo)
            with col3:
                st.write(order['ticker'])
            with col4:
                st.write(order['units'])
            with col5:
                st.write(f"{order['price']:.2f} €")
            with col6:
                st.write(f"{order['total']:.2f} €")
            with col7:
                comm = order.get('commission', 0)
                st.write(f"{comm:.2f} €")
            with col8:
                st.write(order.get('system', '-') or '-')
            with col9:
                if st.button("🗑️", key=f"del_order_{idx}_{order['id']}"):
                    orders_to_delete = idx
        
        if orders_to_delete is not None:
            data['orders'].pop(orders_to_delete)
            save_data(data)
            st.rerun()
    else:
        st.info("No hay órdenes registradas.")

def page_portfolio():
    """Página de cartera"""
    data = get_session_state()
    positions = calculate_positions(data)
    
    st.subheader("💼 Cartera Actual")
    
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
        
        if hasattr(st.session_state, 'selling_ticker') and st.session_state.selling_ticker:
            ticker = st.session_state.selling_ticker
            pos = st.session_state.selling_pos
            
            st.warning(f"📤 Vender {ticker}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                sell_units = st.number_input("Unidades a vender", min_value=1, max_value=pos['units'], value=pos['units'])
            with col2:
                sell_price = st.number_input("Precio (€)", min_value=0.01, value=pos['current_price'], format="%.2f")
            with col3:
                exchange_rate = st.session_state.get('exchange_rate', 1.08)
                default_commission_eur = DEFAULT_COMMISSION_USD / exchange_rate
                sell_commission = st.number_input("Comisión (€)", min_value=0.0, value=round(default_commission_eur, 2), format="%.2f")
            
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
                        'commission': round(sell_commission, 2),
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
                
                if f"quote_{result['symbol']}" in st.session_state:
                    q = st.session_state[f"quote_{result['symbol']}"]
                    st.info(f"💰 {q['price']:.2f} {q['currency']} | Cambio: {q.get('change_pct', 0):+.2f}%")
        
        elif search:
            st.warning("No se encontraron resultados")
    
    st.markdown("---")
    
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
    
    st.markdown("### 📋 ETFs Guardados")
    
    if data['etfs']:
        tickers_list = list(data['etfs'].keys())
        etf_to_delete = None
        
        for ticker in tickers_list:
            etf = data['etfs'][ticker]
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
                if st.button("🗑️", key=f"delete_etf_{ticker}"):
                    etf_to_delete = ticker
        
        if etf_to_delete is not None:
            del data['etfs'][etf_to_delete]
            save_data(data)
            st.rerun()
    else:
        st.info("No hay ETFs guardados. Usa el buscador para añadir.")

def page_settings():
    """Página de configuración"""
    data = get_session_state()
    
    st.subheader("⚙️ Configuración")
    
    # Capital y liquidez editables
    st.markdown("### 💰 Capital y Reserva")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        new_capital = st.number_input(
            "Capital Total (€)",
            min_value=1000,
            value=data['settings']['capital'],
            step=500,
            help="Capital total de la cartera"
        )
    
    with col2:
        current_reserve = data['settings'].get('reserve', 500)
        new_reserve = st.number_input(
            "Reserva de Liquidez (€)",
            min_value=0,
            max_value=new_capital - 1000,
            value=current_reserve,
            step=100,
            help="Cantidad reservada que no se usará para inversiones"
        )
    
    with col3:
        effective = new_capital - new_reserve
        st.metric("Capital Efectivo", f"{effective:,.0f} €")
    
    # Guardar cambios si hay modificaciones
    if new_capital != data['settings']['capital'] or new_reserve != current_reserve:
        if st.button("💾 Guardar Configuración de Capital", type="primary"):
            data['settings']['capital'] = new_capital
            data['settings']['reserve'] = new_reserve
            save_data(data)
            st.success("✅ Configuración actualizada")
            st.rerun()
    
    st.info(f"ℹ️ Se reservan {new_reserve}€ de liquidez para evitar problemas de ejecución. Los cálculos de asignación se realizan sobre el capital efectivo ({effective:,.0f}€).")
    
    st.markdown("---")
    
    # Comisión por defecto
    st.markdown("### 💸 Comisión por Defecto")
    st.info(f"La comisión por defecto es de **{DEFAULT_COMMISSION_USD} USD** por orden, que se convierte automáticamente a EUR según el tipo de cambio del día de la orden.")
    
    st.markdown("---")
    
    # Snapshot
    st.markdown("### 📸 Gestión de Snapshots")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📸 Guardar Snapshot Ahora", use_container_width=True):
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
            st.rerun()
    
    with col2:
        st.metric("Snapshots guardados", len(data['snapshots']))
    
    with col3:
        if st.button("🗑️ Borrar Todos los Snapshots", use_container_width=True):
            data['snapshots'] = []
            save_data(data)
            st.success("Snapshots borrados")
            st.rerun()
    
    # Mostrar historial de snapshots
    if data['snapshots']:
        with st.expander("📋 Ver Historial de Snapshots"):
            snapshots_df = pd.DataFrame(data['snapshots'])
            snapshots_df['date'] = pd.to_datetime(snapshots_df['date']).dt.strftime('%Y-%m-%d %H:%M')
            snapshots_df.columns = ['Fecha', 'Valor Total', 'Invertido', 'P&L']
            st.dataframe(snapshots_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Export/Import
    st.markdown("### 💾 Exportar / Importar Datos")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Descargar Backup (JSON)",
            data=json.dumps(data, indent=2, default=str),
            file_name=f"portfolio_backup_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        uploaded = st.file_uploader("📤 Importar Backup", type=['json'])
        if uploaded:
            try:
                imported = json.load(uploaded)
                # Asegurar compatibilidad
                if 'reserve' not in imported.get('settings', {}):
                    imported['settings']['reserve'] = 500
                st.session_state.data = imported
                save_data(imported)
                st.success("✅ Datos importados")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.markdown("---")
    
    # Reset
    st.markdown("### ⚠️ Zona de Peligro")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Borrar TODOS los Datos", type="secondary", use_container_width=True):
            st.session_state.confirm_delete = True
    
    if st.session_state.get('confirm_delete', False):
        st.warning("⚠️ Esta acción eliminará todos los datos. ¿Estás seguro?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Sí, borrar todo", type="primary"):
                st.session_state.data = {
                    'settings': {'capital': 15000, 'reserve': 500},
                    'etfs': {},
                    'signals': {},
                    'orders': [],
                    'snapshots': []
                }
                save_data(st.session_state.data)
                st.session_state.confirm_delete = False
                st.success("Datos borrados")
                st.rerun()
        with col2:
            if st.button("❌ Cancelar"):
                st.session_state.confirm_delete = False
                st.rerun()

# ============================================
# MAIN
# ============================================
def main():
    render_header()
    
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
