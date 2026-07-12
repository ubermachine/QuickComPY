import websocket
import json
import uuid

ws = websocket.create_connection(f"ws://localhost:5000?clientId={uuid.uuid4()}")
ws.send(json.dumps({"action": "setLocation", "location": "201306"}))

while True:
    res = ws.recv()
    print("RECV:", res)
    data = json.loads(res)
    if data.get("action") == "setLocation" and data.get("status") in ["success", "error"]:
        break

ws.send(json.dumps({"action": "search", "searchTerm": "milk"}))
while True:
    res = ws.recv()
    print("RECV:", res)
    data = json.loads(res)
    if data.get("action") == "statusUpdate" and data.get("step") == "search" and data.get("status") in ["completed", "error"]:
        break

ws.close()
