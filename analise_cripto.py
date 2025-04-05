import requests
import pandas as pd
import concurrent.futures
from jinja2 import Template
from tqdm import tqdm
from datetime import datetime

# Configurações da estratégia
TIMEFRAME = '4h'
EMA_SHORT = 9
EMA_LONG = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_MINIMO_USDT = 10_000_000

def classify_volume(volume):
    if volume > 50_000_000:
        return "Alto"
    elif volume > 10_000_000:
        return "Médio"
    return "Baixo"

def calculate_trailing_stop(atr, volatility):
    if volatility > 0.05:
        return 10
    elif volatility > 0.03:
        return 7
    elif volatility > 0.02:
        return 5
    return 3

def get_all_usdt_pairs(min_volume_usdt=VOLUME_MINIMO_USDT):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        data = requests.get(url).json()
        return [
            {'symbol': item['symbol'], 'quoteVolume': float(item['quoteVolume'])}
            for item in data
            if item['symbol'].endswith('USDT') and float(item['quoteVolume']) > min_volume_usdt
        ]
    except Exception as e:
        print(f"Erro ao buscar pares: {e}")
        return []

def get_historical_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={TIMEFRAME}&limit=200"
    try:
        data = requests.get(url).json()
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '', '', '', '', '', ''])
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"Erro ao buscar dados históricos de {symbol}: {e}")
        return pd.DataFrame()

def calculate_indicators(df):
    df = df.copy()
    df['ema_short'] = df['close'].ewm(span=EMA_SHORT, adjust=False).mean()
    df['ema_long'] = df['close'].ewm(span=EMA_LONG, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['atr'] = (df['high'] - df['low']).rolling(window=ATR_PERIOD).mean()
    df['volatility'] = df['atr'] / df['close']
    df['macd'] = df['close'].ewm(span=MACD_FAST, adjust=False).mean() - df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    df.dropna(inplace=True)
    return df

def calculate_bollinger_bands(df):
    df['middle_band'] = df['close'].rolling(window=20).mean()
    df['std_dev'] = df['close'].rolling(window=20).std()
    df['upper_band'] = df['middle_band'] + (df['std_dev'] * 2)
    df['lower_band'] = df['middle_band'] - (df['std_dev'] * 2)
    return df

def calculate_obv(df):
    df['obv'] = (df['volume'] * ((df['close'] - df['close'].shift(1)) > 0).astype(int)) - (df['volume'] * ((df['close'] - df['close'].shift(1)) < 0).astype(int))
    df['obv'] = df['obv'].cumsum()
    return df

def calculate_fibonacci(df):
    high = df['high'].max()
    low = df['low'].min()
    diff = high - low
    df['fib_0.236'] = high - diff * 0.236
    df['fib_0.382'] = high - diff * 0.382
    df['fib_0.5'] = high - diff * 0.5
    df['fib_0.618'] = high - diff * 0.618
    df['fib_0.786'] = high - diff * 0.786
    return df

def check_candlestick_patterns(df):
    df['hammer'] = (df['close'] > df['open']) & ((df['high'] - df['low']) > 3 * abs(df['close'] - df['open']))
    return df

def calculate_potential(df):
    last_row = df.iloc[-1]
    upper_band = last_row['upper_band']
    current_price = last_row['close']
    potential = ((upper_band - current_price) / current_price) * 100
    return potential

def analyze_pair(pair_data):
    pair = pair_data['symbol']
    volume_usdt = pair_data['quoteVolume']

    df = get_historical_data(pair)
    if df.empty:
        return None

    df = calculate_indicators(df)
    df = calculate_bollinger_bands(df)
    df = calculate_obv(df)
    df = calculate_fibonacci(df)
    df = check_candlestick_patterns(df)

    last = df.iloc[-1]
    previous = df.iloc[-2]

    criterios = {
        "RSI < 50": last['rsi'] < 50,
        "EMA 9 > EMA 50": last['ema_short'] > last['ema_long'],
        "Volatilidade < 1.5%": last['volatility'] < 0.015,
        "MACD > 0": last['macd'] > 0,
        "OBV crescente": last['obv'] > previous['obv'],
        "Preço acima da média BB": last['close'] > last['middle_band'],
        "Padrão martelo": last['hammer']
    }

    score = sum(criterios.values())

    trailing_stop = calculate_trailing_stop(last['atr'], last['volatility'])
    stop_market = max(0.001, round(last['close'] - (2 * last['atr']), 4))

    return {
        'symbol': pair,
        'quote': round(last['close'], 4),
        'stop_market': stop_market,
        'trailing_stop': trailing_stop,
        'rsi': round(last['rsi'], 2),
        'macd': round(last['macd'], 4),
        'score': round(score, 2),
        'criterios': criterios,
        'volume': classify_volume(volume_usdt),
        'volume_usdt': round(volume_usdt, 2),
        'potential': round(calculate_potential(df), 2)
    }

def find_opportunities():
    pairs_data = get_all_usdt_pairs()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(tqdm(executor.map(analyze_pair, pairs_data), total=len(pairs_data), desc="Analisando Mercados"))
    return [trade for trade in results if trade]

def select_best_opportunity(trades):
    return max(trades, key=lambda x: x['score']) if trades else None

def generate_best_trade_html(best_trade):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    take_profit = round(best_trade['quote'] * (1 + best_trade['potential'] / 100), 4)
    stop_loss = best_trade['stop_market']
    score_str = f"{best_trade['score']} de 7.0"

    criterios_html = "".join([
        f"<li>{'✅' if ok else '❌'} {desc}</li>"
        for desc, ok in best_trade['criterios'].items()
    ])

    html_template = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>Melhor Oportunidade de Trade</title>
        <style>
            body {{
                background: linear-gradient(to right, #0f2027, #203a43, #2c5364);
                color: #f0f0f0;
                font-family: 'Segoe UI', sans-serif;
                padding: 40px;
            }}
            .container {{
                background-color: rgba(255, 255, 255, 0.05);
                padding: 30px;
                border-radius: 20px;
                box-shadow: 0 0 20px rgba(0,255,255,0.2);
                max-width: 700px;
                margin: auto;
            }}
            h1, h2 {{
                color: #00ffff;
                text-align: center;
            }}
            ul {{ font-size: 18px; list-style: none; padding: 0; }}
            li {{ margin: 5px 0; }}
            .info {{
                font-size: 18px;
                margin-bottom: 12px;
            }}
            .badge {{
                display: inline-block;
                padding: 8px 15px;
                border-radius: 12px;
                background-color: #00ffff;
                color: #000;
                margin: 10px 0;
                font-weight: bold;
            }}
            .footer {{
                text-align: center;
                margin-top: 25px;
                font-size: 14px;
                color: #aaa;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Melhor Oportunidade de Trade</h1>
            <h2>{best_trade['symbol']}</h2>

            <p class="info">💹 <strong>Cotação Atual:</strong> R$ {best_trade['quote']}</p>
            <p class="info">📈 <strong>Potencial de Valorização:</strong> {best_trade['potential']}%</p>
            <p class="info">📊 <strong>RSI:</strong> {best_trade['rsi']}</p>
            <p class="info">📉 <strong>MACD:</strong> {best_trade['macd']}</p>
            <p class="info">🔥 <strong>Volume:</strong> {best_trade['volume']} ({best_trade['volume_usdt']} USDT)</p>
            <p class="info">🧠 <strong>Score:</strong> {score_str}</p>

            <ul>{criterios_html}</ul>

            <p class="info badge">🎯 Sugestão de venda para lucro: R$ {take_profit}</p>
            <p class="info badge">🛑 Stop Loss sugerido: R$ {stop_loss}</p>

            <div class="footer">Última atualização: {now}</div>
        </div>
    </body>
    </html>
    """

    with open("melhor_oportunidade_trade.html", "w", encoding="utf-8") as f:
        f.write(html_template)

    print("✅ Relatório HTML gerado com sucesso!")

# EXECUÇÃO
trades = find_opportunities()
best_trade = select_best_opportunity(trades)
if best_trade:
    generate_best_trade_html(best_trade)
else:
    print("❌ Nenhuma oportunidade encontrada.")
