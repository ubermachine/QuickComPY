import asyncio
import zendriver as zd
import time

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('http://localhost:8501', new_tab=True)
        print("Navigated to localhost:8501")
        
        # Wait for Streamlit to load the DOM elements
        await asyncio.sleep(5)
        
        # Check if Set Location button exists and is enabled
        res = await page.evaluate("""
        (() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const setLocBtn = buttons.find(b => b.textContent.includes('Set Location'));
            if (!setLocBtn) return "Button not found";
            if (setLocBtn.disabled) return "Button is disabled";
            setLocBtn.click();
            return "Clicked Set Location!";
        })()
        """)
        print("UI Test Result:", res)
        
        if res == "Clicked Set Location!":
            await asyncio.sleep(2)
            # Check if loading message appeared
            res2 = await page.evaluate("""
            (() => {
                const infoMsg = document.querySelector('.stAlert');
                return infoMsg ? infoMsg.textContent : "No alert found";
            })()
            """)
            print("UI Feedback after click:", res2)
            
            # Wait 50 seconds to see if it succeeds
            print("Waiting 50 seconds for location setup...")
            await asyncio.sleep(50)
            
            res3 = await page.evaluate("""
            (() => {
                const successMsg = document.querySelector('.stAlert[data-baseweb="notification"]');
                return successMsg ? successMsg.textContent : document.body.innerText.substring(0,200);
            })()
            """)
            print("UI Result after wait:", res3)
            
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
