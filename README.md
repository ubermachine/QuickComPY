# QuickCom Scraper

QuickCom is a web application that helps you find and compare product prices across Blinkit, Bigbasket, and JioMart. Instead of checking each app individually, you can search once and see all the options, saving you time and money when ordering groceries or essentials.

## Demo

### Location Setting & Search Interface
![Location and Search Interface](./screenshots/quickcom-search-interface.png)

### Product Results Across Platforms
![Product Results](./screenshots/quickcom-results.png)

## Features

- **Multi-platform Search**: Find products across multiple platforms with one search
- **Location-based Results**: Set your location once to get accurate delivery options
- **Real-time Comparison**: See prices and delivery times side by side
- **Visual Indicators**: Easily spot discounts and best deals
- **Responsive Design**: Works well on both desktop and mobile
- **Live Updates**: Results appear as they're found thanks to WebSocket integration
- **Complete Product Info**: See quantity, price, discounts, and delivery times

## Project Structure

```
QuickCom/
├── backend_py/                # Python backend server
│   ├── scrapers/              # Individual store scrapers
│   │   ├── blinkit.py
│   │   ├── bigbasket.py
│   │   └── jiomart.py
│   ├── server.py              # Main FastAPI server
│   └── stealth.py             # Playwright stealth utilities
├── streamlit/                 # Python Streamlit Frontend
│   └── app.py                 # Main UI application
├── requirements.txt           # Python Dependencies
└── README.md                  # This documentation
```

## Technology Stack

### Backend
- **Python** - Programming language
- **FastAPI** - Web framework
- **WebSocket** - Real-time communication
- **Zendriver** - Web automation and scraping

### Frontend
- **Python** - Programming language
- **Streamlit** - UI framework
- **websocket-client** - WebSocket communication library

### Installation

1. **Clone the Repository:**
```shell
git clone https://github.com/yourusername/QuickCom.git
cd QuickCom
```

2. **Install Dependencies:**
```shell
pip install -r requirements.txt
playwright install chromium
```

### Running the Application

1. **Start the Backend Server:**
```shell
python backend_py/server.py
```
The backend will run on `http://localhost:5000`

2. **Start the Streamlit Application (in a new terminal):**
```shell
streamlit run streamlit/app.py
```
The frontend will run on `http://localhost:8501`

3. **Access the Dashboard:**
Open your browser and navigate to `http://localhost:8501`

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

Happy shopping and happy scraping! 🚀
# QuickComPY
