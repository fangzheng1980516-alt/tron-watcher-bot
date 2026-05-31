import requests
import time
import json
import os
from datetime import datetime
from threading import Thread

# ========== 配置 ==========
BOT_TOKEN = "8956870921:AAFBvYNS4ier8joOvMGByDozA3iiH29DeLQ"
# =========================

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
DATA_FILE = "processed_txs.json"
WALLETS_FILE = "wallets.json"

def load_processed_txs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_processed_txs(txs_set):
    with open(DATA_FILE, 'w') as f:
        json.dump(list(txs_set), f)

def load_wallets():
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                return {"0": data}
    return {}

def save_wallets(wallets):
    with open(WALLETS_FILE, 'w') as f:
        json.dump(wallets, f, indent=2)

chat_wallets = load_wallets()
processed_txs = load_processed_txs()
last_update_id = 0

def send_telegram(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=5)
        print(f"已发送消息到 {chat_id}")
    except Exception as e:
        print(f"发送失败: {e}")

def send_main_menu(chat_id, is_group=False):
    keyboard = {
        "inline_keyboard": [
            [{"text": "💰 查询余额", "callback_data": "balance"}],
            [{"text": "📋 钱包列表", "callback_data": "list"}],
            [{"text": "➕ 添加钱包", "callback_data": "add"}],
            [{"text": "❌ 移除钱包", "callback_data": "remove"}],
            [{"text": "📈 今日统计", "callback_data": "stats"}],
        ]
    }
    msg = "🤖 **TRC20 钱包监控机器人**\n\n请点击下方按钮："
    send_telegram(chat_id, msg, keyboard)

def get_usdt_balance(address):
    try:
        url = f"https://api.trongrid.io/v1/accounts/{address}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        for trc20 in data.get('data', [{}])[0].get('trc20', []):
            for contract, bal in trc20.items():
                if contract == USDT_CONTRACT:
                    return int(bal) / 1_000_000
        return 0
    except:
        return 0

def get_recent_transactions(address):
    try:
        url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
        params = {"contract_address": USDT_CONTRACT, "limit": 30, "only_confirmed": True}
        resp = requests.get(url, params=params, timeout=10)
        return resp.json().get('data', [])
    except:
        return []

def check_all_wallets():
    global processed_txs
    wallets_copy = dict(chat_wallets.items())
    
    for chat_id_str, addresses in wallets_copy.items():
        if not isinstance(addresses, list):
            continue
        for addr in addresses:
            txs = get_recent_transactions(addr)
            for tx in txs:
                tx_id = tx.get('transaction_id')
                if tx_id and tx_id not in processed_txs:
                    processed_txs.add(tx_id)
                    
                    if tx.get('to') != addr:
                        continue
                    
                    amount = int(tx.get('value', 0)) / 1_000_000
                    timestamp = tx.get('block_timestamp', 0) / 1000
                    dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    addr_short = addr[:6] + "..." + addr[-4:]
                    msg = f"📥 **收到 USDT**\n地址: `{addr_short}`\n金额: **{amount}** USDT\n时间: {dt}"
                    
                    try:
                        send_telegram(int(chat_id_str), msg)
                        print(f"[{datetime.now()}] 收到 {amount} USDT -> {addr_short}")
                    except:
                        send_telegram(chat_id_str, msg)
    
    save_processed_txs(processed_txs)

def monitoring_loop():
    print("🔍 监控线程已启动")
    while True:
        try:
            check_all_wallets()
            time.sleep(15)
        except Exception as e:
            print(f"监控错误: {e}")
            time.sleep(30)

def handle_updates():
    global last_update_id, chat_wallets
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 20}
            resp = requests.get(url, params=params, timeout=25)
            result = resp.json()
            
            if not result.get('ok'):
                time.sleep(5)
                continue
            
            updates = result.get('result', [])
            
            for update in updates:
                last_update_id = update.get('update_id', last_update_id)
                
                chat_id = None
                chat_type = None
                
                if 'callback_query' in update:
                    msg = update['callback_query']['message']
                    chat_id = msg['chat']['id']
                    chat_type = msg['chat']['type']
                elif 'message' in update:
                    msg = update['message']
                    chat_id = msg['chat']['id']
                    chat_type = msg['chat']['type']
                
                if not chat_id:
                    continue
                
                chat_id_key = str(chat_id)
                is_group = (chat_type in ['group', 'supergroup'])
                
                if chat_id_key not in chat_wallets:
                    chat_wallets[chat_id_key] = []
                
                if 'callback_query' in update:
                    callback = update['callback_query']
                    data = callback.get('data', '')
                    callback_id = callback.get('id', '')
                    
                    try:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", 
                                      json={"callback_query_id": callback_id}, timeout=5)
                    except:
                        pass
                    
                    wallets = chat_wallets[chat_id_key]
                    
                    if data == "balance":
                        if not wallets:
                            send_telegram(chat_id, "📭 暂无监控钱包\n\n点击「➕ 添加钱包」开始监控")
                        else:
                            total = 0
                            msg = "💰 **余额查询**\n\n"
                            for addr in wallets:
                                bal = get_usdt_balance(addr)
                                total += bal
                                addr_short = addr[:6] + "..." + addr[-4:]
                                msg += f"`{addr_short}`: {bal} USDT\n"
                            msg += f"\n**总计**: {total} USDT"
                            send_telegram(chat_id, msg)
                    
                    elif data == "list":
                        if not wallets:
                            send_telegram(chat_id, "📭 暂无监控钱包")
                        else:
                            msg = "📋 **钱包列表**\n\n"
                            for i, addr in enumerate(wallets, 1):
                                addr_short = addr[:6] + "..." + addr[-4:]
                                msg += f"{i}. `{addr_short}`\n"
                            send_telegram(chat_id, msg)
                    
                    elif data == "add":
                        send_telegram(chat_id, "📝 请发送 TRC20 地址\n\n格式：T开头，共34位")
                    
                    elif data == "remove":
                        if not wallets:
                            send_telegram(chat_id, "📭 暂无钱包可移除")
                        else:
                            keyboard = {"inline_keyboard": []}
                            for i, addr in enumerate(wallets):
                                addr_short = addr[:6] + "..." + addr[-4:]
                                keyboard["inline_keyboard"].append([{"text": f"❌ {addr_short}", "callback_data": f"remove_{i}"}])
                            keyboard["inline_keyboard"].append([{"text": "🔙 返回菜单", "callback_data": "back"}])
                            send_telegram(chat_id, "请选择要移除的钱包：", keyboard)
                    
                    elif data == "stats":
                        today = datetime.now().strftime('%Y-%m-%d')
                        today_start = int(datetime.strptime(today, '%Y-%m-%d').timestamp())
                        total_in = 0
                        total_out = 0
                        for addr in wallets:
                            for tx in get_recent_transactions(addr):
                                ts = tx.get('block_timestamp', 0) / 1000
                                if ts >= today_start:
                                    amt = int(tx.get('value', 0)) / 1_000_000
                                    if tx.get('to') == addr:
                                        total_in += amt
                                    else:
                                        total_out += amt
                        msg = f"📈 **今日统计** ({today})\n\n📥 收入: {total_in} USDT\n📤 支出: {total_out} USDT\n📊 净额: {total_in - total_out} USDT"
                        send_telegram(chat_id, msg)
                    
                    elif data.startswith("remove_"):
                        try:
                            idx = int(data.split('_')[1])
                            if 0 <= idx < len(wallets):
                                removed = wallets.pop(idx)
                                chat_wallets[chat_id_key] = wallets
                                save_wallets(chat_wallets)
                                send_telegram(chat_id, f"✅ 已移除: `{removed[:6]}...{removed[-4:]}`")
                        except:
                            send_telegram(chat_id, "❌ 移除失败")
                        send_main_menu(chat_id, is_group)
                    
                    elif data == "back":
                        send_main_menu(chat_id, is_group)
                
                elif 'message' in update:
                    msg = update['message']
                    text = msg.get('text', '')
                    
                    if text in ['/start', '/Query', '/查询']:
                        send_main_menu(chat_id, is_group)
                    elif text and len(text) == 34 and text.startswith('T') and not is_group:
                        wallets = chat_wallets[chat_id_key]
                        if text not in wallets:
                            wallets.append(text)
                            chat_wallets[chat_id_key] = wallets
                            save_wallets(chat_wallets)
                            send_telegram(chat_id, f"✅ 已添加钱包\n`{text[:6]}...{text[-4:]}`")
                            send_main_menu(chat_id, False)
                        else:
                            send_telegram(chat_id, "⚠️ 该钱包已在监控列表中")
                    elif text and not text.startswith('/') and not is_group:
                        send_telegram(chat_id, "❌ 地址格式错误\nTRC20 地址应以 T 开头，共34位")
            
        except Exception as e:
            print(f"消息处理错误: {e}")
            time.sleep(3)

if __name__ == "__main__":
    if os.path.exists(WALLETS_FILE):
        try:
            test = load_wallets()
            if not isinstance(test, dict):
                os.remove(WALLETS_FILE)
                chat_wallets = {}
        except:
            os.remove(WALLETS_FILE)
            chat_wallets = {}
    
    print(f"🤖 TRC20 监控机器人启动...")
    print(f"📊 监控群组数量: {len(chat_wallets)}")
    print(f"📝 支持命令: /start  /Query  /查询")
    print(f"🔔 只监控 USDT 入账，转出不通知")
    
    Thread(target=monitoring_loop, daemon=True).start()
    handle_updates()