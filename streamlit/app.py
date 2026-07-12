import streamlit as st
import websocket
import json
import uuid
import time
import threading

# Initialize session state variables
if 'client_id' not in st.session_state:
    st.session_state.client_id = str(uuid.uuid4())
if 'ws_messages' not in st.session_state:
    st.session_state.ws_messages = []
if 'ws' not in st.session_state:
    st.session_state.ws = None
if 'is_connected' not in st.session_state:
    st.session_state.is_connected = False
if 'is_location_set' not in st.session_state:
    st.session_state.is_location_set = False
if 'current_location' not in st.session_state:
    st.session_state.current_location = None
if 'services' not in st.session_state:
    st.session_state.services = {
        'blinkit': {'products': [], 'status': 'idle', 'isLoading': False, 'message': ''},
        'bigbasket': {'products': [], 'status': 'idle', 'isLoading': False, 'message': ''},
        'jiomart': {'products': [], 'status': 'idle', 'isLoading': False, 'message': ''},
        'zepto': {'products': [], 'status': 'idle', 'isLoading': False, 'message': ''},
        'instamart': {'products': [], 'status': 'idle', 'isLoading': False, 'message': ''}
    }

def on_message(ws, message):
    try:
        data = json.loads(message)
        st.session_state.ws_messages.append(data)

        # Handle specific actions
        action = data.get("action")
        status = data.get("status")

        if action == "setLocation" and status == "success":
            st.session_state.is_location_set = True
            st.session_state.current_location = data.get("location")
            # Force a rerun to update UI
            st.rerun()

        elif action == "searchResults" and status == "success":
            products_data = data.get("products", {})
            for svc in st.session_state.services.keys():
                if svc in products_data:
                    svc_products = products_data[svc]
                    st.session_state.services[svc]['products'] = svc_products
                    st.session_state.services[svc]['status'] = 'success' if len(svc_products) > 0 else 'empty'
                    st.session_state.services[svc]['isLoading'] = False
            # Force a rerun to update UI
            st.rerun()

    except Exception as e:
        print(f"Error processing message: {e}")

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    st.session_state.is_connected = False
    print("WebSocket connection closed")

def on_open(ws):
    st.session_state.is_connected = True
    print("WebSocket connection opened")

def start_ws(ws_url, client_id):
    ws = websocket.WebSocketApp(f"{ws_url}?clientId={client_id}",
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    st.session_state.ws = ws
    ws.run_forever()

# Start WebSocket connection in a separate thread if not already running
if not st.session_state.is_connected and ('ws_thread' not in st.session_state or not st.session_state.ws_thread.is_alive()):
    st.session_state.ws_thread = threading.Thread(target=start_ws, args=("ws://localhost:5000", st.session_state.client_id))
    st.session_state.ws_thread.daemon = True
    st.session_state.ws_thread.start()
    # Wait a bit for connection to establish
    time.sleep(1)

st.title("QuickCom Scraper")

# Location Input
col1, col2 = st.columns([3, 1])
with col1:
    location = st.text_input("Location", "201306", disabled=st.session_state.is_location_set)
with col2:
    if st.button("Set Location", disabled=st.session_state.is_location_set or not st.session_state.is_connected):
        if st.session_state.ws and st.session_state.is_connected:
            msg = json.dumps({"action": "setLocation", "location": location})
            st.session_state.ws.send(msg)
            st.info("Setting location...")

if st.session_state.is_location_set:
    st.success(f"Location set to: {st.session_state.current_location}")

# Search Input
col3, col4 = st.columns([3, 1])
with col3:
    search_term = st.text_input("Search Term", "", disabled=not st.session_state.is_location_set)
with col4:
    if st.button("Search Products", disabled=not st.session_state.is_location_set or not search_term):
        if st.session_state.ws and st.session_state.is_connected:
            # Set all services to loading
            for svc in st.session_state.services:
                st.session_state.services[svc]['isLoading'] = True
                st.session_state.services[svc]['products'] = []

            msg = json.dumps({"action": "search", "searchTerm": search_term})
            st.session_state.ws.send(msg)
            st.info("Searching...")

# Display Results
for svc_name, svc_data in st.session_state.services.items():
    st.subheader(svc_name.capitalize())
    if svc_data['isLoading']:
        st.write("Loading...")
    elif svc_data['status'] == 'success':
        st.write(f"Found {len(svc_data['products'])} items")
        # Grid layout for products
        cols = st.columns(3)
        for i, product in enumerate(svc_data['products']):
            with cols[i % 3]:
                if product.get('imageUrl'):
                    st.image(product['imageUrl'], width=100)
                st.write(f"**{product['name']}**")
                st.write(f"{product['quantity']} | {product['price']}")
                if product.get('deliveryTime'):
                    st.write(f"Delivery: {product['deliveryTime']}")
                st.divider()
    elif svc_data['status'] == 'empty':
        st.write("No products found")
