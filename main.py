import json
import time

import requests
from rich.console import Console
from rich.progress import track
from rich.style import Style
from rich.table import Table

app_id = 2923300
currency = 1 # https://partner.steamgames.com/doc/store/pricing/currencies To get currencies number.
steam_id = 0

def scrap_inventory():
    data = {
        "count": 5000,
    }

    result = {}

    while True:
        r = requests.get(f"http://steamcommunity.com/inventory/{steam_id}/{app_id}/2?count=5000", params=data)
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

def get_price(market_hash_name):
    while True:
        data = {
            "appid": app_id,
            "currency": currency,
            "market_hash_name": market_hash_name,
        }

        r = requests.get("https://steamcommunity.com/market/priceoverview/", params=data)
        if r.status_code == 429:
            time.sleep(5)
            continue

        return r.json()

def render():
    data = {
        "appid": app_id,
        "currency": currency,
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

        result.extend(r["results"])
        if len(r["results"]) < 100:
            break

    return result

def load_data():
    try:
        with open("data.json", encoding="utf-8") as fo:
            return json.load(fo)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return []

def save_data(data):
    with open("data.json", "w", encoding="utf-8") as fo:
        json.dump(data, fo, indent=4, ensure_ascii=False)

def print_prices(data, inventory=False):
    table = Table()

    table.add_column("🚧")
    table.add_column("💰")
    table.add_column("🔊")
    table.add_column("〽️")
    table.add_column("🚩")
    table.add_column("🆓")
    if inventory: table.add_column("📄")
    if inventory: table.add_column("🏦")
    table.add_column("🔗")

    total_price = 0

    for item in data:
        diff = item["difference"]

        if item.get("amount_price"):
            total_price += item["amount_price"]

        if diff == 0:
            price_changed = 0
            emoji = "🚩"
            style = Style(color="white")

        elif diff < 0:
            price_changed = abs(diff/100)
            emoji = "⬇️"
            style = Style(color="red")

        elif diff > 0:
            price_changed = abs(diff/100)
            emoji = "⬆️"
            style = Style(color="green")

        url = f"https://steamcommunity.com/market/listings/{app_id}/{item["asset_description"]["market_hash_name"]}"

        if inventory:
            table.add_row(item["name"], item["sell_price_text"], item["volume"], str(price_changed), emoji, item["drop_in_game"], str(item["amount"]), str(item["amount_price"]), url, style=style)
        else:
            table.add_row(item["name"], item["sell_price_text"], item["volume"], str(price_changed), emoji, item["drop_in_game"], url, style=style)

    console = Console()
    console.print(table)

    if inventory:
        console.print(f"[green]Total Price: {total_price}")

def add_volume(data, use_cache=False):
    old_data = load_data()

    if old_data and use_cache:
        for item in data:
            need_request = True

            for old_item in old_data:
                if item["hash_name"] == old_item["hash_name"]:
                    need_request = False
                    item["volume"] = old_item["volume"]
                    break

            if need_request:
                volume = get_price(item["hash_name"])
                item["volume"] = volume["volume"] if volume.get("volume") else "0"

        return data

    for item in track(data, "Requesting volume..."):
        volume = get_price(item["hash_name"])
        volume = volume["volume"] if volume.get("volume") else "0"

        item["volume"] = volume
        time.sleep(2)

    return data

def add_drop_in_game(data):
    for item in data:
        status = is_drop_in_game(item["asset_description"]["descriptions"][0]["value"])

        if status:
            item["drop_in_game"] = "✅"
        else:
            item["drop_in_game"] = "❌"

    return data

def is_drop_in_game(desc):
    if "Drops ingame" in desc:
        return True

    return False

def check_price(data):
    old_data = load_data()

    for item in data:
        item["difference"] = 0

        for old_item in old_data:
            if item["hash_name"] == old_item["hash_name"]:
                if old_item.get("old_price"):

                    old_diff = old_item["sell_price"] - old_item["old_price"]
                    new_diff = item["sell_price"] - old_item["sell_price"]

                    if old_diff > 0 and new_diff > 0 or old_diff < 0 and new_diff < 0 or old_diff == new_diff or new_diff == 0:
                        item["old_price"] = old_item["old_price"]
                        item["difference"] = item["sell_price"] - old_item["old_price"]
                    else:
                        item["old_price"] = old_item["sell_price"]
                        item["difference"] = item["sell_price"] - old_item["sell_price"]
                else:
                    item["old_price"] = old_item["sell_price"]
                    item["difference"] = 0

                break

    return data

def add_inventory(data):
    inventory = scrap_inventory()

    for item in data:
        classid = item["asset_description"]["classid"]
        item["amount"] = 0
        item["amount_price"] = 0

        if inventory.get(classid):
            item["amount"] = inventory[classid]
            item["amount_price"] = item["sell_price"] * int(item["amount"]) / 100
            continue

    return data

def main():
    data = render()

    data = add_volume(data, True)

    data = add_drop_in_game(data)

    data = check_price(data)

    if steam_id:
        data = add_inventory(data)

        print_prices(data, True)
    else:
        print_prices(data)

    save_data(data)

if __name__ == "__main__":
    main()
