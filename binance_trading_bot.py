import os
import logging
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')

# Set up Binance client
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_symbol_info(symbol):
    exchange_info = client.futures_exchange_info()
    symbol_info = next(item for item in exchange_info['symbols'] if item['symbol'] == symbol)
    return symbol_info

def round_step_size(quantity, step_size):
    return round(quantity - (quantity % step_size), 8)

def place_market_order(symbol, side, quantity, leverage, position_side):
    symbol_info = get_symbol_info(symbol)
    step_size = float(next(filter(lambda f: f['filterType'] == 'LOT_SIZE', symbol_info['filters']))['stepSize'])
    quantity = round_step_size(quantity, step_size)

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity,
            positionSide=position_side
        )
        return order
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise

def place_limit_order(symbol, side, quantity, price, leverage, position_side):
    symbol_info = get_symbol_info(symbol)
    step_size = float(next(filter(lambda f: f['filterType'] == 'LOT_SIZE', symbol_info['filters']))['stepSize'])
    tick_size = float(next(filter(lambda f: f['filterType'] == 'PRICE_FILTER', symbol_info['filters']))['tickSize'])
    quantity = round_step_size(quantity, step_size)
    price = round_step_size(price, tick_size)

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=price,
            timeInForce=TIME_IN_FORCE_GTC,
            positionSide=position_side
        )
        return order
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise

def set_take_profit(symbol, side, quantity, price, position_side):
    symbol_info = get_symbol_info(symbol)
    tick_size = float(next(filter(lambda f: f['filterType'] == 'PRICE_FILTER', symbol_info['filters']))['tickSize'])
    price = round_step_size(price, tick_size)
    
    client.futures_create_order(
        symbol=symbol,
        side=side,
        type=ORDER_TYPE_TAKE_PROFIT,
        quantity=quantity,
        stopPrice=price,
        positionSide=position_side
    )

def set_stop_loss(symbol, side, quantity, price, position_side):
    symbol_info = get_symbol_info(symbol)
    tick_size = float(next(filter(lambda f: f['filterType'] == 'PRICE_FILTER', symbol_info['filters']))['tickSize'])
    price = round_step_size(price, tick_size)

    client.futures_create_order(
        symbol=symbol,
        side=side,
        type=ORDER_TYPE_STOP_MARKET,
        quantity=quantity,
        stopPrice=price,
        positionSide=position_side
    )

def get_order_price(order):
    if 'fills' in order and len(order['fills']) > 0:
        return float(order['fills'][0]['price'])
    else:
        order_info = client.futures_get_order(symbol=order['symbol'], orderId=order['orderId'])
        return float(order_info['avgPrice']) if 'avgPrice' in order_info else float(order_info['price'])

def main():
    while True:
        symbol = input("Enter the token symbol (e.g., BTCUSDT): ").upper()
        try:
            trade_type = input("Do you want to trade using USDT or a specific number of coins? (usdt/coins): ").lower()
            if trade_type == 'usdt':
                amount_usdt = float(input("Enter the amount in USDT you want to trade: "))
                leverage = int(input("Enter the leverage you want to use: "))
                symbol_info = get_symbol_info(symbol)
                mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                quantity = amount_usdt / mark_price
            elif trade_type == 'coins':
                quantity = float(input("Enter the number of coins you want to trade: "))
                leverage = int(input("Enter the leverage you want to use: "))
            else:
                print("Invalid trade type. Please enter 'usdt' or 'coins'.")
                continue

            limit_order_choice = input("Do you want to place a limit order? (yes/no): ").lower()

            if limit_order_choice == 'yes':
                limit_price = float(input("Enter the limit price: "))
                print(f"Waiting for {symbol} to reach the limit price of {limit_price}...")

                while True:
                    current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                    if current_price >= limit_price:
                        print(f"Limit price reached. Placing long and short orders for {symbol} with leverage {leverage}...")
                        long_order = place_limit_order(symbol, SIDE_BUY, quantity, limit_price, leverage, 'LONG')
                        short_order = place_limit_order(symbol, SIDE_SELL, quantity, limit_price, leverage, 'SHORT')
                        break
                    time.sleep(1)
            else:
                print(f"Placing market long and short orders for {symbol} with leverage {leverage}...")
                long_order = place_market_order(symbol, SIDE_BUY, quantity, leverage, 'LONG')
                short_order = place_market_order(symbol, SIDE_SELL, quantity, leverage, 'SHORT')

            long_price = get_order_price(long_order)
            short_price = get_order_price(short_order)

            print(f"Long order placed at {long_price}, short order placed at {short_price}")

            # Prompt for stop loss prices
            long_stop_loss_price = float(input("Enter the stop loss price for the long position: "))
            short_stop_loss_price = float(input("Enter the stop loss price for the short position: "))

            print(f"Setting stop loss for long position at {long_stop_loss_price} and short position at {short_stop_loss_price}")

            while True:
                current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                if current_price <= long_stop_loss_price or current_price >= short_stop_loss_price:
                    print(f"Stop loss price reached. Placing stop loss orders for {symbol}...")
                    if current_price <= long_stop_loss_price:
                        set_stop_loss(symbol, SIDE_SELL, quantity, long_stop_loss_price, 'LONG')
                    if current_price >= short_stop_loss_price:
                        set_stop_loss(symbol, SIDE_BUY, quantity, short_stop_loss_price, 'SHORT')
                    break
                time.sleep(1)

            # Monitor positions and set take profit if necessary
            while True:
                positions = client.futures_position_information(symbol=symbol)
                for position in positions:
                    if float(position['positionAmt']) != 0:
                        entry_price = float(position['entryPrice'])
                        mark_price = float(position['markPrice'])
                        if (position['positionSide'] == 'LONG' and mark_price >= entry_price * 1.10) or (position['positionSide'] == 'SHORT' and mark_price <= entry_price * 0.90):
                            remaining_position = position['positionSide']
                            remaining_quantity = abs(float(position['positionAmt']))
                            take_profit_price = entry_price * 1.10 if remaining_position == 'LONG' else entry_price * 0.90
                            set_take_profit(symbol, SIDE_SELL if remaining_position == 'LONG' else SIDE_BUY, remaining_quantity, take_profit_price, remaining_position)
                            print(f"Take profit triggered. Setting take profit at {take_profit_price} for remaining {remaining_position} position.")
                            return
        except BinanceAPIException as e:
            print(f"Error: {e}")
            print("Please enter a valid token symbol.")
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

if __name__ == '__main__':
    main()
