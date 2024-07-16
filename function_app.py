import csv
import re
import os
import uuid
import base64
import asyncio
from flask import Flask, request, jsonify
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext, ActivityHandler
from botbuilder.schema import Activity, Attachment
from botframework.connector.auth import ClaimsIdentity

import azure.functions as func

app = Flask(__name__)

class CustomBotFrameworkAdapter(BotFrameworkAdapter):
    async def _authenticate_request(self, activity: Activity, auth_header: str):
        return ClaimsIdentity({}, True)

class OrderBot(ActivityHandler):
    def __init__(self):
        self.orders = {}

    async def on_message_activity(self, turn_context: TurnContext):
        user_input = turn_context.activity.text
        if user_input.lower() == "orders":
            file_path = self.export_to_csv()
            await self.send_file(turn_context, file_path)
        else:
            orders = self.parse_orders(user_input)
            if orders:
                self.collect_orders(orders)
                response = "Orders have been collected."
            else:
                response = "Could not parse the order. Please check the format."
            await turn_context.send_activity(response)

    def parse_orders(self, text):
        text = text.strip()
        order_pattern = re.compile(r'(\d+)\.hét:\s*((?:\w+:[^\n]+\n?)*)', re.UNICODE)
        day_pattern = re.compile(r'([hkscp]\w+):\s*([^hkscp]+)', re.UNICODE)
        orders = {}
        week_match = order_pattern.search(text)

        if week_match:
            week = week_match.group(1)
            days_text = week_match.group(2).strip()
            days = {}
            day_matches = day_pattern.findall(days_text)
            print(day_matches)
            print(f"days_text {days_text}")
            for day, items in day_matches:
                items = [item.strip() for item in items.split(',')]
                days[day.lower()] = items
                print(items)
            orders[week] = days
        return orders

    def collect_orders(self, new_orders):
        for week, days in new_orders.items():
            if week not in self.orders:
                self.orders[week] = {}
            for day, items in days.items():
                if day not in self.orders[week]:
                    self.orders[week][day] = []
                self.orders[week][day].extend(items)

    def export_to_csv(self):
        file_path = f"orders_{uuid.uuid4()}.csv"
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            for week, days in self.orders.items():
                writer.writerow([week])
                day_map = {'hétfő': 1, 'kedd': 2, 'szerda': 3, 'csütörtök': 4, 'péntek': 5}
                for day, items in days.items():
                    day_number = day_map.get(day, None)
                    if day_number:
                        for item in items:
                            writer.writerow([f"{item}_{day_number}"])
        return file_path

    async def send_file(self, turn_context, file_path):
        with open(file_path, "rb") as file:
            content = file.read()

        base64_content = base64.b64encode(content).decode('utf-8')
        attachment = Attachment(
            name=os.path.basename(file_path),
            content_type="text/csv",
            content_url=f"data:text/csv;base64,{base64_content}"
        )

        await turn_context.send_activity(
            Activity(
                type="message",
                text="Here are the collected orders:",
                attachments=[attachment]
            )
        )

        os.remove(file_path)

SETTINGS = BotFrameworkAdapterSettings(os.getenv('MicrosoftAppId'), os.getenv('MicrosoftAppPassword'))
ADAPTER = CustomBotFrameworkAdapter(SETTINGS)
BOT = OrderBot()

@app.route("/api/messages", methods=["POST"])
def messages():
    body = request.json
    activity = Activity().deserialize(body)
    auth_header = request.headers['Authorization'] if 'Authorization' in request.headers else ''
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ADAPTER.process_activity(activity, auth_header, BOT.on_turn))
    return jsonify({"status": "ok"})

async def main(req: func.HttpRequest) -> func.HttpResponse:
    return func.WsgiMiddleware(app.wsgi_app).handle(req)
