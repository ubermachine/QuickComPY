async function setBigbasketLocation(page, loc) {
  console.log(`Setting Bigbasket location to: ${loc}`);
  try {
    // Navigate to Bigbasket if not already there
    if (!page.url().includes("bigbasket.com")) {
      await page.goto("https://www.bigbasket.com/", {
        waitUntil: "domcontentloaded",
        timeout: 120000
      });
    }

    // Set viewport
    await page.setViewport({ width: 1280, height: 800 });

    // Click the Location selector button
    console.log("Clicking location selector button...");
    
    // Wait for the button to appear
    await page.waitForFunction(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      return buttons.some(b => b.textContent && (
        b.textContent.includes("Deliver to") || 
        b.textContent.includes("Delivery in") || 
        b.textContent.includes("Get it in") || 
        b.textContent.includes("Select Location")
      ));
    }, { timeout: 15000 }).catch(() => console.log("Timeout waiting for location button..."));

    const clicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const target = buttons.find(b => b.textContent && (
        b.textContent.includes("Deliver to") || 
        b.textContent.includes("Delivery in") || 
        b.textContent.includes("Get it in") || 
        b.textContent.includes("Select Location")
      ));
      if (target) {
        target.click();
        return true;
      }
      return false;
    });

    if (!clicked) {
      console.log("Failed to click location button, checking if already set...");
      const alreadySet = await isLocSet(page);
      if (alreadySet) return alreadySet;
      throw new Error("Could not find or click Location selector button");
    }

    await new Promise(r => setTimeout(r, 3000));

    // Type the location into the visible input
    console.log("Focusing and typing location in visible input...");
    const inputSelector = 'input[placeholder="Search for area or street name"]';
    await page.waitForSelector(inputSelector, { timeout: 15000 });

    // Find and type in the visible input
    const typeSuccess = await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input[placeholder="Search for area or street name"]'));
      const visibleInput = inputs.find(el => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
      });
      if (visibleInput) {
        visibleInput.click();
        visibleInput.focus();
        return true;
      }
      return false;
    });

    if (!typeSuccess) {
      throw new Error("Visible location search input not found in popup");
    }

    // Type using page.keyboard to simulate actual typing
    await page.keyboard.type(loc, { delay: 100 });
    console.log(`Typed location: ${loc}`);
    await new Promise(r => setTimeout(r, 4000)); // wait for autocomplete suggestions to render

    // Find suggestions list items and click the first matching suggestion
    console.log("Clicking first matching location suggestion...");
    const suggestionClicked = await page.evaluate((locText) => {
      const items = Array.from(document.querySelectorAll("li"));
      // Try to find suggestion matching search terms or just any suggestion if Noida/Delhi
      const cleanLoc = locText.toLowerCase();
      const target = items.find(item => {
        const txt = (item.textContent || "").toLowerCase();
        // Match if suggestion text contains some parts of search query
        return cleanLoc.split(" ").some(part => part.length > 2 && txt.includes(part));
      }) || items[0]; // fallback to first item

      if (target) {
        target.click();
        return target.textContent.trim();
      }
      return null;
    }, loc);

    if (!suggestionClicked) {
      console.log("No suggestions found or clicked. Attempting to check if location changed anyway...");
    } else {
      console.log(`Clicked suggestion: "${suggestionClicked}"`);
    }

    await new Promise(r => setTimeout(r, 5000)); // wait for reload/location setting

    const finalLocation = await isLocSet(page);
    if (finalLocation) {
      console.log(`Bigbasket location successfully set to: ${finalLocation}`);
      return finalLocation;
    }

    return "Location Set";
  } catch (err) {
    console.error("Error setting Bigbasket location:", err);
    return null;
  }
}

async function isLocSet(page) {
  try {
    const locText = await page.evaluate(() => {
      // Find delivery button text (usually contains 'Deliver to')
      const button = Array.from(document.querySelectorAll("button")).find(b => 
        b.textContent && (
          b.textContent.includes("Deliver to") || 
          b.textContent.includes("Delivery in") || 
          b.textContent.includes("Get it in") || 
          b.textContent.includes("Select Location")
        )
      );
      if (button) {
        const txt = button.textContent.trim();
        // If it still says "Select Location", it's not set
        if (txt.includes("Select Location")) return null;
        return txt;
      }
      return null;
    });
    return locText;
  } catch (e) {
    return null;
  }
}

module.exports = {
  setBigbasketLocation,
  isLocSet
};
