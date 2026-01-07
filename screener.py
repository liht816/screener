import requests
import time
from datetime import datetime
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = "7589870613:AAFtTcUROflTN40AMsoQZvS4oy6AmrjEBXI"
ADMIN_LINK = "https://t.me/kingpumpdump"
# ═══════════════════════════════════════════════════════════════


class MEXCFullScreener:
    def __init__(self, send_func):
        self.base_url = "https://contract.mexc.com"
        self.spot_url = "https://api.mexc.com"
        
        self.sent_alerts = {}
        self.timeframe = "Min5"
        self.timeframe_display = "5m"
        self.min_pump = 5.0
        self.min_dump = 5.0
        self.send_telegram = send_func
        self.chat_id = None
        
        self.signal_mode = "both"
        self.candle_mode = "current"
        self.scan_interval = 5
        
        self.futures_symbols = []
        self.spot_symbols = []
        self.all_symbols = []
        self.funding_rates = {}
        self.last_update = 0
        
        self.cached_futures_tickers = {}
        self.cached_spot_tickers = {}
        self.tickers_cache_time = 0
        
        self.min_volume_usdt = 0
        self.market_type_filter = "all"
        self.spot_quote_filter = "all"
        
        self.alert_cooldown = 60
        self.allow_duplicates = True
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        self.tf_map = {
            "1m": "Min1", "5m": "Min5", "15m": "Min15",
            "30m": "Min30", "1h": "Min60", "4h": "Hour4", "1d": "Day1"
        }
        
        self.spot_tf_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d"
        }
        
        self.tf_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400
        }
    
    def format_number(self, num):
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.2f}M"
        elif num >= 1_000:
            return f"{num/1_000:.2f}K"
        return f"{num:.2f}"
    
    def format_price(self, price):
        if price >= 100:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        elif price >= 0.0001:
            return f"{price:.6f}"
        return f"{price:.8f}"
    
    def format_time_remaining(self, seconds):
        if seconds <= 0:
            return "закрыта"
        m, s = int(seconds // 60), int(seconds % 60)
        return f"{m}м {s}с" if m > 0 else f"{s}с"
    
    def get_funding_rates(self):
        funding = {}
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/funding_rate",
                                   headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        rate = float(item.get('fundingRate', 0))
                        funding[symbol] = rate * 100
        except Exception as e:
            print(f"Funding error: {e}")
        return funding
    
    def get_futures_symbols(self):
        symbols = {}
        
        print("   🔍 Сбор ВСЕХ деривативов MEXC...")
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/detail", 
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol:
                            symbols[symbol] = {
                                'symbol': symbol,
                                'state': item.get('state', 0),
                                'type': item.get('contractType', 'unknown'),
                                'quote': item.get('quoteCoin', ''),
                                'base': item.get('baseCoin', '')
                            }
            print(f"      📋 Contract detail: {len(symbols)}")
        except Exception as e:
            print(f"      ❌ Contract detail error: {e}")
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/ticker",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'from_ticker', 'state': 0}
            print(f"      📊 После тикеров: {len(symbols)}")
        except Exception as e:
            print(f"      ❌ Ticker error: {e}")
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/funding_rate",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'perpetual', 'state': 0}
            print(f"      💰 После funding: {len(symbols)}")
        except:
            pass
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/risk_reverse",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'from_risk', 'state': 0}
            print(f"      ⚖️ После risk: {len(symbols)}")
        except:
            pass
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/index_price",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'from_index', 'state': 0}
            print(f"      📈 После index: {len(symbols)}")
        except:
            pass
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/fair_price",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'from_fair', 'state': 0}
            print(f"      💲 После fair: {len(symbols)}")
        except:
            pass
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/open_interest",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol')
                        if symbol and symbol not in symbols:
                            symbols[symbol] = {'symbol': symbol, 'type': 'from_oi', 'state': 0}
            print(f"      📊 После OI: {len(symbols)}")
        except:
            pass
        
        active_symbols = []
        for sym, info in symbols.items():
            if info.get('state', 0) == 0 or info.get('type') in ['from_ticker', 'perpetual']:
                active_symbols.append(sym)
        
        print(f"   ✅ ИТОГО деривативов: {len(active_symbols)}")
        return active_symbols
    
    def get_spot_symbols(self):
        symbols = {}
        
        print("   🔍 Сбор ВСЕХ спот пар MEXC...")
        
        try:
            response = requests.get(f"{self.spot_url}/api/v3/exchangeInfo",
                                   headers=self.headers, timeout=60)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('symbols', []):
                    sym = item.get('symbol', '')
                    status = item.get('status', '')
                    base = item.get('baseAsset', '')
                    quote = item.get('quoteAsset', '')
                    
                    if status == 'TRADING' and sym:
                        symbols[sym] = {
                            'symbol': sym,
                            'base': base,
                            'quote': quote,
                            'status': status
                        }
            print(f"      📋 ExchangeInfo: {len(symbols)}")
        except Exception as e:
            print(f"      ❌ ExchangeInfo error: {e}")
        
        try:
            response = requests.get(f"{self.spot_url}/api/v3/ticker/24hr",
                                   headers=self.headers, timeout=60)
            if response.status_code == 200:
                for item in response.json():
                    sym = item.get('symbol', '')
                    if sym and sym not in symbols:
                        symbols[sym] = {
                            'symbol': sym,
                            'quote': 'USDT' if 'USDT' in sym else ('BTC' if 'BTC' in sym else 'OTHER'),
                            'status': 'TRADING'
                        }
            print(f"      📊 После ticker: {len(symbols)}")
        except Exception as e:
            print(f"      ❌ Ticker error: {e}")
        
        try:
            response = requests.get(f"{self.spot_url}/api/v3/ticker/price",
                                   headers=self.headers, timeout=60)
            if response.status_code == 200:
                for item in response.json():
                    sym = item.get('symbol', '')
                    if sym and sym not in symbols:
                        symbols[sym] = {
                            'symbol': sym,
                            'status': 'TRADING'
                        }
            print(f"      💲 После price: {len(symbols)}")
        except:
            pass
        
        if self.spot_quote_filter != "all":
            quote_upper = self.spot_quote_filter.upper()
            filtered = {k: v for k, v in symbols.items() if k.endswith(quote_upper)}
            print(f"   ✅ ИТОГО спот (фильтр {quote_upper}): {len(filtered)}")
            return list(filtered.keys())
        
        print(f"   ✅ ИТОГО спот: {len(symbols)}")
        return list(symbols.keys())
    
    def get_all_symbols(self, force_reload=False):
        if not force_reload and self.all_symbols and (time.time() - self.last_update) < 300:
            return self._filter_symbols()
        
        print("=" * 50)
        print("📊 ЗАГРУЗКА ВСЕХ ТОРГОВЫХ ПАР MEXC")
        print("=" * 50)
        
        self.futures_symbols = self.get_futures_symbols()
        self.spot_symbols = self.get_spot_symbols()
        self.funding_rates = self.get_funding_rates()
        print(f"   💰 Funding rates: {len(self.funding_rates)}")
        
        self.all_symbols = []
        
        for sym in self.futures_symbols:
            self.all_symbols.append({
                'symbol': sym,
                'type': 'futures',
                'display': sym.replace('_', '')
            })
        
        for sym in self.spot_symbols:
            self.all_symbols.append({
                'symbol': sym,
                'type': 'spot',
                'display': sym
            })
        
        self.last_update = time.time()
        
        print("=" * 50)
        print(f"📊 ИТОГО: {len(self.futures_symbols)} деривативов + {len(self.spot_symbols)} спот = {len(self.all_symbols)} пар")
        print("=" * 50)
        
        return self._filter_symbols()
    
    def _filter_symbols(self):
        if self.market_type_filter == "futures":
            return [s for s in self.all_symbols if s['type'] == 'futures']
        elif self.market_type_filter == "spot":
            return [s for s in self.all_symbols if s['type'] == 'spot']
        return self.all_symbols
    
    def get_futures_tickers(self, use_cache=False):
        if use_cache and self.cached_futures_tickers and (time.time() - self.tickers_cache_time) < 10:
            return self.cached_futures_tickers
        
        tickers = {}
        try:
            response = requests.get(f"{self.base_url}/api/v1/contract/ticker",
                                   headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    for item in data.get('data', []):
                        tickers[item['symbol']] = item
            self.cached_futures_tickers = tickers
            self.tickers_cache_time = time.time()
        except:
            pass
        return tickers
    
    def get_spot_tickers(self, use_cache=False):
        if use_cache and self.cached_spot_tickers and (time.time() - self.tickers_cache_time) < 10:
            return self.cached_spot_tickers
        
        tickers = {}
        try:
            response = requests.get(f"{self.spot_url}/api/v3/ticker/24hr",
                                   headers=self.headers, timeout=60)
            if response.status_code == 200:
                for item in response.json():
                    tickers[item['symbol']] = item
            self.cached_spot_tickers = tickers
            self.tickers_cache_time = time.time()
        except:
            pass
        return tickers
    
    def get_futures_klines(self, symbol, limit=5):
        try:
            url = f"{self.base_url}/api/v1/contract/kline/{symbol}"
            params = {'interval': self.timeframe, 'limit': limit}
            response = requests.get(url, params=params, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    kdata = data['data']
                    if isinstance(kdata, dict) and 'time' in kdata:
                        candles = []
                        times = kdata.get('time', [])
                        for i in range(len(times)):
                            candles.append({
                                'time': times[i],
                                'open': float(kdata['open'][i]) if i < len(kdata.get('open', [])) else 0,
                                'high': float(kdata['high'][i]) if i < len(kdata.get('high', [])) else 0,
                                'low': float(kdata['low'][i]) if i < len(kdata.get('low', [])) else 0,
                                'close': float(kdata['close'][i]) if i < len(kdata.get('close', [])) else 0,
                                'vol': float(kdata['vol'][i]) if i < len(kdata.get('vol', [])) else 0
                            })
                        return candles
        except:
            pass
        return None
    
    def get_spot_klines(self, symbol, limit=5):
        try:
            interval = self.spot_tf_map.get(self.timeframe_display, '5m')
            url = f"{self.spot_url}/api/v3/klines"
            params = {'symbol': symbol, 'interval': interval, 'limit': limit}
            response = requests.get(url, params=params, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                candles = []
                for k in data:
                    candles.append({
                        'time': k[0],
                        'open': float(k[1]),
                        'high': float(k[2]),
                        'low': float(k[3]),
                        'close': float(k[4]),
                        'vol': float(k[5])
                    })
                return candles
        except:
            pass
        return None
    
    def is_candle_closed(self, candle_time):
        tf_seconds = self.tf_seconds.get(self.timeframe_display, 300)
        candle_end_time = candle_time + (tf_seconds * 1000)
        current_time = int(time.time() * 1000)
        return current_time >= candle_end_time
    
    def get_time_until_close(self, candle_time):
        tf_seconds = self.tf_seconds.get(self.timeframe_display, 300)
        candle_end_time = candle_time + (tf_seconds * 1000)
        current_time = int(time.time() * 1000)
        remaining = (candle_end_time - current_time) / 1000
        return max(0, remaining)
    
    def get_change_for_period(self, symbol, market_type, period):
        period_map = {
            "1m": {"spot": "1m", "futures": "Min1"},
            "5m": {"spot": "5m", "futures": "Min5"},
            "15m": {"spot": "15m", "futures": "Min15"},
            "30m": {"spot": "30m", "futures": "Min30"},
            "1h": {"spot": "1h", "futures": "Min60"},
            "4h": {"spot": "4h", "futures": "Hour4"},
        }
        
        if period not in period_map:
            return None
        
        config = period_map[period]
        
        try:
            if market_type == 'futures':
                url = f"{self.base_url}/api/v1/contract/kline/{symbol}"
                params = {'interval': config['futures'], 'limit': 2}
                response = requests.get(url, params=params, headers=self.headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success') and data.get('data'):
                        kdata = data['data']
                        if isinstance(kdata, dict) and 'open' in kdata:
                            opens = kdata.get('open', [])
                            closes = kdata.get('close', [])
                            vols = kdata.get('vol', [])
                            
                            if opens and closes:
                                open_price = float(opens[-1])
                                close_price = float(closes[-1])
                                volume = float(vols[-1]) if vols else 0
                                
                                if open_price > 0:
                                    change = ((close_price - open_price) / open_price) * 100
                                    return {'change': change, 'open': open_price, 
                                           'close': close_price, 'volume': volume * close_price}
            else:
                url = f"{self.spot_url}/api/v3/klines"
                params = {'symbol': symbol, 'interval': config['spot'], 'limit': 2}
                response = requests.get(url, params=params, headers=self.headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        candle = data[-1]
                        open_price = float(candle[1])
                        close_price = float(candle[4])
                        volume = float(candle[7])
                        
                        if open_price > 0:
                            change = ((close_price - open_price) / open_price) * 100
                            return {'change': change, 'open': open_price,
                                   'close': close_price, 'volume': volume}
        except:
            pass
        return None
    
    def analyze_context(self, klines, current_idx):
        if not klines or len(klines) < 2:
            return {'prev_change': 0, 'impulse_series': 1}
        
        klines_sorted = sorted(klines, key=lambda x: x.get('time', 0))
        actual_idx = len(klines_sorted) + current_idx if current_idx < 0 else current_idx
        
        prev_change = 0
        if actual_idx > 0:
            prev = klines_sorted[actual_idx - 1]
            if prev.get('open', 0) > 0:
                prev_change = ((prev.get('close', 0) - prev.get('open', 0)) / prev.get('open', 0)) * 100
        
        impulse_series = 1
        current = klines_sorted[actual_idx]
        current_change = 0
        if current.get('open', 0) > 0:
            current_change = ((current.get('close', 0) - current.get('open', 0)) / current.get('open', 0)) * 100
        
        is_pump = current_change > 0
        
        for i in range(actual_idx - 1, max(actual_idx - 5, -1), -1):
            if i >= 0:
                candle = klines_sorted[i]
                if candle.get('open', 0) > 0:
                    change = ((candle.get('close', 0) - candle.get('open', 0)) / candle.get('open', 0)) * 100
                    if is_pump and change >= self.min_pump * 0.5:
                        impulse_series += 1
                    elif not is_pump and change <= -self.min_dump * 0.5:
                        impulse_series += 1
                    else:
                        break
        
        return {'prev_change': prev_change, 'impulse_series': impulse_series}
    
    def calculate_liquidity_score(self, volume_24h, spread):
        score = 0
        if volume_24h >= 1000000:
            score += 50
        elif volume_24h >= 100000:
            score += 35
        elif volume_24h >= 10000:
            score += 20
        elif volume_24h >= 1000:
            score += 10
        
        if spread is not None:
            if spread < 0.1:
                score += 50
            elif spread < 0.5:
                score += 35
            elif spread < 1:
                score += 20
            elif spread < 2:
                score += 10
        else:
            score += 25
        return min(score, 100)
    
    def should_send_alert(self, symbol, candle_time, is_closed):
        current_time = time.time()
        key = f"{symbol}_{self.timeframe}_{candle_time}" if is_closed else f"{symbol}_{self.timeframe}_live"
        
        if self.allow_duplicates:
            if key in self.sent_alerts:
                last_time, last_candle = self.sent_alerts[key]
                if not is_closed:
                    if (current_time - last_time) >= self.alert_cooldown:
                        self.sent_alerts[key] = (current_time, candle_time)
                        return True
                    return False
                if candle_time != last_candle or (current_time - last_time) >= self.alert_cooldown:
                    self.sent_alerts[key] = (current_time, candle_time)
                    return True
                return False
            else:
                self.sent_alerts[key] = (current_time, candle_time)
                return True
        else:
            full_key = f"{symbol}_{candle_time}_{self.timeframe}"
            if full_key in self.sent_alerts:
                return False
            self.sent_alerts[full_key] = True
            return True
    
    def analyze_symbol(self, symbol_info, futures_tickers, spot_tickers):
        symbol = symbol_info['symbol']
        market_type = symbol_info['type']
        
        if market_type == 'futures':
            klines = self.get_futures_klines(symbol)
            ticker = futures_tickers.get(symbol, {})
        else:
            klines = self.get_spot_klines(symbol)
            ticker = spot_tickers.get(symbol, {})
        
        if not klines or len(klines) < 2:
            return None
        
        results = []
        
        try:
            klines_sorted = sorted(klines, key=lambda x: x.get('time', 0))
            
            candles_to_check = []
            if self.candle_mode == "current":
                candles_to_check = [(-1, False)]
            elif self.candle_mode == "closed":
                last = klines_sorted[-1]
                if self.is_candle_closed(last['time']):
                    candles_to_check = [(-1, True)]
                elif len(klines_sorted) >= 2:
                    candles_to_check = [(-2, True)]
            else:
                candles_to_check = [(-1, False)]
                if len(klines_sorted) >= 2:
                    candles_to_check.append((-2, True))
            
            if market_type == 'futures':
                current_price = float(ticker.get('lastPrice', 0) or 0)
            else:
                current_price = float(ticker.get('lastPrice', 0) or 0)
            
            for idx, force_closed in candles_to_check:
                if len(klines_sorted) >= abs(idx):
                    current = klines_sorted[idx]
                    
                    open_price = current.get('open', 0)
                    close_price = current.get('close', 0)
                    high_price = current.get('high', 0)
                    low_price = current.get('low', 0)
                    volume = current.get('vol', 0)
                    candle_time = current.get('time', 0)
                    
                    if open_price <= 0:
                        continue
                    
                    change = ((close_price - open_price) / open_price) * 100
                    
                    is_pump = change >= self.min_pump
                    is_dump = change <= -self.min_dump
                    
                    if self.signal_mode == "pump" and not is_pump:
                        continue
                    elif self.signal_mode == "dump" and not is_dump:
                        continue
                    elif self.signal_mode == "both" and not (is_pump or is_dump):
                        continue
                    
                    if not (is_pump or is_dump):
                        continue
                    
                    is_closed = force_closed or self.is_candle_closed(candle_time)
                    time_remaining = 0 if is_closed else self.get_time_until_close(candle_time)
                    
                    volume_usdt = volume * close_price
                    
                    if market_type == 'futures':
                        vol24 = float(ticker.get('volume24', 0)) * close_price
                    else:
                        vol24 = float(ticker.get('quoteVolume', 0) or 0)
                    
                    if self.min_volume_usdt > 0 and vol24 < self.min_volume_usdt:
                        continue
                    
                    spread = None
                    if market_type == 'futures':
                        bid = float(ticker.get('bid1', 0) or 0)
                        ask = float(ticker.get('ask1', 0) or 0)
                        if bid > 0 and ask > 0:
                            spread = ((ask - bid) / bid) * 100
                    else:
                        bid = float(ticker.get('bidPrice', 0) or 0)
                        ask = float(ticker.get('askPrice', 0) or 0)
                        if bid > 0 and ask > 0:
                            spread = ((ask - bid) / bid) * 100
                    
                    funding_rate = self.funding_rates.get(symbol, None)
                    context = self.analyze_context(klines_sorted, idx)
                    liquidity_score = self.calculate_liquidity_score(vol24, spread)
                    
                    signal_type = "pump" if is_pump else "dump"
                    
                    if current_price <= 0:
                        current_price = close_price
                    
                    results.append({
                        'symbol': symbol,
                        'display_symbol': symbol_info['display'],
                        'market_type': market_type,
                        'signal_type': signal_type,
                        'open_price': open_price,
                        'close_price': close_price,
                        'current_price': current_price,
                        'high_price': high_price,
                        'low_price': low_price,
                        'change_percent': change,
                        'volume': volume,
                        'volume_usdt': volume_usdt,
                        'volume_24h': vol24,
                        'spread': spread,
                        'funding_rate': funding_rate,
                        'candle_time': candle_time,
                        'timeframe': self.timeframe_display,
                        'prev_change': context['prev_change'],
                        'impulse_series': context['impulse_series'],
                        'liquidity_score': liquidity_score,
                        'is_closed': is_closed,
                        'time_remaining': time_remaining
                    })
            
            return results if results else None
        except:
            pass
        return None
    
    def format_alert(self, data):
        symbol = data['display_symbol']
        market_type = "Futures" if data['market_type'] == 'futures' else "Spot"
        signal_type = data['signal_type']
        is_closed = data.get('is_closed', True)
        
        open_price = self.format_price(data['open_price'])
        close_price = self.format_price(data['close_price'])
        current_price = self.format_price(data.get('current_price', data['close_price']))
        change = data['change_percent']
        
        vol_candle = self.format_number(data['volume'])
        vol_candle_usdt = self.format_number(data['volume_usdt'])
        vol_24h = self.format_number(data['volume_24h'])
        
        spread = data['spread']
        spread_text = f"{spread:.2f}%" if spread is not None else "N/A"
        
        funding = data.get('funding_rate')
        
        tf = data['timeframe']
        prev_change = data.get('prev_change', 0)
        impulse_series = data.get('impulse_series', 1)
        liq_score = data.get('liquidity_score', 50)
        
        base_token = symbol.replace('USDT', '').replace('_', '').replace('BTC', '').replace('ETH', '').replace('USDC', '')
        if not base_token:
            base_token = symbol[:3]
        
        market_icon = "🔮" if market_type == "Futures" else "💱"
        
        candle_status = "CLOSED" if is_closed else "LIVE"
        
        if signal_type == "pump":
            header = f"🟢 [MEXC] ONE-CANDLE PUMP | {candle_status} | 🟢"
            change_icon = "📈"
            change_str = f"+{change:.2f}%"
        else:
            header = f"🔴 [MEXC] ONE-CANDLE DUMP | {candle_status} | 🔴"
            change_icon = "📉"
            change_str = f"{change:.2f}%"
        
        if impulse_series == 1:
            series_text = "1 импульсная свеча"
        elif impulse_series < 5:
            series_text = f"{impulse_series} импульсных свечи"
        else:
            series_text = f"{impulse_series} импульсных свечей"
        
        msg = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━
{header}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
{market_icon} Пара: {symbol} ({market_type})
⏱️ Таймфрейм: {tf}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Цена: {open_price} → {close_price}
{change_icon} Изменение: {change_str}
💰 Текущая цена: {current_price}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Объём свечи: {vol_candle} {base_token} (${vol_candle_usdt})
💵 Объём 24ч: ${vol_24h}
💧 Спред: {spread_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Контекст:
├ Пред. свеча: {prev_change:+.1f}%
└ Серия: {series_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ Ликвидность: {liq_score}%"""
        
        if data['market_type'] == 'futures' and funding is not None:
            msg += f"\n💰 Funding: {funding:+.4f}%"
        
        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━
👑 Admin: {ADMIN_LINK}"""
        
        return msg
    
    def set_timeframe(self, tf):
        if tf in self.tf_map:
            self.timeframe = self.tf_map[tf]
            self.timeframe_display = tf
            return True
        return False
    
    def get_volume_reliability(self, volume_24h):
        if volume_24h >= 10_000_000:
            return "🟢🟢🟢 Высокая"
        elif volume_24h >= 1_000_000:
            return "🟢🟢 Хорошая"
        elif volume_24h >= 100_000:
            return "🟢 Средняя"
        elif volume_24h >= 10_000:
            return "🟡 Низкая"
        else:
            return "🔴 Очень низкая"
    
    def get_top_movers(self, period="24h", limit=10, mode="gainers", progress_callback=None):
        results = []
        period_names = {
            "1m": "1 минуту", "5m": "5 минут", "15m": "15 минут",
            "30m": "30 минут", "1h": "1 час", "4h": "4 часа", "24h": "24 часа"
        }
        period_name = period_names.get(period, period)
        
        futures_tickers = self.get_futures_tickers() if self.market_type_filter in ["all", "futures"] else {}
        spot_tickers = self.get_spot_tickers() if self.market_type_filter in ["all", "spot"] else {}
        
        if period == "24h":
            for sym, data in futures_tickers.items():
                try:
                    change = float(data.get('riseFallRate', 0)) * 100
                    price = float(data.get('lastPrice', 0))
                    vol = float(data.get('volume24', 0)) * price
                    if self.min_volume_usdt > 0 and vol < self.min_volume_usdt:
                        continue
                    results.append({
                        'symbol': sym.replace('_', ''), 'type': 'futures', 'type_icon': '🔮',
                        'change': change, 'volume': vol, 'price': price,
                        'funding': self.funding_rates.get(sym), 'reliability': self.get_volume_reliability(vol)
                    })
                except:
                    continue
            
            for sym, data in spot_tickers.items():
                try:
                    change = float(data.get('priceChangePercent', 0))
                    vol = float(data.get('quoteVolume', 0) or 0)
                    price = float(data.get('lastPrice', 0) or 0)
                    if self.min_volume_usdt > 0 and vol < self.min_volume_usdt:
                        continue
                    results.append({
                        'symbol': sym, 'type': 'spot', 'type_icon': '💱',
                        'change': change, 'volume': vol, 'price': price,
                        'funding': None, 'reliability': self.get_volume_reliability(vol)
                    })
                except:
                    continue
        else:
            all_coins = []
            for sym, data in futures_tickers.items():
                try:
                    price = float(data.get('lastPrice', 0))
                    vol = float(data.get('volume24', 0)) * price
                    if self.min_volume_usdt > 0 and vol < self.min_volume_usdt:
                        continue
                    all_coins.append({'symbol': sym, 'display': sym.replace('_', ''), 'type': 'futures',
                                     'volume': vol, 'price': price, 'funding': self.funding_rates.get(sym)})
                except:
                    continue
            
            for sym, data in spot_tickers.items():
                try:
                    vol = float(data.get('quoteVolume', 0) or 0)
                    price = float(data.get('lastPrice', 0) or 0)
                    if self.min_volume_usdt > 0 and vol < self.min_volume_usdt:
                        continue
                    all_coins.append({'symbol': sym, 'display': sym, 'type': 'spot',
                                     'volume': vol, 'price': price, 'funding': None})
                except:
                    continue
            
            if progress_callback:
                progress_callback(f"📊 Анализ {len(all_coins)} монет за {period_name}...")
            
            def analyze(coin):
                try:
                    r = self.get_change_for_period(coin['symbol'], coin['type'], period)
                    if r:
                        return {
                            'symbol': coin['display'], 'type': coin['type'],
                            'type_icon': '🔮' if coin['type'] == 'futures' else '💱',
                            'change': r['change'], 'volume': coin['volume'], 'price': coin['price'],
                            'funding': coin['funding'], 'reliability': self.get_volume_reliability(coin['volume'])
                        }
                except:
                    pass
                return None
            
            with ThreadPoolExecutor(max_workers=100) as ex:
                for r in ex.map(analyze, all_coins):
                    if r:
                        results.append(r)
        
        if mode == "gainers":
            results = [r for r in results if r['change'] > 0]
            results.sort(key=lambda x: x['change'], reverse=True)
        else:
            results = [r for r in results if r['change'] < 0]
            results.sort(key=lambda x: x['change'])
        
        return results[:limit], period_name
    
    def scan(self):
        now = datetime.now().strftime('%H:%M:%S')
        mode_names = {"pump": "PUMP", "dump": "DUMP", "both": "PUMP+DUMP"}
        candle_names = {"current": "LIVE", "closed": "CLOSED", "both": "ALL"}
        
        all_symbols = self.get_all_symbols()
        if not all_symbols:
            print(f"[{now}] ❌ Нет пар")
            return
        
        fut = len([s for s in all_symbols if s['type'] == 'futures'])
        spot = len([s for s in all_symbols if s['type'] == 'spot'])
        print(f"[{now}] 🔍 {self.timeframe_display} | {mode_names[self.signal_mode]} | {candle_names[self.candle_mode]} | 🔮{fut} 💱{spot} | Total: {len(all_symbols)}")
        
        futures_tickers = self.get_futures_tickers() if self.market_type_filter in ["all", "futures"] else {}
        spot_tickers = self.get_spot_tickers() if self.market_type_filter in ["all", "spot"] else {}
        
        signals = []
        errors = [0]
        
        def analyze(sym):
            try:
                return self.analyze_symbol(sym, futures_tickers, spot_tickers)
            except:
                errors[0] += 1
                return None
        
        with ThreadPoolExecutor(max_workers=50) as ex:
            for result in ex.map(analyze, all_symbols):
                if result:
                    for signal in result:
                        if self.should_send_alert(signal['symbol'], signal['candle_time'], signal['is_closed']):
                            signals.append(signal)
        
        signals.sort(key=lambda x: abs(x['change_percent']), reverse=True)
        
        for signal in signals:
            msg = self.format_alert(signal)
            icon = "🚀" if signal['signal_type'] == 'pump' else "💥"
            status = "|LIVE|" if not signal['is_closed'] else "|CLOSED|"
            change_str = f"+{signal['change_percent']:.2f}%" if signal['signal_type'] == 'pump' else f"{signal['change_percent']:.2f}%"
            print(f"  {icon} {status} {signal['display_symbol']} {change_str}")
            
            if self.chat_id:
                self.send_telegram(self.chat_id, msg)
                time.sleep(0.03)
        
        pumps = len([s for s in signals if s['signal_type'] == 'pump'])
        dumps = len([s for s in signals if s['signal_type'] == 'dump'])
        print(f"  ✅ 🚀{pumps} 💥{dumps} ❌{errors[0]}")
        
        if len(self.sent_alerts) > 5000:
            ct = time.time()
            self.sent_alerts = {k: v for k, v in self.sent_alerts.items() 
                               if isinstance(v, tuple) and (ct - v[0]) < 3600}


class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.screener = MEXCFullScreener(self.send_message)
        self.running = False
        self.screener_thread = None
        self.waiting_for_input = {}
        self.top_mode = None
        self.last_menu_message = {}
        
        # Защита от дублирования
        self.processed_updates = set()
        self.processed_messages = {}
        self.max_processed_updates = 10000
        self.update_lock = threading.Lock()
        
    def is_duplicate(self, update_id, chat_id, message_id):
        with self.update_lock:
            if update_id in self.processed_updates:
                return True
            
            if chat_id in self.processed_messages:
                if message_id in self.processed_messages[chat_id]:
                    return True
            
            self.processed_updates.add(update_id)
            
            if chat_id not in self.processed_messages:
                self.processed_messages[chat_id] = set()
            self.processed_messages[chat_id].add(message_id)
            
            if len(self.processed_updates) > self.max_processed_updates:
                sorted_updates = sorted(self.processed_updates)
                updates_to_remove = sorted_updates[:len(sorted_updates)//2]
                for uid in updates_to_remove:
                    self.processed_updates.discard(uid)
            
            for cid in list(self.processed_messages.keys()):
                if len(self.processed_messages[cid]) > 1000:
                    sorted_msgs = sorted(self.processed_messages[cid])
                    self.processed_messages[cid] = set(sorted_msgs[-500:])
            
            return False
        
    def send_message(self, chat_id, text, reply_markup=None):
        try:
            data = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup)
            response = requests.post(f"{self.base_url}/sendMessage", data=data, timeout=10)
            return response.json()
        except:
            return None
    
    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        try:
            data = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'disable_web_page_preview': True}
            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup)
            response = requests.post(f"{self.base_url}/editMessageText", data=data, timeout=10)
            return response.json()
        except:
            return None
    
    def send_or_edit(self, chat_id, text, reply_markup=None, setting_key=None):
        if setting_key and chat_id in self.last_menu_message:
            msg_id = self.last_menu_message[chat_id].get(setting_key)
            if msg_id:
                result = self.edit_message(chat_id, msg_id, text, reply_markup)
                if result and result.get('ok'):
                    return result
        
        result = self.send_message(chat_id, text, reply_markup)
        if result and result.get('ok') and setting_key:
            if chat_id not in self.last_menu_message:
                self.last_menu_message[chat_id] = {}
            self.last_menu_message[chat_id][setting_key] = result['result']['message_id']
        return result
    
    def get_main_keyboard(self):
        return {"keyboard": [
            [{"text": "🚀 Старт"}, {"text": "🛑 Стоп"}, {"text": "📊 Статус"}],
            [{"text": "🔥 ТОП"}, {"text": "📋 Пары"}, {"text": "⚙️ Настройки"}]
        ], "resize_keyboard": True}
    
    def get_top_mode_keyboard(self):
        return {"keyboard": [
            [{"text": "📈 ТОП Роста"}],
            [{"text": "📉 ТОП Падения"}],
            [{"text": "🔙 Главное меню"}]
        ], "resize_keyboard": True}
    
    def get_top_period_keyboard(self):
        return {"keyboard": [
            [{"text": "⏱ 1m"}, {"text": "⏱ 5m"}, {"text": "⏱ 15m"}],
            [{"text": "⏱ 30m"}, {"text": "⏱ 1h"}, {"text": "⏱ 4h"}],
            [{"text": "⏱ 24h"}, {"text": "🔙 Назад"}]
        ], "resize_keyboard": True}
    
    def get_settings_keyboard(self):
        return {"keyboard": [
            [{"text": "⏱ Таймфрейм"}, {"text": "💹 Мин. процент"}],
            [{"text": "🎯 Режим сигналов"}, {"text": "🕯 Режим свечей"}],
            [{"text": "🏪 Тип рынка"}, {"text": "💰 Мин. объём"}],
            [{"text": "🔄 Дубликаты"}, {"text": "⏰ Кулдаун"}, {"text": "⚡ Скорость"}],
            [{"text": "💱 Quote фильтр"}, {"text": "🔙 Главное меню"}]
        ], "resize_keyboard": True}
    
    def get_quote_filter_keyboard(self):
        c = self.screener.spot_quote_filter
        return {"keyboard": [
            [{"text": f"{'✅' if c == 'all' else '⬜'} 🌐 Все пары"}],
            [{"text": f"{'✅' if c == 'usdt' else '⬜'} 💵 Только USDT"}],
            [{"text": f"{'✅' if c == 'btc' else '⬜'} 🟠 Только BTC"}],
            [{"text": f"{'✅' if c == 'eth' else '⬜'} 🔷 Только ETH"}],
            [{"text": f"{'✅' if c == 'usdc' else '⬜'} 💲 Только USDC"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_signal_mode_keyboard(self):
        c = self.screener.signal_mode
        return {"keyboard": [
            [{"text": f"{'✅' if c == 'pump' else '⬜'} 🚀 Только PUMP"}],
            [{"text": f"{'✅' if c == 'dump' else '⬜'} 💥 Только DUMP"}],
            [{"text": f"{'✅' if c == 'both' else '⬜'} 📊 PUMP + DUMP"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_candle_mode_keyboard(self):
        c = self.screener.candle_mode
        return {"keyboard": [
            [{"text": f"{'✅' if c == 'current' else '⬜'} 🟡 Текущая |LIVE|"}],
            [{"text": f"{'✅' if c == 'closed' else '⬜'} ✅ Закрытая |CLOSED|"}],
            [{"text": f"{'✅' if c == 'both' else '⬜'} 📊 Обе"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_speed_keyboard(self):
        c = self.screener.scan_interval
        return {"keyboard": [
            [{"text": f"{'✅' if c == 3 else '⬜'} ⚡ 3 сек"}, {"text": f"{'✅' if c == 5 else '⬜'} ⚡ 5 сек"}],
            [{"text": f"{'✅' if c == 10 else '⬜'} ⚡ 10 сек"}, {"text": f"{'✅' if c == 15 else '⬜'} ⚡ 15 сек"}],
            [{"text": f"{'✅' if c == 30 else '⬜'} ⚡ 30 сек"}, {"text": f"{'✅' if c == 60 else '⬜'} ⚡ 60 сек"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_timeframe_keyboard(self):
        return {"keyboard": [
            [{"text": "🕐 1m"}, {"text": "🕐 5m"}, {"text": "🕐 15m"}],
            [{"text": "🕐 30m"}, {"text": "🕐 1h"}, {"text": "🕐 4h"}],
            [{"text": "🕐 1d"}, {"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_percent_keyboard(self):
        return {"keyboard": [
            [{"text": "📊 0.5%"}, {"text": "📊 1%"}, {"text": "📊 2%"}],
            [{"text": "📊 3%"}, {"text": "📊 5%"}, {"text": "📊 10%"}],
            [{"text": "📊 15%"}, {"text": "📊 20%"}, {"text": "✏️ Свой %"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_market_keyboard(self):
        c = self.screener.market_type_filter
        return {"keyboard": [
            [{"text": f"{'✅' if c == 'all' else '⬜'} 🌐 Все рынки"}],
            [{"text": f"{'✅' if c == 'futures' else '⬜'} 🔮 Только Фьючерсы"}],
            [{"text": f"{'✅' if c == 'spot' else '⬜'} 💱 Только Спот"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_volume_keyboard(self):
        return {"keyboard": [
            [{"text": "💵 Без фильтра"}, {"text": "💵 $1K+"}],
            [{"text": "💵 $10K+"}, {"text": "💵 $50K+"}],
            [{"text": "💵 $100K+"}, {"text": "💵 $500K+"}],
            [{"text": "💵 $1M+"}, {"text": "✏️ Свой объём"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_duplicates_keyboard(self):
        return {"keyboard": [
            [{"text": "✅ Дубли ВКЛ"}, {"text": "❌ Дубли ВЫКЛ"}],
            [{"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def get_cooldown_keyboard(self):
        return {"keyboard": [
            [{"text": "🔔 0с"}, {"text": "🔔 15с"}, {"text": "🔔 30с"}],
            [{"text": "🔔 60с"}, {"text": "🔔 120с"}, {"text": "🔔 300с"}],
            [{"text": "✏️ Свой КД"}, {"text": "🔙 Настройки"}]
        ], "resize_keyboard": True}
    
    def show_status(self, chat_id):
        s = self.screener
        fut = len(s.futures_symbols)
        spot = len(s.spot_symbols)
        active = len(s.get_all_symbols())
        
        filter_names = {"all": "Все", "futures": "FUTURES", "spot": "SPOT"}
        mode_names = {"pump": "🚀 Только PUMP", "dump": "💥 Только DUMP", "both": "📊 PUMP + DUMP"}
        candle_names = {"current": "🟡 Текущая |LIVE|", "closed": "✅ Закрытая |CLOSED|", "both": "📊 Обе"}
        quote_names = {"all": "Все", "usdt": "USDT", "btc": "BTC", "eth": "ETH", "usdc": "USDC"}
        vol_filter = f"${s.format_number(s.min_volume_usdt)}" if s.min_volume_usdt > 0 else "Выкл"
        
        msg = f"""📊 СТАТУС СКРИНЕРА
━━━━━━━━━━━━━━━━━━━━━━━━
{"🟢 РАБОТАЕТ" if self.running else "🔴 ОСТАНОВЛЕН"}
━━━━━━━━━━━━━━━━━━━━━━━━

⚙️ НАСТРОЙКИ:
├ ⏱ Таймфрейм: {s.timeframe_display}
├ 🎯 Режим: {mode_names[s.signal_mode]}
├ 🕯 Свеча: {candle_names[s.candle_mode]}
├ 📊 Мин. изменение: {s.min_pump}%
├ 🏪 Рынок: {filter_names[s.market_type_filter]}
├ 💱 Quote: {quote_names[s.spot_quote_filter]}
├ 💰 Мин. объём: {vol_filter}
├ 🔄 Дубликаты: {"ВКЛ" if s.allow_duplicates else "ВЫКЛ"}
├ ⏰ Кулдаун: {s.alert_cooldown}с
└ ⚡ Скорость скана: {s.scan_interval}с

📊 ПАРЫ:
├ 🔮 Деривативов: {fut}
├ 💱 Спот: {spot}
├ 📊 Всего: {fut + spot}
└ 🎯 Активных: {active}

🔔 Алертов в памяти: {len(s.sent_alerts)}
━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        self.send_message(chat_id, msg, self.get_main_keyboard())
    
    def show_settings(self, chat_id):
        s = self.screener
        filter_names = {"all": "Все", "futures": "FUTURES", "spot": "SPOT"}
        mode_names = {"pump": "🚀 PUMP", "dump": "💥 DUMP", "both": "📊 PUMP+DUMP"}
        candle_names = {"current": "🟡 |LIVE|", "closed": "✅ |CLOSED|", "both": "📊 ОБЕ"}
        quote_names = {"all": "Все", "usdt": "USDT", "btc": "BTC", "eth": "ETH", "usdc": "USDC"}
        vol_filter = f"${s.format_number(s.min_volume_usdt)}" if s.min_volume_usdt > 0 else "Выкл"
        
        msg = f"""⚙️ НАСТРОЙКИ
━━━━━━━━━━━━━━━━━━━━━━━━

📋 Текущие значения:
├ ⏱ Таймфрейм: {s.timeframe_display}
├ 💹 Мин. изменение: {s.min_pump}%
├ 🎯 Сигналы: {mode_names[s.signal_mode]}
├ 🕯 Свеча: {candle_names[s.candle_mode]}
├ 🏪 Рынок: {filter_names[s.market_type_filter]}
├ 💱 Quote: {quote_names[s.spot_quote_filter]}
├ 💰 Мин. объём: {vol_filter}
├ 🔄 Дубликаты: {"ВКЛ" if s.allow_duplicates else "ВЫКЛ"}
├ ⏰ Кулдаун: {s.alert_cooldown}с
└ ⚡ Скорость: {s.scan_interval}с

Выберите параметр для изменения:
━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        self.send_or_edit(chat_id, msg, self.get_settings_keyboard(), "settings")
    
    def show_top(self, chat_id, period="24h"):
        def progress_callback(text):
            self.send_message(chat_id, text)
        
        mode_name = "📈 РОСТ" if self.top_mode == "gainers" else "📉 ПАДЕНИЕ"
        self.send_message(chat_id, f"⚡ Загрузка {mode_name} за {period}...")
        
        self.screener.funding_rates = self.screener.get_funding_rates()
        top, period_name = self.screener.get_top_movers(period, 10, self.top_mode, progress_callback)
        
        if not top:
            self.send_message(chat_id, "❌ Нет данных", self.get_top_period_keyboard())
            return
        
        filter_names = {"all": "Все", "futures": "FUTURES", "spot": "SPOT"}
        vol_filter = f">${self.screener.format_number(self.screener.min_volume_usdt)}" if self.screener.min_volume_usdt > 0 else "Без фильтра"
        
        if self.top_mode == "gainers":
            header = "🚀 ТОП-10 РОСТ"
            medals = ["🥇", "🥈", "🥉"]
        else:
            header = "💥 ТОП-10 ПАДЕНИЕ"
            medals = ["💀", "☠️", "👻"]
        
        msg = f"""{header} за {period_name}
━━━━━━━━━━━━━━━━━━━━━━━━
📊 Рынок: {filter_names[self.screener.market_type_filter]}
💰 Мин. объём: {vol_filter}
━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        for i, d in enumerate(top):
            vol = self.screener.format_number(d['volume'])
            price = self.screener.format_price(d['price'])
            
            if self.top_mode == "gainers":
                change_str = f"+{d['change']:.2f}%"
            else:
                change_str = f"{d['change']:.2f}%"
            
            if i < 3:
                medal = medals[i]
                msg += f"""{medal} {d['type_icon']} {d['symbol']}
   {change_str} | ${vol}
   {d['reliability']}
"""
                if d['funding'] is not None:
                    msg += f"   💰 Funding: {d['funding']:+.4f}%\n"
                msg += "\n"
            else:
                funding_txt = f" | F:{d['funding']:+.3f}%" if d['funding'] else ""
                msg += f"{i+1}. {d['type_icon']} {d['symbol']} {change_str} | ${vol}{funding_txt}\n"
        
        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━
👑 Admin: {ADMIN_LINK}"""
        
        self.send_message(chat_id, msg, self.get_top_period_keyboard())
    
    def show_pairs(self, chat_id):
        self.send_message(chat_id, "⚡ Загрузка ВСЕХ пар...")
        
        old_filter = self.screener.market_type_filter
        old_quote = self.screener.spot_quote_filter
        
        self.screener.market_type_filter = "all"
        self.screener.spot_quote_filter = "all"
        self.screener.get_all_symbols(force_reload=True)
        
        self.screener.market_type_filter = old_filter
        self.screener.spot_quote_filter = old_quote
        
        fut = len(self.screener.futures_symbols)
        spot = len(self.screener.spot_symbols)
        active = len(self.screener.get_all_symbols())
        
        filter_names = {"all": "Все", "futures": "Только FUTURES", "spot": "Только SPOT"}
        quote_names = {"all": "Все", "usdt": "USDT", "btc": "BTC", "eth": "ETH", "usdc": "USDC"}
        
        msg = f"""📊 ТОРГОВЫЕ ПАРЫ MEXC
━━━━━━━━━━━━━━━━━━━━━━━━
🔮 Деривативы (Futures+SWAP): {fut}
💱 Спот (все пары): {spot}
━━━━━━━━━━━━━━━━━━━━━━━━
📊 ВСЕГО: {fut + spot} пар
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Фильтр рынка: {filter_names[self.screener.market_type_filter]}
💱 Фильтр Quote: {quote_names[self.screener.spot_quote_filter]}
📌 Активных для скана: {active}
━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        self.send_message(chat_id, msg, self.get_main_keyboard())
    
    def handle(self, update):
        update_id = update.get('update_id', 0)
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id', 0)
        message_id = message.get('message_id', 0)
        text = message.get('text', '').strip()
        
        if self.is_duplicate(update_id, chat_id, message_id):
            return
        
        self.screener.chat_id = chat_id
        
        if chat_id in self.waiting_for_input:
            inp = self.waiting_for_input.pop(chat_id)
            
            if inp == 'percent':
                try:
                    v = float(text.replace('%', '').replace(',', '.'))
                    if 0 < v <= 100:
                        self.screener.min_pump = self.screener.min_dump = v
                        self.send_or_edit(chat_id, f"✅ Мин. изменение: {v}%", self.get_percent_keyboard(), "percent")
                    else:
                        self.send_message(chat_id, "❌ Введите от 0.1 до 100", self.get_percent_keyboard())
                except:
                    self.send_message(chat_id, "❌ Неверный формат", self.get_percent_keyboard())
                return
            
            elif inp == 'volume':
                try:
                    t = text.upper().replace('$', '').replace(' ', '')
                    m = 1
                    if t.endswith('K'):
                        m = 1000
                        t = t[:-1]
                    elif t.endswith('M'):
                        m = 1000000
                        t = t[:-1]
                    v = float(t.replace(',', '.')) * m
                    self.screener.min_volume_usdt = v
                    self.send_or_edit(chat_id, f"✅ Мин. объём: ${self.screener.format_number(v)}", self.get_volume_keyboard(), "volume")
                except:
                    self.send_message(chat_id, "❌ Примеры: 5000, 50K, 1M", self.get_volume_keyboard())
                return
            
            elif inp == 'cooldown':
                try:
                    v = int(text.replace('с', '').replace('s', ''))
                    if 0 <= v <= 3600:
                        self.screener.alert_cooldown = v
                        self.send_or_edit(chat_id, f"✅ Кулдаун: {v}с", self.get_cooldown_keyboard(), "cooldown")
                    else:
                        self.send_message(chat_id, "❌ От 0 до 3600", self.get_cooldown_keyboard())
                except:
                    self.send_message(chat_id, "❌ Введите число", self.get_cooldown_keyboard())
                return
        
        if text in ['/start', '/help']:
            msg = f"""KING |PUMP/DUMP|
━━━━━━━━━━━━━━━━━━━━━━━━
🔮 Фьючерсы + SWAP + 💱 Спот
🚀 PUMP + 💥 DUMP мониторинг
🟡 |LIVE| + ✅ |CLOSED| свечи
━━━━━━━━━━━━━━━━━━━━━━━━

🚀 Старт - запуск скринера
🛑 Стоп - остановка
📊 Статус - текущее состояние
🔥 ТОП - лидеры роста/падения
📋 Пары - все торговые пары
⚙️ Настройки - параметры

━━━━━━━━━━━━━━━━━━━━━━━━
👑 Admin: {ADMIN_LINK}"""
            self.send_message(chat_id, msg, self.get_main_keyboard())
            
        elif text == "🚀 Старт":
            if not self.running:
                self.running = True
                self.screener.chat_id = chat_id
                self.screener_thread = threading.Thread(target=self.loop, daemon=True)
                self.screener_thread.start()
                
                mode_names = {"pump": "🚀 PUMP", "dump": "💥 DUMP", "both": "📊 PUMP+DUMP"}
                candle_names = {"current": "🟡 |LIVE|", "closed": "✅ |CLOSED|", "both": "📊 ОБЕ"}
                filter_names = {"all": "Все", "futures": "FUTURES", "spot": "SPOT"}
                vol_filter = f"${self.screener.format_number(self.screener.min_volume_usdt)}" if self.screener.min_volume_usdt > 0 else "Выкл"
                
                msg = f"""✅ СКРИНЕР ЗАПУЩЕН!
━━━━━━━━━━━━━━━━━━━━━━━━
⏱ Таймфрейм: {self.screener.timeframe_display}
🎯 Режим: {mode_names[self.screener.signal_mode]}
🕯 Свеча: {candle_names[self.screener.candle_mode]}
📊 Мин: {self.screener.min_pump}%
🏪 Рынок: {filter_names[self.screener.market_type_filter]}
💰 Объём: {vol_filter}
⚡ Скорость: {self.screener.scan_interval}с
━━━━━━━━━━━━━━━━━━━━━━━━"""
                self.send_message(chat_id, msg, self.get_main_keyboard())
            else:
                self.send_message(chat_id, "⚠️ Скринер уже работает", self.get_main_keyboard())
                
        elif text == "🛑 Стоп":
            self.running = False
            self.send_message(chat_id, "🛑 Скринер остановлен", self.get_main_keyboard())
            
        elif text == "📊 Статус":
            self.show_status(chat_id)
            
        elif text == "🔥 ТОП":
            self.top_mode = None
            self.send_message(chat_id, "🔥 Выберите тип ТОПа:", self.get_top_mode_keyboard())
        
        elif text == "📈 ТОП Роста":
            self.top_mode = "gainers"
            self.send_message(chat_id, "✅ Режим: 📈 ТОП РОСТА\n\nВыберите период:", self.get_top_period_keyboard())
        
        elif text == "📉 ТОП Падения":
            self.top_mode = "losers"
            self.send_message(chat_id, "✅ Режим: 📉 ТОП ПАДЕНИЯ\n\nВыберите период:", self.get_top_period_keyboard())
        
        elif text == "🔙 Назад":
            self.top_mode = None
            self.send_message(chat_id, "🔥 Выберите тип ТОПа:", self.get_top_mode_keyboard())
        
        elif text.startswith("⏱ ") and text[2:] in ["1m", "5m", "15m", "30m", "1h", "4h", "24h"]:
            if self.top_mode:
                threading.Thread(target=self.show_top, args=(chat_id, text[2:]), daemon=True).start()
            else:
                self.send_message(chat_id, "❌ Сначала выберите тип ТОПа", self.get_top_mode_keyboard())
            
        elif text == "📋 Пары":
            threading.Thread(target=self.show_pairs, args=(chat_id,), daemon=True).start()
            
        elif text == "⚙️ Настройки":
            self.show_settings(chat_id)
            
        elif text == "🔙 Главное меню":
            self.top_mode = None
            self.send_message(chat_id, "🏠 Главное меню", self.get_main_keyboard())
            
        elif text == "🔙 Настройки":
            self.show_settings(chat_id)
        
        elif text == "💱 Quote фильтр":
            quote_names = {"all": "Все", "usdt": "USDT", "btc": "BTC", "eth": "ETH", "usdc": "USDC"}
            self.send_or_edit(chat_id, f"💱 Текущий: {quote_names[self.screener.spot_quote_filter]}\n\nФильтр для спот пар:", self.get_quote_filter_keyboard(), "quote")
        
        elif "🌐 Все пары" in text:
            self.screener.spot_quote_filter = "all"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Quote: 🌐 Все пары", self.get_quote_filter_keyboard(), "quote")
        
        elif "💵 Только USDT" in text:
            self.screener.spot_quote_filter = "usdt"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Quote: 💵 Только USDT", self.get_quote_filter_keyboard(), "quote")
        
        elif "🟠 Только BTC" in text:
            self.screener.spot_quote_filter = "btc"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Quote: 🟠 Только BTC", self.get_quote_filter_keyboard(), "quote")
        
        elif "🔷 Только ETH" in text:
            self.screener.spot_quote_filter = "eth"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Quote: 🔷 Только ETH", self.get_quote_filter_keyboard(), "quote")
        
        elif "💲 Только USDC" in text:
            self.screener.spot_quote_filter = "usdc"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Quote: 💲 Только USDC", self.get_quote_filter_keyboard(), "quote")
        
        elif text == "🎯 Режим сигналов":
            mode_names = {"pump": "🚀 PUMP", "dump": "💥 DUMP", "both": "📊 PUMP+DUMP"}
            self.send_or_edit(chat_id, f"🎯 Текущий: {mode_names[self.screener.signal_mode]}\n\nВыберите режим:", self.get_signal_mode_keyboard(), "signal_mode")
        
        elif "🚀 Только PUMP" in text:
            self.screener.signal_mode = "pump"
            self.send_or_edit(chat_id, "✅ Режим: 🚀 Только PUMP", self.get_signal_mode_keyboard(), "signal_mode")
        
        elif "💥 Только DUMP" in text:
            self.screener.signal_mode = "dump"
            self.send_or_edit(chat_id, "✅ Режим: 💥 Только DUMP", self.get_signal_mode_keyboard(), "signal_mode")
        
        elif "📊 PUMP + DUMP" in text:
            self.screener.signal_mode = "both"
            self.send_or_edit(chat_id, "✅ Режим: 📊 PUMP + DUMP", self.get_signal_mode_keyboard(), "signal_mode")
        
        elif text == "🕯 Режим свечей":
            candle_names = {"current": "🟡 |LIVE|", "closed": "✅ |CLOSED|", "both": "📊 ОБЕ"}
            self.send_or_edit(chat_id, f"🕯 Текущий: {candle_names[self.screener.candle_mode]}\n\nВыберите:", self.get_candle_mode_keyboard(), "candle_mode")
        
        elif "🟡 Текущая |LIVE|" in text:
            self.screener.candle_mode = "current"
            self.send_or_edit(chat_id, "✅ Свеча: 🟡 Текущая |LIVE|", self.get_candle_mode_keyboard(), "candle_mode")
        
        elif "✅ Закрытая |CLOSED|" in text:
            self.screener.candle_mode = "closed"
            self.send_or_edit(chat_id, "✅ Свеча: ✅ Закрытая |CLOSED|", self.get_candle_mode_keyboard(), "candle_mode")
        
        elif "📊 Обе" in text and "PUMP" not in text:
            self.screener.candle_mode = "both"
            self.send_or_edit(chat_id, "✅ Свеча: 📊 Обе", self.get_candle_mode_keyboard(), "candle_mode")
        
        elif text == "⚡ Скорость":
            self.send_or_edit(chat_id, f"⚡ Текущая: {self.screener.scan_interval}с\n\nВыберите интервал сканирования:", self.get_speed_keyboard(), "speed")
        
        elif "⚡ " in text and "сек" in text:
            try:
                v = int(text.replace("✅ ", "").replace("⬜ ", "").replace("⚡ ", "").replace(" сек", ""))
                self.screener.scan_interval = v
                self.send_or_edit(chat_id, f"✅ Скорость: {v} сек", self.get_speed_keyboard(), "speed")
            except:
                pass
        
        elif text == "⏱ Таймфрейм":
            self.send_or_edit(chat_id, f"⏱ Текущий: {self.screener.timeframe_display}\n\nВыберите:", self.get_timeframe_keyboard(), "timeframe")
        
        elif text.startswith("🕐 "):
            tf = text[2:].strip()
            if self.screener.set_timeframe(tf):
                self.send_or_edit(chat_id, f"✅ Таймфрейм: {tf}", self.get_timeframe_keyboard(), "timeframe")
        
        elif text == "💹 Мин. процент":
            self.send_or_edit(chat_id, f"📊 Текущий: {self.screener.min_pump}%\n\nВыберите или введите свой:", self.get_percent_keyboard(), "percent")
        
        elif text.startswith("📊 ") and "%" in text:
            try:
                v = float(text[2:].replace("%", "").strip())
                self.screener.min_pump = self.screener.min_dump = v
                self.send_or_edit(chat_id, f"✅ Мин. изменение: {v}%", self.get_percent_keyboard(), "percent")
            except:
                pass
        
        elif text == "✏️ Свой %":
            self.waiting_for_input[chat_id] = 'percent'
            self.send_message(chat_id, "✏️ Введите минимальный процент (например: 2.5):", self.get_percent_keyboard())
        
        elif text == "🏪 Тип рынка":
            filter_names = {"all": "Все", "futures": "FUTURES", "spot": "SPOT"}
            self.send_or_edit(chat_id, f"🏪 Текущий: {filter_names[self.screener.market_type_filter]}\n\nВыберите:", self.get_market_keyboard(), "market")
        
        elif "🌐 Все рынки" in text:
            self.screener.market_type_filter = "all"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Рынок: 🌐 Все (Futures + Spot)", self.get_market_keyboard(), "market")
        
        elif "🔮 Только Фьючерсы" in text:
            self.screener.market_type_filter = "futures"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Рынок: 🔮 Только Фьючерсы", self.get_market_keyboard(), "market")
        
        elif "💱 Только Спот" in text:
            self.screener.market_type_filter = "spot"
            self.screener.last_update = 0
            self.send_or_edit(chat_id, "✅ Рынок: 💱 Только Спот", self.get_market_keyboard(), "market")
        
        elif text == "💰 Мин. объём":
            vol = f"${self.screener.format_number(self.screener.min_volume_usdt)}" if self.screener.min_volume_usdt > 0 else "Выключен"
            self.send_or_edit(chat_id, f"💰 Текущий: {vol}\n\nВыберите или введите свой:", self.get_volume_keyboard(), "volume")
        
        elif text == "💵 Без фильтра":
            self.screener.min_volume_usdt = 0
            self.send_or_edit(chat_id, "✅ Фильтр по объёму выключен", self.get_volume_keyboard(), "volume")
        
        elif text.startswith("💵 $") and "+" in text:
            try:
                t = text[3:].replace("+", "").upper().strip()
                m = 1
                if t.endswith("K"):
                    m = 1000
                    t = t[:-1]
                elif t.endswith("M"):
                    m = 1000000
                    t = t[:-1]
                v = float(t) * m
                self.screener.min_volume_usdt = v
                self.send_or_edit(chat_id, f"✅ Мин. объём: ${self.screener.format_number(v)}", self.get_volume_keyboard(), "volume")
            except:
                pass
        
        elif text == "✏️ Свой объём":
            self.waiting_for_input[chat_id] = 'volume'
            self.send_message(chat_id, "✏️ Введите минимальный объём (примеры: 5000, 50K, 1M):", self.get_volume_keyboard())
        
        elif text == "🔄 Дубликаты":
            status = "ВКЛ" if self.screener.allow_duplicates else "ВЫКЛ"
            self.send_or_edit(chat_id, f"🔄 Текущий: {status}\n\nВыберите:", self.get_duplicates_keyboard(), "duplicates")
        
        elif text == "✅ Дубли ВКЛ":
            self.screener.allow_duplicates = True
            self.send_or_edit(chat_id, "✅ Дубликаты: ВКЛ", self.get_duplicates_keyboard(), "duplicates")
        
        elif text == "❌ Дубли ВЫКЛ":
            self.screener.allow_duplicates = False
            self.send_or_edit(chat_id, "✅ Дубликаты: ВЫКЛ", self.get_duplicates_keyboard(), "duplicates")
        
        elif text == "⏰ Кулдаун":
            self.send_or_edit(chat_id, f"⏰ Текущий: {self.screener.alert_cooldown}с\n\nВыберите или введите свой:", self.get_cooldown_keyboard(), "cooldown")
        
        elif text.startswith("🔔 ") and "с" in text:
            try:
                v = int(text[2:].replace("с", "").strip())
                self.screener.alert_cooldown = v
                self.send_or_edit(chat_id, f"✅ Кулдаун: {v}с", self.get_cooldown_keyboard(), "cooldown")
            except:
                pass
        
        elif text == "✏️ Свой КД":
            self.waiting_for_input[chat_id] = 'cooldown'
            self.send_message(chat_id, "✏️ Введите кулдаун в секундах (0-3600):", self.get_cooldown_keyboard())
    
    def loop(self):
        while self.running:
            try:
                self.screener.scan()
                time.sleep(self.screener.scan_interval)
            except Exception as e:
                print(f"❌ Loop error: {e}")
                time.sleep(5)
    
    def run(self):
        print("=" * 60)
        print("🚀 MEXC FULL SCREENER v5.5")
        print("🔮 ALL Futures + SWAP + 💱 ALL Spot")
        print("🚀 PUMP + 💥 DUMP | 🟡 |LIVE| + ✅ |CLOSED|")
        print("=" * 60)
        
        offset = None
        while True:
            try:
                params = {'timeout': 30, 'allowed_updates': ['message']}
                if offset:
                    params['offset'] = offset
                
                r = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=35)
                updates = r.json()
                
                if updates.get('ok'):
                    for u in updates.get('result', []):
                        offset = u['update_id'] + 1
                        if 'message' in u:
                            try:
                                self.handle(u)
                            except Exception as e:
                                print(f"❌ Handle error: {e}")
            except Exception as e:
                print(f"❌ Polling error: {e}")
                time.sleep(5)


if __name__ == "__main__":
    TelegramBot().run()
