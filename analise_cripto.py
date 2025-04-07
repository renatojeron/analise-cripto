import requests
import pandas as pd
import concurrent.futures
from datetime import datetime
import smtplib
import ssl
import os
from email.message import EmailMessage
from tqdm import tqdm

# Estratégia
TIMEFRAME = '4h'
EMA_SHORT = 9
EMA_LONG = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_THRESHOLD = 200000
VOLA_THRESHOLD = 0.015

STABLECOINS = {"USDT", "BUSD", "USDC", "DAI", "TUSD", "PAX", "GUSD", "UST"}

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

def send_email(subject, body):
    msg = EmailMessage()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

def classify_volume(volume):
    if volume > 50000000:
        return "Alto"
    elif volume > 10000000:
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

def get_all_usdt_pairs():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        data = requests.get(url).json()
        pairs = [item['symbol'] for item in data if item['symbol'].endswith('USDT') and float(item['quoteVolume']) > VOLUME_THRESHOLD]
        return [pair for pair in pairs if pair.replace("USDT", "") not in STABLECOINS]
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
    df['score'] = ((df['rsi'] < 50) * 1.5 + (df['ema_short'] > df['ema_long']) * 2 + (df['volatility'] < VOLA_THRESHOLD) * 1 + (df['macd'] > 0) * 1.5)
    df.dropna(inplace=True)
    return df

def calculate_bollinger_bands(df):
    df['middle_band'] = df['close'].rolling(window=20).mean()
    df['std_dev'] = df['close'].rolling(window=20).std()
    df['upper_band'] = df['middle_band'] + (df['std_dev'] * 2)
    df['lower_band'] = df['middle_band'] - (df['std_dev'] * 2)
    return df

def calculate_potential(df):
    last_row = df.iloc[-1]
    upper_band = last_row['upper_band']
    current_price = last_row['close']
    potential = ((upper_band - current_price) / current_price) * 100
    return potential

def analyze_pair(pair):
    df = get_historical_data(pair)
    if df.empty:
        return None

    df = calculate_indicators(df)
    df = calculate_bollinger_bands(df)

    df['pct_change'] = df['close'].pct_change()
    last_5_candles_pct = df['pct_change'].tail(5).sum()
    if last_5_candles_pct > 0.10:
        return None

    last_row = df.iloc[-1]

    if last_row['volatility'] < 0.005:
        return None

    return {
        'symbol': pair,
        'quote': round(last_row['close'], 4),
        'rsi': round(last_row['rsi'], 2),
        'macd': round(last_row['macd'], 4),
        'score': round(last_row['score'], 2),
        'volume': classify_volume(last_row['volume']),
        'potential': round(calculate_potential(df), 2),
    }

def find_opportunities():
    pairs = get_all_usdt_pairs()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(tqdm(executor.map(analyze_pair, pairs), total=len(pairs), desc="Analisando"))
    return [r for r in results if r]

def main():
    print(f"\n⏳ Rodando análise às {datetime.now().strftime('%H:%M:%S')}...")
    trades = find_opportunities()
    for t in trades:
        if t['score'] >= 5:
            subject = f"Oportunidade: {t['symbol']} com Score {t['score']}"
            body = f"""
🕒 Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔍 Par: {t['symbol']}
📈 Cotação: {t['quote']}
⭐ Score: {t['score']}
📊 RSI: {t['rsi']}
📉 MACD: {t['macd']}
💥 Potencial: {t['potential']}%
📦 Volume: {t['volume']}
"""
            send_email(subject, body)
            print(f"✅ E-mail enviado para {EMAIL_RECEIVER} sobre {t['symbol']}")
        else:
            print(f"🔸 {t['symbol']} - Score {t['score']}")

if __name__ == "__main__":
    main()
