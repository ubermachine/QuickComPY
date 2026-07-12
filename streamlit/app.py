import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import asyncio
import time
import threading
import zendriver as zd
from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto

# --- Premium Custom CSS ---
st.set_page_config(page_title="QuickCom", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #f8fafc; }
    .glass-card { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 16px; margin-bottom: 16px; transition: transform 0.2s, box-shadow 0.2s; height: 100%; display: flex; flex-direction: column; }
    .glass-card:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.3); border-color: rgba(255, 255, 255, 0.2); }
    .product-img { width: 100%; height: 140px; object-fit: contain; border-radius: 8px; margin-bottom: 12px; background: rgba(255,255,255,0.9); padding: 8px; }
    .product-title { font-weight: 600; font-size: 1.1em; line-height: 1.3; margin-bottom: 8px; color: #f8fafc; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .price-row { display: flex; align-items: center; gap: 8px; margin-top: auto; }
    .current-price { font-size: 1.25em; font-weight: 800; color: #10b981; }
    .original-price { text-decoration: line-through; color: #64748b; font-size: 0.9em; }
    .discount-badge { background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; font-weight: 600; }
    .brand-badge { padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 1em; display: inline-block; margin-bottom: 16px; color: white; text-transform: uppercase; letter-spacing: 1px; }
    .bg-blinkit { background: linear-gradient(90deg, #f59e0b, #d97706); }
    .bg-bigbasket { background: linear-gradient(90deg, #84cc16, #65a30d); }
    .bg-jiomart { background: linear-gradient(90deg, #3b82f6, #2563eb); }
    .bg-zepto { background: linear-gradient(90deg, #8b5cf6, #6d28d9); }
</style>
""", unsafe_allow_html=True)

# Define Scraping Services
SERVICES = ["blinkit", "bigbasket", "jiomart", "zepto"]
SCRAPERS = {
    "blinkit": blinkit,
    "bigbasket": bigbasket,
    "jiomart": jiomart,
    "zepto": zepto,
}

# Stealth JS to evade bot detection (injected into every page before any JS runs)
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
"""

async def stealth_new_page(browser):
    """Create a new page with stealth scripts injected that persist across navigations"""
    page = await browser.get('about:blank', new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH_JS))
    return page

# --- Cache Zendriver Browser globally across sessions ---
@st.cache_resource
def get_browser_and_loop():
    print("Starting global Zendriver browser in background thread...")
    loop = asyncio.new_event_loop()
    
    def run_loop_and_browser():
        asyncio.set_event_loop(loop)
        try:
            # Start browser with stealth configuration
            stealth_config = zd.Config(
                sandbox=False,
                headless=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                disable_webrtc=True,
            )
            browser = loop.run_until_complete(zd.start(config=stealth_config))
            loop.zendriver_browser = browser
            
            # Initialize global semaphore for scraping concurrency limits
            async def init_sem():
                loop.global_semaphore = asyncio.Semaphore(2)
            loop.run_until_complete(init_sem())
            
            print("Zendriver initialized successfully on background thread!")
            loop.run_forever()
        except Exception as e:
            print(f"Failed to start Zendriver on background thread: {e}")
            loop.zendriver_browser = None
            
    t = threading.Thread(target=run_loop_and_browser, daemon=True)
    t.start()
    
    # Wait for the background thread to finish initialization
    while not hasattr(loop, 'zendriver_browser'):
        time.sleep(0.1)
        
    if loop.zendriver_browser is None:
        raise RuntimeError("Zendriver failed to start.")
        
    return loop.zendriver_browser, loop

try:
    global_browser, global_loop = get_browser_and_loop()
except Exception as e:
    st.error(f"Failed to start browser: {e}")
    st.stop()

# Helper async functions
def robust_close(page):
    async def _close():
        try:
            await page.close()
        except Exception as e:
            print(f"Error closing page: {e}")
    t = asyncio.create_task(_close())
    if not hasattr(global_loop, 'cleanup_tasks'):
        global_loop.cleanup_tasks = set()
    global_loop.cleanup_tasks.add(t)
    t.add_done_callback(global_loop.cleanup_tasks.discard)

async def set_loc_svc(svc, location):
    print(f"Setting location for {svc}")
    page = None
    try:
        page = await stealth_new_page(global_browser)
        success = await asyncio.wait_for(SCRAPERS[svc].set_location(page, location), timeout=15.0)
        return svc, success
    except Exception as e:
        print(f"Location error {svc}: {type(e).__name__} - {e}")
        return svc, False
    finally:
        if page:
            robust_close(page)

async def run_set_location_all(location):
    sem = global_loop.global_semaphore
    async def _run(s):
        async with sem:
            return await set_loc_svc(s, location)
    results = await asyncio.gather(*[_run(s) for s in SERVICES], return_exceptions=True)
    results_dict = {}
    for i, s in enumerate(SERVICES):
        res = results[i]
        if isinstance(res, Exception):
            print(f"Service {s} failed with exception: {res}")
            results_dict[s] = False
        else:
            results_dict[s] = res[1]
    return results_dict

async def search_svc(svc, search_term):
    print(f"Searching {svc} for {search_term}")
    page = None
    try:
        page = await stealth_new_page(global_browser)
        products = await asyncio.wait_for(SCRAPERS[svc].search(page, search_term), timeout=30.0)
        return svc, products
    except Exception as e:
        print(f"Search error {svc}: {type(e).__name__} - {e}")
        return svc, []
    finally:
        if page:
            robust_close(page)

async def run_search_all(search_term):
    sem = global_loop.global_semaphore
    async def _run(s):
        async with sem:
            return await search_svc(s, search_term)
    results = await asyncio.gather(*[_run(s) for s in SERVICES], return_exceptions=True)
    results_dict = {}
    for i, s in enumerate(SERVICES):
        res = results[i]
        if isinstance(res, Exception):
            print(f"Service {s} failed with exception: {res}")
            results_dict[s] = []
        else:
            results_dict[s] = res[1]
    return results_dict

def run_async_task(coro):
    future = asyncio.run_coroutine_threadsafe(coro, global_loop)
    try:
        return future.result()
    except BaseException:
        future.cancel()
        raise

# Initialize session state variables
if 'is_location_set' not in st.session_state:
    st.session_state.is_location_set = False
if 'current_location' not in st.session_state:
    st.session_state.current_location = None
if 'services' not in st.session_state:
    st.session_state.services = {
        'blinkit': {'products': [], 'status': 'idle'},
        'bigbasket': {'products': [], 'status': 'idle'},
        'jiomart': {'products': [], 'status': 'idle'},
        'zepto': {'products': [], 'status': 'idle'},
    }

st.markdown("<h1 style='text-align: center; margin-bottom: 2rem;'>⚡ QuickCom Search</h1>", unsafe_allow_html=True)

# Location Input Section
st.markdown("### 📍 Select Delivery Location")
preset_col1, preset_col2, preset_col3, preset_col4, _ = st.columns([1,1,1,1,4])
presets = [("Noida", "201306"), ("Mumbai", "400001"), ("Delhi", "110001"), ("Bangalore", "560001")]

if 'manual_loc' not in st.session_state:
    st.session_state.manual_loc = "201306"

for i, (name, code) in enumerate(presets):
    with [preset_col1, preset_col2, preset_col3, preset_col4][i]:
        if st.button(name, key=f"preset_{code}", use_container_width=True, disabled=st.session_state.is_location_set):
            st.session_state.manual_loc = code
            st.rerun()

col1, col2 = st.columns([3, 1])
with col1:
    location = st.text_input("Pincode", st.session_state.manual_loc, disabled=st.session_state.is_location_set)
with col2:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button("Set Location", type="primary", use_container_width=True, disabled=st.session_state.is_location_set):
        with st.spinner("Initializing vendor sessions... This may take up to 15 seconds."):
            res = run_async_task(run_set_location_all(location))
        st.session_state.is_location_set = True
        st.session_state.current_location = location
        st.session_state.location_results = res
        st.rerun()

if st.session_state.is_location_set:
    succ_col, btn_col = st.columns([4, 1])
    with succ_col:
        st.success(f"Success! Vendors initialized for location: **{st.session_state.current_location}**")
        
        # Display vendor statuses
        if 'location_results' in st.session_state:
            status_html = "<div style='display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px;'>"
            for svc, success in st.session_state.location_results.items():
                if success:
                    status_html += f"<span style='background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 4px 10px; border-radius: 20px; font-size: 0.85em; font-weight: 600;'>[OK] {svc.capitalize()}</span>"
                else:
                    status_html += f"<span style='background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 4px 10px; border-radius: 20px; font-size: 0.85em; font-weight: 600;'>[ERR] {svc.capitalize()} Failed</span>"
            status_html += "</div>"
            st.markdown(status_html, unsafe_allow_html=True)
    with btn_col:
        if st.button("Change Location", use_container_width=True):
            st.session_state.is_location_set = False
            for svc in SERVICES:
                st.session_state.services[svc]['products'] = []
                st.session_state.services[svc]['status'] = 'idle'
            st.rerun()

st.markdown("---")

# Search Input Section
st.markdown("### 🔍 Search Products")
col3, col4 = st.columns([3, 1])
with col3:
    search_term = st.text_input("What are you looking for?", "", placeholder="e.g. Milk, Bread, Eggs...", disabled=not st.session_state.is_location_set)
with col4:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button("Search All Apps", type="primary", use_container_width=True, disabled=not st.session_state.is_location_set or not search_term):
        with st.spinner(f"Searching for '{search_term}' across all vendors..."):
            res = run_async_task(run_search_all(search_term))
            for svc in SERVICES:
                prods = res.get(svc, [])
                st.session_state.services[svc]['products'] = prods
                st.session_state.services[svc]['status'] = 'success' if len(prods) > 0 else 'empty'
        st.rerun()

st.markdown("<br/>", unsafe_allow_html=True)

# Display Results
has_active_searches = any(data['status'] != 'idle' for data in st.session_state.services.values())

if has_active_searches:
    vendor_cols = st.columns(len(SERVICES))
    
    for i, (svc_name, svc_data) in enumerate(st.session_state.services.items()):
        with vendor_cols[i]:
            st.markdown(f"<div style='text-align:center;'><div class='brand-badge bg-{svc_name}'>{svc_name}</div></div>", unsafe_allow_html=True)
            
            if svc_data['status'] == 'success':
                st.caption(f"Found {len(svc_data['products'])} items")
                for product in svc_data['products']:
                    img_tag = f"<img src='{product.get('imageUrl')}' class='product-img'/>" if product.get('imageUrl') else ""
                    orig_price = f"<span class='original-price'>{product['originalPrice']}</span>" if product.get('originalPrice') else ""
                    discount = f"<span class='discount-badge'>{product['discount']}</span>" if product.get('discount') else ""
                    
                    card_html = f"""
                    <div class="glass-card">
                        {img_tag}
                        <div class="product-title">{product['name']}</div>
                        <div style="color: #cbd5e1; font-size: 0.8em; margin-bottom: 8px;">{product.get('quantity', '1 item')} | Time: {product.get('deliveryTime', 'N/A')}</div>
                        <div class="price-row">
                            <span class="current-price">{product['price']}</span>
                            {orig_price}
                        </div>
                        <div style="margin-top:4px;">{discount}</div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
            elif svc_data['status'] == 'empty':
                st.warning(f"No products found")