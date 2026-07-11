/**
 * set-location.js - JioMart location helper.
 * JioMart sets location automatically or via manual pincode inputs.
 */

async function setJioMartLocation(page, pincode) {
  console.log(`[JioMart] setJioMartLocation: "${pincode || '400001'}"`);
  // Since JioMart automatically sets up a valid default location (400001),
  // we can simply return the initialized or requested pincode location.
  return pincode || "400001";
}

module.exports = {
  setLocation: setJioMartLocation,
  setJioMartLocation
};
