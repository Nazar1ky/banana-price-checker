import json
import os
import re
import time
import urllib

import requests
from rich import box, print
from rich.console import Console
from rich.progress import track
from rich.style import Style
from rich.table import Table
from rich.text import Text


class Market:
    def __init__(self, app_id, currency, steam_id=None):
        self.steam_id = steam_id

        self.app_id = app_id
        self.currency = currency
        self.language = "english"
        self.folder_items = "items"

        self.currency_symbol = None

    def get_full_data(self):
        data = self.render()

        items_file_name = f"{self.folder_items}/{self.app_id}.json"

        items = self.load_items(items_file_name)

        for item in track(data, description="🛠️ [green bold]Requesting item ids..."):
            hash_name = item["market_hash_name"]

            if items.get(hash_name):
                item["item_id"] = items[hash_name]
                continue

            item_id = self.get_item_id(hash_name)

            item["item_id"] = item_id
            items[hash_name] = item_id

            time.sleep(10)

        self.save_items(items_file_name, items)

        for item in track(data, description="💲 [green bold]Requesting prices...  "):
            order_histogram = self.get_orders_histogram(item["item_id"])

            if order_histogram.get("buy_order_count", 0) != 0:
                item["buy_order_count"] = int(re.sub(r"\D", "", order_histogram["buy_order_count"]))

            if order_histogram.get("sell_order_count", 0) != 0:
                item["sell_order_count"] = int(re.sub(r"\D", "", order_histogram["sell_order_count"]))

            item["highest_buy_order"] = int(order_histogram["highest_buy_order"]) if order_histogram.get("highest_buy_order") else -1
            item["lowest_sell_order"] = int(order_histogram["lowest_sell_order"]) if order_histogram.get("lowest_sell_order") else -1

            self.currency_symbol = order_histogram["price_suffix"]

        if self.steam_id:
            print("🎒 [green bold]Requesting inventory...")
            data = self.add_inventory(data)

        return data

    def add_inventory(self, data):
        inventory = self.get_inventory(self.steam_id)

        for item in data:
            classid = item["class_id"] # We using that to find item in inventory

            item["amount"] = 0
            item["amount_price"] = 0

            if inventory.get(classid) and item.get("highest_buy_order"):
                item["amount"] = inventory[classid]
                item["amount_price"] = item["highest_buy_order"] * item["amount"] / 100

                continue

        return data

    def render(self):
        data = {
            "appid": self.app_id,
            "start": 0,
            "count": 100,
            "sort_column": "price",
            "sort_dir": "asc",
            "norender": 1,
        }

        result = []

        while True:
            r = requests.get("https://steamcommunity.com/market/search/render/", params=data)
            r.raise_for_status()
            r = r.json()

            for item in r["results"]:
                item_data = {
                    "name": item["name"],
                    "app_name": item["app_name"],
                    "sell_listings": item["sell_listings"],
                    "class_id": item["asset_description"]["classid"],
                    "market_hash_name": item["asset_description"]["market_hash_name"],
                    "descriptions": item["asset_description"]["descriptions"],
                    "url": f"https://steamcommunity.com/market/listings/{self.app_id}/{urllib.parse.quote(item["asset_description"]["market_hash_name"])}",
                }

                result.append(item_data)

            if len(r["results"]) <= 100:
                break

        return result

    def get_item_id(self, hash_name):
        while True:
            r = requests.get(f"https://steamcommunity.com/market/listings/{self.app_id}/{hash_name}")

            if r.status_code == 429:
                time.sleep(10)
                continue

            r.raise_for_status()

            match = re.search(r"Market_LoadOrderSpread\s*\(\s*(\d+)\s*\);", r.text)

            if not match:
                raise RuntimeError("Not founded item_id")

            return match.group(1)

    def get_orders_histogram(self, item_id):
        data = {
            "language": self.language,
            "currency": self.currency,
            "item_nameid": item_id,
            "norender": 1,
        }
        r = requests.get("https://steamcommunity.com/market/itemordershistogram", params=data)
        r.raise_for_status()

        return r.json()

    def load_items(self, file_name):
        try:
            with open(file_name, encoding="utf-8") as fo:
                return json.load(fo)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return {}

    def save_items(self, file_name, data):
        if not os.path.exists(self.folder_items):
            os.mkdir(self.folder_items)

        with open(file_name, "w", encoding="utf-8") as fo:
            json.dump(data, fo, indent=4, ensure_ascii=False)

    def get_inventory(self, steam_id):
        data = {
            "count": 5000,
        }

        result = {}

        while True:
            r = requests.get(f"http://steamcommunity.com/inventory/{steam_id}/{self.app_id}/2?count=5000", params=data)
            r.raise_for_status()
            r = r.json()

            for asset in r["assets"]:
                if result.get(asset["classid"]):
                    result[asset["classid"]] += int(asset["amount"])
                else:
                    result[asset["classid"]] = int(asset["amount"])

            if len(r["assets"]) < 5000:
                break

            data["start_assetid"] = [r["assets"][-1]["assetid"]]

        return result

def print_prices(data, steam_id=None, currency_symbol="$"):
    table = Table(padding=(0), style="yellow")

    table.add_column("🚧 [bold white]Item")
    table.add_column("💲 [bold green]Buy")
    table.add_column("💲 [bold red]Sell")
    table.add_column("📈 ")
    table.add_column("🚩 ")
    table.add_column("🆓 ")

    if steam_id:
        table.add_column("🎒 [bold blue]Inv")
        table.add_column("💰 [bold green]Total Price")

    # table.add_column("🔗 URL", style="dim")

    total_price = 0

    for item in data:
        diff = item["difference"]

        if item.get("amount_price"):
            total_price += item["amount_price"]

        if diff == 0:
            price_changed = 0
            emoji = ""
            style = Style(color="white")

        elif diff < 0:
            price_changed = abs(diff/100)
            emoji = "👎"
            style = Style(color="red")

        elif diff > 0:
            price_changed = abs(diff/100)
            emoji = "👍"
            style = Style(color="green")

        if not item.get("highest_buy_order"):
            item["highest_buy_order"] = "❌"

        drops_in_game = "✅" if item.get("drops_in_game") else "❌"

        row_items = [
            f"[bold][link={item["url"]}]{item["name"]}[/link][/bold]",
            str(item["highest_buy_order"] / 100),
            str(item["lowest_sell_order"] / 100),
            str(price_changed),
            emoji,
            drops_in_game,
        ]

        if steam_id:
            row_items.insert(6, str(item["amount"]))
            row_items.insert(7, str(item["amount_price"]))

        table.add_row(*row_items, style=style)

    console = Console()

    if steam_id:
        console.print(f"🏦 [green][bold]Total Price of [/green][yellow][underline][link=https://steamcommunity.com/profiles/{steam_id}/inventory italic]inventory[/link][/underline][/yellow][green]:[/green] [blue bold]{total_price}{currency_symbol}")

    console.print(table)

def add_drop_in_game(data):
    for item in data:
        for desc in item["descriptions"]:
            if "Drops ingame" in desc["value"] or "Drops from the game" in desc["value"]:
                item["drops_in_game"] = True
                break

            item["drops_in_game"] = False

    return data

def check_price(data, old_data):
    for item in data:
        item["difference"] = 0

        if not item.get("highest_buy_order"):
            continue

        for old_item in old_data:
            if item["market_hash_name"] == old_item["market_hash_name"]:
                if old_item.get("old_price"):

                    old_diff = old_item["highest_buy_order"] - old_item["old_price"]
                    new_diff = item["highest_buy_order"] - old_item["highest_buy_order"]

                    if old_diff > 0 and new_diff > 0 or old_diff < 0 and new_diff < 0 or old_diff == new_diff or new_diff == 0:
                        item["old_price"] = old_item["highest_buy_order"]
                        item["difference"] = item["highest_buy_order"] - old_item["old_price"]
                    else:
                        item["old_price"] = old_item["highest_buy_order"]
                        item["difference"] = item["highest_buy_order"] - old_item["highest_buy_order"]
                else:
                    item["old_price"] = old_item["highest_buy_order"]
                    item["difference"] = 0

                break

    return data

def load_data(folder, app_id):
    try:
        with open(f"{folder}/{app_id}.json", encoding="utf-8") as fo:
            return json.load(fo)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return []

def save_data(folder, app_id, data):
    if not os.path.exists(folder):
        os.mkdir(folder)

    with open(f"{folder}/{app_id}.json", "w", encoding="utf-8") as fo:
        json.dump(data, fo, indent=4, ensure_ascii=False)

def main():
    app_id = 2923300 # 2923300 (BANANA) 2784840 (EGG) 2977660 (CATS)
    currency = 3 # https://partner.steamgames.com/doc/store/pricing/currencies To get currencies number.
    steam_id = "76561198047167723" # Put there STEAMID
    folder = "data"

    scraper = Market(app_id, currency, steam_id)

    data = scraper.get_full_data()

    old_data = load_data(folder, app_id)
    data = check_price(data, old_data)

    data = add_drop_in_game(data)

    save_data(folder, app_id, data)

    if steam_id:
        data.sort(key=lambda x: (-x["amount"], x["highest_buy_order"]))

    print_prices(data, steam_id, scraper.currency_symbol)


if __name__ == "__main__":
    main()
