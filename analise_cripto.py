import requests
import pandas as pd
import numpy as np
from datetime import datetime
from time import sleep

def get_klines(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        data = requests.get(url, params=params, timeout=5).json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
        return df
    except:
        return None

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))

def macd(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9).mean()
    return line, signal

def atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def adx(df, period=14):
    up = df['high'].diff()
    down = -df['low'].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, period)
    plus_di = 100 * pd.Series(plus_dm).rolling(window=period).mean() / tr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=period).mean() / tr
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    return dx.rolling(window=period).mean()

def is_bullish_engulfing(df):
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    return (
        prev['close'] < prev['open'] and
        curr['close'] > curr['open'] and
        curr['close'] > prev['open'] and
        curr['open'] < prev['close']
    )

def backtest_success(df):
    success = 0
    total = 0
    for i in range(20, len(df)-3):
        rsi_val = df['rsi'].iloc[i]
        macd_val = df['macd'].iloc[i]
        macd_sig = df['macd_signal'].iloc[i]
        if macd_val > macd_sig and 45 < rsi_val < 70:
            future = df['close'].iloc[i+2]
            now = df['close'].iloc[i]
            if future > now * 1.03:
                success += 1
            total += 1
    return success / total if total > 0 else 0

def calculate_indicators(df):
    df['rsi'] = rsi(df['close'])
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    df['macd'], df['macd_signal'] = macd(df['close'])
    df['atr'] = atr(df)
    df['adx'] = adx(df)
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    return df

def mercado_favoravel():
    df = get_klines('BTCUSDT')
    if df is not None:
        df = calculate_indicators(df)
        last = df.iloc[-1]
        return last['macd'] > last['macd_signal']
    return False

def get_usdt_pairs():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    data = requests.get(url).json()
    return [x['symbol'] for x in data if x['symbol'].endswith('USDT') and not any(s in x['symbol'] for s in ['BUSD', 'TUSD', 'EUR', 'USDC']) and float(x['quoteVolume']) > 10_000_000]

def main():
    print("Analisando oportunidades de swing trade com IA técnica...")
    coins = get_usdt_pairs()
    favoravel = mercado_favoravel()
    oportunidades = []

    for symbol in coins:
        df = get_klines(symbol)
        if df is None or len(df) < 60:
            continue

        df = calculate_indicators(df)
        last = df.iloc[-1]

        if (
            last['close'] > last['ema50'] > last['ema200'] and
            last['macd'] > last['macd_signal'] and
            50 < last['rsi'] < 70 and
            last['volume'] > 1.5 * last['vol_ma20'] and
            last['adx'] > 20 and
            last['atr'] > last['close'] * 0.01 and
            is_bullish_engulfing(df)
        ):
            sucesso = backtest_success(df)
            score = (
                (last['rsi'] - 50) * 1.2 +
                (last['macd'] - last['macd_signal']) * 200 +
                ((last['close'] - last['ema50']) / last['ema50']) * 100 * 1.5 +
                sucesso * 100
            )
            if favoravel:
                score *= 1.1

            oportunidades.append({
                'symbol': symbol,
                'score': score,
                'rsi': round(last['rsi'], 2),
                'macd': round(last['macd'], 4),
                'macd_signal': round(last['macd_signal'], 4),
                'adx': round(last['adx'], 2),
                'close': round(last['close'], 4)
            })
        sleep(0.2)  # respeitar rate limits

    if oportunidades:
        top = sorted(oportunidades, key=lambda x: x['score'], reverse=True)[:3]
        print("\nTOP 3 Oportunidades com alta probabilidade de explosão:")
        for op in top:
            print(f"{op['symbol']} | Preço: {op['close']} | RSI: {op['rsi']} | MACD: {op['macd']} > {op['macd_signal']} | ADX: {op['adx']}")
    else:
        print("Nenhuma oportunidade clara no momento.")

if _name_ == "_main_":
    main()
